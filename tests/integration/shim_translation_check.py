"""Script standalone: verifica que o shim traduz uma sessão stdio para Streamable HTTP.

Roda em um PROCESSO ISOLADO (via `subprocess`, chamado por `test_shim.py`) -- nunca no mesmo
processo pytest que os outros testes de integração. Necessário por causa do AD-011
(`STATE.md`): mais de uma conexão MCP real no mesmo processo Python, em event loops
diferentes, trava indefinidamente (bug de afinidade a event loop no SDK `mcp` subjacente,
não deste projeto). Isolar esta checagem no próprio processo elimina o problema por
construção, sem reduzir a cobertura real do teste nem depender de nenhuma dependência nova.

Sai com código 0 e imprime o resultado da tool em stdout se a tradução funcionar; propaga
qualquer exceção (código de saída != 0, traceback em stderr) caso contrário.
"""

import asyncio
import sys

import uvicorn
from fastmcp import Client
from shim.mcp_http_shim import build_http_app, build_proxy


async def _main() -> str:
    proxy = build_proxy()
    app = build_http_app(proxy)

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}/mcp"

        async with Client(url) as client:
            result = await client.call_tool("read_file", {"path": "a.txt"})
    finally:
        server.should_exit = True
        await serve_task

    if result.data != "content of a.txt":
        raise AssertionError(f"resultado inesperado da tool atraves do shim: {result.data!r}")
    return str(result.data)


if __name__ == "__main__":
    print(asyncio.run(_main()))
    sys.exit(0)
