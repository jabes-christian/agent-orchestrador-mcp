"""Testes de integração de `GET /health` (MCPO-11 AC1)."""

from fastmcp import FastMCP
from httpx import ASGITransport, AsyncClient

from orchestrator.main import create_app
from orchestrator.mcp_client.registry import ServerConfig

from .mcp_test_server import NeverInvokedChatModel, run_fake_mcp_server


def _make_fake_filesystem_server() -> FastMCP:
    mcp = FastMCP("fake-fs")

    @mcp.tool
    def read_file(path: str) -> str:
        """Read a file's content."""
        return f"content of {path}"

    return mcp


async def test_get_health_reports_ok_when_every_server_is_healthy() -> None:
    async with run_fake_mcp_server(_make_fake_filesystem_server()) as url:
        app = create_app(
            server_configs=[
                ServerConfig(name="filesystem", transport="streamable_http", url=url, timeout=5.0)
            ],
            model=NeverInvokedChatModel(),
        )

        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["servers"] == [{"name": "filesystem", "status": "healthy"}]


async def test_get_health_reports_degraded_without_failing_the_route_when_a_server_is_down() -> (
    None
):
    async with run_fake_mcp_server(_make_fake_filesystem_server()) as url:
        app = create_app(
            server_configs=[
                ServerConfig(name="filesystem", transport="streamable_http", url=url, timeout=5.0),
                ServerConfig(
                    name="down",
                    transport="streamable_http",
                    url="http://127.0.0.1:1/mcp",
                    timeout=1.0,
                ),
            ],
            model=NeverInvokedChatModel(),
        )

        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        servers = {s["name"]: s["status"] for s in body["servers"]}
        assert servers == {"filesystem": "healthy", "down": "unhealthy"}
