"""Auxiliares de teste: processos com o formato real de um servidor MCP, para testes de
integração.

`run_fake_mcp_server` inicia um servidor `fastmcp.FastMCP` real em uma porta efêmera do
localhost, servido via Streamable HTTP -- o mesmo mecanismo de transporte usado em produção, com
dados falsos (design.md Sec 6). `black_hole_server` aceita conexões TCP mas nunca responde,
usado para exercitar um timeout de rede genuíno (em contraste com uma recusa de conexão
imediata).

`NeverInvokedChatModel` é o dublê padrão para `orchestrator.main.create_app(model=...)` em
QUALQUER teste que não exercite `POST /tasks` de propósito (ex.: `test_main.py`,
`test_routes_servers.py`) -- ver AD-010 em `STATE.md`: construir um `ChatOpenRouter` real
(via `llm.provider.get_chat_model`) corrompe o event loop de testes async subsequentes no
mesmo processo (o SDK `openrouter` prende algum recurso ao loop em que foi construído). Como
`create_app()` monta o grafo no `lifespan` de toda app criada em teste, usar este dublê é
obrigatório para qualquer `create_app()` que não precise de um LLM funcional.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastmcp import FastMCP


class NeverInvokedChatModel:
    """Dublê mínimo de `BaseChatModel`: falha se `ainvoke` for chamado. Evita construir um
    `ChatOpenRouter` real em testes que não exercitam o LLM (ver docstring do módulo)."""

    def bind_tools(self, tools: object) -> "NeverInvokedChatModel":
        return self

    async def ainvoke(self, messages: object) -> Any:
        raise AssertionError("este dublê nao deveria ter sido invocado")


@asynccontextmanager
async def run_fake_mcp_server(mcp: FastMCP) -> AsyncIterator[str]:
    """Inicia `mcp` como um servidor Streamable HTTP em uma porta efêmera; retorna sua URL
    `/mcp`."""
    app = mcp.http_app(path="/mcp")
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await serve_task


async def _swallow(_reader: asyncio.StreamReader, _writer: asyncio.StreamWriter) -> None:
    # Aceita a conexão mas nunca responde, forçando o cliente a atingir seu próprio timeout.
    await asyncio.sleep(3600)


@asynccontextmanager
async def black_hole_server() -> AsyncIterator[str]:
    """Um servidor TCP que aceita conexões e nunca responde. Retorna sua URL base.

    `asyncio.start_server` já começa a aceitar conexões por conta própria -- nenhuma task
    `serve_forever()` é necessária. `close()` para de escutar imediatamente, mas a conexão pendente
    que expirou do lado do cliente ainda está sendo "tratada" por `_swallow`, que nunca retorna --
    então `wait_closed()` (que também espera por handlers de conexão em andamento) ficaria travado
    para sempre. Dá-se um curto período de tolerância e segue-se em frente de qualquer forma.
    """
    server = await asyncio.start_server(_swallow, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.close()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(server.wait_closed(), timeout=0.5)
