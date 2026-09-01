"""Script standalone: verifica que `McpRegistry.discover()` se recupera de uma 1a tentativa
travada (AD-015, STATE.md).

Roda em um PROCESSO ISOLADO (via `subprocess`, chamado por `test_registry.py`) -- nunca no
mesmo processo pytest que os outros testes de integração. Necessário porque este teste envolve
uma conexão MCP real que é cancelada em pleno voo (a 1a tentativa, forçadamente interrompida
pelo timeout) -- um padrão de poluição de processo ainda mais forte que o do AD-011: mesmo
como o ÚLTIMO teste do seu próprio arquivo, ele corrompeu testes de OUTROS arquivos de
integração que rodam depois no mesmo processo (`test_routes_health.py`,
`test_routes_servers.py`, `test_routes_tasks.py`). Isolar em subprocesso elimina o problema
por construção.

Sai com código 0 e imprime "ok" em stdout se a recuperação funcionar; propaga qualquer exceção
(código de saída != 0, traceback em stderr) caso contrário.
"""

import asyncio
import sys

from fastmcp import FastMCP

from integration.mcp_test_server import flaky_first_attempt_server
from orchestrator.mcp_client.registry import McpRegistry, ServerConfig


def _make_success_server() -> FastMCP:
    mcp = FastMCP("fake-fs")

    @mcp.tool
    def read_file(path: str) -> str:
        """Read a file's content."""
        return f"content of {path}"

    return mcp


async def _main() -> None:
    async with flaky_first_attempt_server(_make_success_server()) as url:
        registry = McpRegistry(
            [ServerConfig(name="filesystem", transport="streamable_http", url=url, timeout=1.0)]
        )

        await asyncio.wait_for(registry.discover(), timeout=10)

        servers = registry.servers()
        if servers[0]["status"] != "healthy":
            raise AssertionError(f"esperava 'healthy', obteve {servers[0]['status']!r}")
        tool_names = [t["name"] for t in servers[0]["tools"]]
        if "read_file" not in tool_names:
            raise AssertionError(f"'read_file' ausente em {tool_names!r}")


if __name__ == "__main__":
    asyncio.run(_main())
    print("ok")
    sys.exit(0)
