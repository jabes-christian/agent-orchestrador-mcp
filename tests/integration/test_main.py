"""Testes de integração de orchestrator.main (MCPO-02 AC1, edge case de configuração
inválida)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import FastMCP

from orchestrator.main import ServerMisconfiguredError, create_app
from orchestrator.mcp_client.exceptions import ServerUnavailableError
from orchestrator.mcp_client.registry import ServerConfig

from .mcp_test_server import NeverInvokedChatModel, run_fake_mcp_server


def _make_fake_mcp() -> FastMCP:
    mcp = FastMCP("fake-fs")

    @mcp.tool
    def read_file(path: str) -> str:
        """Read a file's content."""
        return f"content of {path}"

    return mcp


async def test_startup_discovers_tools_and_marks_a_reachable_server_healthy() -> None:
    async with run_fake_mcp_server(_make_fake_mcp()) as url:
        app = create_app(
            server_configs=[
                ServerConfig(name="filesystem", transport="streamable_http", url=url, timeout=5.0)
            ],
            model=NeverInvokedChatModel(),
        )

        # `TestClient` roda o lifespan numa thread/loop separada (portal) -- isso
        # congelaria o loop deste teste (e, com ele, o servidor MCP falso que também vive
        # nele) enquanto espera pela thread. Chamar `router.lifespan_context` direto roda
        # tudo no mesmo loop, sem essa disputa.
        async with app.router.lifespan_context(app):
            servers = app.state.registry.servers()

        assert servers[0]["status"] == "healthy"
        assert any(t["name"] == "read_file" for t in servers[0]["tools"])


async def test_startup_fails_fast_when_a_declared_server_has_no_dns_entry() -> None:
    # ".invalid" nunca resolve (RFC 2606) -- simula um server declarado em servers.yaml sem
    # servico correspondente no docker-compose.yml.
    app = create_app(
        server_configs=[
            ServerConfig(
                name="fetch",
                transport="streamable_http",
                url="http://this-service-does-not-exist.invalid:8000/mcp",
                timeout=1.0,
            )
        ],
        model=NeverInvokedChatModel(),
    )

    with pytest.raises(ServerMisconfiguredError):
        async with app.router.lifespan_context(app):
            pass


async def test_startup_succeeds_when_a_declared_server_merely_refuses_connection() -> None:
    # O host ("127.0.0.1") resolve normalmente -- so a conexao e recusada, o que e uma
    # indisponibilidade transitoria (MCPO-02 AC2), nao um erro de configuracao.
    app = create_app(
        server_configs=[
            ServerConfig(
                name="down", transport="streamable_http", url="http://127.0.0.1:1/mcp", timeout=1.0
            )
        ],
        model=NeverInvokedChatModel(),
    )

    async with app.router.lifespan_context(app):
        servers = app.state.registry.servers()

    assert servers[0]["status"] == "unhealthy"


def test_registered_exception_handlers_produce_the_catalog_error_envelope() -> None:
    app = create_app(server_configs=[], model=NeverInvokedChatModel())

    @app.get("/boom")
    async def _boom() -> None:
        raise ServerUnavailableError("indisponivel")

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MCP_SERVER_UNAVAILABLE"


def test_module_level_app_is_a_fastapi_instance() -> None:
    from orchestrator.main import app as default_app

    assert isinstance(default_app, FastAPI)
