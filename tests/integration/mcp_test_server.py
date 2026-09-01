"""Auxiliares de teste: processos com o formato real de um servidor MCP, para testes de
integração.

`run_fake_mcp_server` inicia um servidor `fastmcp.FastMCP` real em uma porta efêmera do
localhost, servido via Streamable HTTP -- o mesmo mecanismo de transporte usado em produção, com
dados falsos (design.md Sec 6). `black_hole_server` aceita conexões TCP mas nunca responde,
usado para exercitar um timeout de rede genuíno (em contraste com uma recusa de conexão
imediata). `sse_stream_hangs_server` entrega os headers HTTP de uma sessão Streamable HTTP
válida (200 OK, `content-type: text/event-stream`, `mcp-session-id`) mas nunca escreve nenhum
evento -- reproduz o cenário do AD-014 (STATE.md): diferente de `black_hole_server` (que nunca
responde nada, nem os headers), aqui o handshake HTTP começa normalmente e é especificamente o
corpo da stream SSE que nunca chega, o cenário em que `sse_read_timeout` sozinho se mostrou
insuficiente.

`flaky_first_attempt_server` envolve um `fastmcp.FastMCP` real (como `run_fake_mcp_server`),
mas a PRIMEIRA requisição HTTP que chega trava para sempre (mesmo comportamento de
`sse_stream_hangs_server`); a partir da segunda requisição em diante, delega normalmente para
o `FastMCP` real. Reproduz a corrida de largada do AD-015 (STATE.md): o healthcheck TCP do
compose marca um MCP server `healthy` assim que o shim aceita conexão, mas o subprocesso
stdio interno pode não estar pronto ainda -- a 1ª tentativa de `discover()` trava, a 2ª
(retry) sucede normalmente.

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


async def _sse_hang_asgi_app(scope: dict, receive: object, send: object) -> None:
    """App ASGI minima (sem fastmcp/mcp) que abre uma sessao Streamable HTTP valida e
    trava para sempre antes de escrever o primeiro evento."""
    if scope["type"] != "http":
        return
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/event-stream"),
                (b"cache-control", b"no-cache, no-transform"),
                (b"mcp-session-id", b"fake-session-id-nunca-usada"),
            ],
        }
    )
    await asyncio.sleep(3600)


@asynccontextmanager
async def sse_stream_hangs_server() -> AsyncIterator[str]:
    """Servidor ASGI real (uvicorn) cujo `/mcp` sempre entrega headers 200 OK de uma sessao
    Streamable HTTP e depois nunca escreve nenhum evento SSE (ver docstring do modulo,
    AD-014).

    O handler de request desta app fica preso em `asyncio.sleep(3600)` propositalmente -- um
    shutdown gracioso do uvicorn esperaria essa request "terminar" antes de retornar, o que
    nunca aconteceria. Mesmo padrao de tolerancia curta usado em `black_hole_server` abaixo:
    sinaliza saida e da um prazo curto antes de seguir em frente de qualquer forma.
    """
    config = uvicorn.Config(_sse_hang_asgi_app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(serve_task, timeout=0.5)


@asynccontextmanager
async def flaky_first_attempt_server(mcp: FastMCP) -> AsyncIterator[str]:
    """Servidor Streamable HTTP real cuja primeira requisição HTTP trava para sempre; a
    partir da segunda, delega normalmente para `mcp` (ver docstring do módulo, AD-015)."""
    real_app = mcp.http_app(path="/mcp")
    call_count = 0

    async def flaky_app(scope: dict, receive: object, send: object) -> None:
        nonlocal call_count
        if scope["type"] != "http":
            await real_app(scope, receive, send)
            return
        call_count += 1
        if call_count == 1:
            await _sse_hang_asgi_app(scope, receive, send)
            return
        await real_app(scope, receive, send)

    config = uvicorn.Config(flaky_app, host="127.0.0.1", port=0, log_level="error", lifespan="on")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(serve_task, timeout=0.5)


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
