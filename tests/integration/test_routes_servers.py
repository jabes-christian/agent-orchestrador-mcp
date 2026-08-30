"""Testes de integração de `GET /servers` (MCPO-02 AC3, AD-007)."""

from fastmcp import FastMCP
from httpx import ASGITransport, AsyncClient

from orchestrator.main import create_app
from orchestrator.mcp_client.registry import ServerConfig

from .mcp_test_server import NeverInvokedChatModel, run_fake_mcp_server


def _make_fake_filesystem_server() -> FastMCP:
    """Expõe uma tool de leitura e uma de escrita -- `write_file` já é classificada como
    escrita em `config/tool_policy.yaml` para o server `filesystem` (mesmo arquivo real usado
    em produção, ver tests/unit/test_policy.py para o precedente de reusar o config real)."""
    mcp = FastMCP("fake-fs")

    @mcp.tool
    def read_file(path: str) -> str:
        """Read a file's content."""
        return f"content of {path}"

    @mcp.tool
    def write_file(path: str, content: str) -> str:
        """Write content to a file."""
        return "ok"

    return mcp


async def test_get_servers_reports_write_true_from_policy_not_the_registry_placeholder() -> None:
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
                response = await client.get("/servers")

        assert response.status_code == 200
        body = response.json()
        servers = {s["name"]: s for s in body["servers"]}
        assert servers["filesystem"]["status"] == "healthy"

        tools = {t["name"]: t for t in servers["filesystem"]["tools"]}
        assert tools["read_file"]["write"] is False
        assert tools["write_file"]["write"] is True
