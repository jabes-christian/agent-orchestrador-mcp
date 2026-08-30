"""Test helpers: real MCP-server-shaped processes for integration tests.

`run_fake_mcp_server` starts a real `fastmcp.FastMCP` server on an ephemeral localhost port,
served over Streamable HTTP -- the same transport mechanism production uses, with fake data
(design.md Sec 6). `black_hole_server` accepts TCP connections but never replies, used to exercise
a genuine network timeout (as opposed to an immediate connection refusal).
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastmcp import FastMCP


@asynccontextmanager
async def run_fake_mcp_server(mcp: FastMCP) -> AsyncIterator[str]:
    """Start `mcp` as a Streamable HTTP server on an ephemeral port; yield its `/mcp` URL."""
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
    # Accept the connection but never respond, forcing the client to hit its own timeout.
    await asyncio.sleep(3600)


@asynccontextmanager
async def black_hole_server() -> AsyncIterator[str]:
    """A TCP server that accepts connections and never answers. Yields its base URL.

    `asyncio.start_server` already starts accepting connections on its own -- no `serve_forever()`
    task is needed. `close()` stops listening immediately, but the dangling connection that timed
    out on the client side is still "handled" by `_swallow`, which never returns -- so
    `wait_closed()` (which waits for in-flight connection handlers too) would hang forever. Give
    it a short grace period and move on regardless.
    """
    server = await asyncio.start_server(_swallow, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.close()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(server.wait_closed(), timeout=0.5)
