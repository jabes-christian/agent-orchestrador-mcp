"""Testes de integração do shim stdio↔Streamable HTTP (AD-001, T27).

O teste de tradução (`test_create_proxy_translates_a_stdio_session_to_streamable_http`) roda
em um SUBPROCESSO isolado (`shim_translation_check.py`), não no processo pytest deste
arquivo -- ver AD-011 em `STATE.md`. O teste de rejeição de `Origin` não faz nenhuma conexão
MCP real (a validação acontece no middleware, antes de qualquer sessão abrir), então roda
in-process normalmente.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from shim.mcp_http_shim import build_http_app, build_proxy

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STDIO_SERVER_SCRIPT = (Path(__file__).parent / "stdio_mcp_server.py").as_posix()
_TRANSLATION_CHECK_SCRIPT = Path(__file__).parent / "shim_translation_check.py"


@pytest.fixture
def _shim_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """As 3 env vars que `build_proxy()` lê, apontando para o server stdio falso de teste."""
    monkeypatch.setenv("MCP_STDIO_COMMAND", sys.executable)
    monkeypatch.setenv("MCP_STDIO_ARGS", _STDIO_SERVER_SCRIPT)
    monkeypatch.setenv("MCP_SERVER_NAME", "fake-fs-stdio")


def test_create_proxy_translates_a_stdio_session_to_streamable_http() -> None:
    result = subprocess.run(
        [sys.executable, str(_TRANSLATION_CHECK_SCRIPT)],
        cwd=_REPO_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(_REPO_ROOT),
            "MCP_STDIO_COMMAND": sys.executable,
            "MCP_STDIO_ARGS": _STDIO_SERVER_SCRIPT,
            "MCP_SERVER_NAME": "fake-fs-stdio",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "content of a.txt"


async def test_request_with_disallowed_origin_is_rejected(_shim_env: None) -> None:
    proxy = build_proxy()
    app = build_http_app(proxy)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {
            "Origin": "http://evil.example",
            "Accept": "application/json, text/event-stream",
        }
        response = await client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )

    assert response.status_code == 403
