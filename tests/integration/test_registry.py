"""Testes de integração de orchestrator.mcp_client.registry (MCPO-02 AC1/AC2/AC3).

Usa um servidor `fastmcp.FastMCP` real em uma porta efêmera (design.md Sec 6), não um mock, para
exercitar o transporte Streamable HTTP real de ponta a ponta.

O teste de retry (`test_discover_retries_once_and_recovers_from_a_flaky_first_attempt`) roda
em um SUBPROCESSO isolado (`registry_retry_check.py`), não neste processo pytest -- ver AD-015
em `STATE.md`. Envolve uma conexão MCP real cancelada em pleno voo (a 1ª tentativa,
forçadamente interrompida pelo timeout), um padrão de poluição de processo mais forte que o do
AD-011: mesmo como o último teste deste arquivo, corrompeu testes de OUTROS arquivos de
integração rodando depois no mesmo processo.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from fastmcp import FastMCP

from orchestrator.mcp_client.registry import McpRegistry, ServerConfig

from .mcp_test_server import black_hole_server, run_fake_mcp_server, sse_stream_hangs_server

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RETRY_CHECK_SCRIPT = Path(__file__).parent / "registry_retry_check.py"


def _make_success_server() -> FastMCP:
    mcp = FastMCP("fake-fs")

    @mcp.tool
    def read_file(path: str) -> str:
        """Read a file's content."""
        return f"content of {path}"

    return mcp


async def test_discover_populates_tools_for_a_healthy_server():
    async with run_fake_mcp_server(_make_success_server()) as url:
        registry = McpRegistry(
            [ServerConfig(name="filesystem", transport="streamable_http", url=url, timeout=5.0)]
        )

        await registry.discover()

        servers = registry.servers()
        assert len(servers) == 1
        assert servers[0]["name"] == "filesystem"
        assert servers[0]["status"] == "healthy"
        tool_names = [t["name"] for t in servers[0]["tools"]]
        assert "read_file" in tool_names


async def test_discover_marks_unreachable_server_unhealthy_without_aborting():
    # Nada escuta nesta porta de loopback -- a conexão é recusada imediatamente.
    registry = McpRegistry(
        [
            ServerConfig(
                name="down", transport="streamable_http", url="http://127.0.0.1:1/mcp", timeout=2.0
            )
        ]
    )

    await registry.discover()  # não deve levantar exceção

    servers = registry.servers()
    assert servers[0]["status"] == "unhealthy"
    assert servers[0]["tools"] == []


async def test_discover_isolates_one_server_failure_from_the_rest():
    async with run_fake_mcp_server(_make_success_server()) as healthy_url:
        registry = McpRegistry(
            [
                ServerConfig(
                    name="down",
                    transport="streamable_http",
                    url="http://127.0.0.1:1/mcp",
                    timeout=2.0,
                ),
                ServerConfig(
                    name="filesystem",
                    transport="streamable_http",
                    url=healthy_url,
                    timeout=5.0,
                ),
            ]
        )

        await registry.discover()

        by_name = {s["name"]: s for s in registry.servers()}
        assert by_name["down"]["status"] == "unhealthy"
        assert by_name["filesystem"]["status"] == "healthy"
        assert any(t["name"] == "read_file" for t in by_name["filesystem"]["tools"])


async def test_discover_marks_timed_out_server_unhealthy_without_aborting():
    async with black_hole_server() as url:
        registry = McpRegistry(
            [ServerConfig(name="slow", transport="streamable_http", url=url, timeout=0.3)]
        )

        await registry.discover()  # não deve levantar exceção nem travar

        servers = registry.servers()
        assert servers[0]["status"] == "unhealthy"


async def test_discover_marks_a_server_whose_sse_stream_never_responds_as_unhealthy():
    """Regressão do AD-014 (STATE.md): um server que entrega os headers HTTP de uma sessão
    Streamable HTTP válida (200 OK, `mcp-session-id`) mas nunca escreve o primeiro evento SSE
    -- diferente de `black_hole_server` (que nunca responde nada). `sse_read_timeout` do
    `MultiServerMCPClient` sozinho não interrompe essa leitura; sem o `asyncio.wait_for`
    explícito em `discover()`, este teste travaria indefinidamente."""
    async with sse_stream_hangs_server() as url:
        registry = McpRegistry(
            [ServerConfig(name="filesystem", transport="streamable_http", url=url, timeout=0.5)]
        )

        await asyncio.wait_for(registry.discover(), timeout=5)  # não deve travar

        servers = registry.servers()
        assert servers[0]["status"] == "unhealthy"


async def test_disabled_server_is_never_contacted_and_stays_unhealthy():
    registry = McpRegistry(
        [
            ServerConfig(
                name="filesystem",
                transport="streamable_http",
                url="http://127.0.0.1:1/mcp",
                timeout=1.0,
                enabled=False,
            )
        ]
    )

    await registry.discover()

    servers = registry.servers()
    assert servers[0]["status"] == "unhealthy"
    assert servers[0]["tools"] == []


async def test_get_tools_returns_all_discovered_tools():
    async with run_fake_mcp_server(_make_success_server()) as url:
        registry = McpRegistry(
            [ServerConfig(name="filesystem", transport="streamable_http", url=url, timeout=5.0)]
        )
        await registry.discover()

        tools = await registry.get_tools()

        assert any(t.name == "read_file" for t in tools)


def test_discover_retries_once_and_recovers_from_a_flaky_first_attempt() -> None:
    """Regressão do AD-015 (STATE.md): a 1ª tentativa de `discover()` trava (corrida de
    largada entre o healthcheck TCP do compose e o subprocesso stdio interno ainda não estar
    pronto), mas o server está genuinamente saudável a partir da 2ª. Sem o retry em
    `_discover_one`, o subprocesso (`registry_retry_check.py`) sai com código != 0 -- ver
    docstring do módulo para o motivo do isolamento em subprocesso."""
    result = subprocess.run(
        [sys.executable, str(_RETRY_CHECK_SCRIPT)],
        cwd=_REPO_ROOT,
        env={**os.environ, "PYTHONPATH": f"{_REPO_ROOT}{os.pathsep}{_REPO_ROOT / 'tests'}"},
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
