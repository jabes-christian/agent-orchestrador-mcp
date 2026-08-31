"""Server MCP falso servido via stdio, para `tests/integration/test_shim.py` (T27).

Processo filho standalone: `StdioTransport` do fastmcp o inicia via subprocess e fala com ele
por stdin/stdout, exatamente como faz com os MCP servers oficiais reais (`server-filesystem`,
`github-mcp-server`) atrás do shim em produção.
"""

from fastmcp import FastMCP

mcp = FastMCP("fake-fs-stdio")


@mcp.tool
def read_file(path: str) -> str:
    """Read a file's content."""
    return f"content of {path}"


if __name__ == "__main__":
    mcp.run()  # default transport="stdio"
