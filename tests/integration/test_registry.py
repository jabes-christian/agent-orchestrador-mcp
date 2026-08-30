"""Testes de integração de orchestrator.mcp_client.registry (MCPO-02 AC1/AC2/AC3).

Usa um servidor `fastmcp.FastMCP` real em uma porta efêmera (design.md Sec 6), não um mock, para
exercitar o transporte Streamable HTTP real de ponta a ponta.
"""

from fastmcp import FastMCP

from orchestrator.mcp_client.registry import McpRegistry, ServerConfig

from .mcp_test_server import black_hole_server, run_fake_mcp_server


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
