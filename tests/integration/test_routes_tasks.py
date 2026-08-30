"""Testes de integração de `POST /tasks` (MCPO-01, MCPO-04, MCPO-05 AC4, MCPO-06)."""

import asyncio

from fastmcp import FastMCP
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, ToolMessage

from orchestrator.api.auth import get_settings
from orchestrator.main import create_app
from orchestrator.mcp_client.policy import ToolPolicy
from orchestrator.mcp_client.registry import ServerConfig
from orchestrator.settings import Settings

from .mcp_test_server import run_fake_mcp_server

_API_KEY = "correct-key"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "orchestrator_api_key": _API_KEY,
        "openrouter_api_key": "test-openrouter-key",
        "openrouter_model": "test/model",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _make_fake_filesystem_server() -> FastMCP:
    mcp = FastMCP("fake-fs")

    @mcp.tool
    def read_file(path: str) -> str:
        """Read a file's content."""
        return f"content of {path}"

    return mcp


class _ScriptedChatModel:
    """Dublê de `BaseChatModel`: uma `AIMessage` por chamada, na ordem do script (mesmo
    precedente de `tests/unit/test_builder.py`)."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def bind_tools(self, tools: object) -> "_ScriptedChatModel":
        return self

    async def ainvoke(self, messages: object) -> AIMessage:
        response = self._responses[self.calls]
        self.calls += 1
        return response


class _AssertNeverCalledModel:
    """Dublê que falha se `ainvoke` for chamado -- prova que autenticação inválida impede a
    rota de sequer tentar invocar o grafo."""

    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools: object) -> "_AssertNeverCalledModel":
        return self

    async def ainvoke(self, messages: object) -> AIMessage:
        self.calls += 1
        raise AssertionError("o grafo nao deveria ter sido invocado com autenticacao invalida")


class _FakeReadFileTool:
    """Dublê de `BaseTool` (mesmo precedente de `tests/unit/test_builder.py`): sempre
    responde com sucesso, sem nenhuma conexão MCP real. Usado no teste de timeout para que
    o `tools` node produza um step real sem depender de `run_fake_mcp_server` -- ver AD-011
    em `STATE.md`: uma segunda conexão MCP real no mesmo processo, após uma primeira já ter
    executado uma tool de verdade, trava indefinidamente (bug de afinidade a event loop no
    SDK `mcp`/`langchain-mcp-adapters` subjacente)."""

    name = "read_file"
    description = "Le o conteudo de um arquivo."

    async def ainvoke(self, call: dict) -> ToolMessage:
        return ToolMessage(content="content of a.txt", status="success", tool_call_id=call["id"])


class _SlowThenHangModel:
    """Dublê: a primeira chamada retorna de imediato pedindo uma tool; a segunda nunca
    retorna dentro do `REQUEST_TIMEOUT_S` do teste -- simula o provider LLM travado, para
    exercitar o cancelamento por `asyncio.timeout` em `api.routes_tasks` (T25)."""

    def __init__(self, first_response: AIMessage) -> None:
        self._first_response = first_response
        self.calls = 0

    def bind_tools(self, tools: object) -> "_SlowThenHangModel":
        return self

    async def ainvoke(self, messages: object) -> AIMessage:
        self.calls += 1
        if self.calls == 1:
            return self._first_response
        await asyncio.sleep(5)
        raise AssertionError("nao deveria retornar -- o teste espera o timeout antes disso")


async def test_post_tasks_returns_200_with_full_trace_on_success() -> None:
    async with run_fake_mcp_server(_make_fake_filesystem_server()) as url:
        model = _ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "read_file", "args": {"path": "a.txt"}, "id": "1"}],
                ),
                AIMessage(content="o arquivo contem: content of a.txt", tool_calls=[]),
            ]
        )
        app = create_app(
            server_configs=[
                ServerConfig(name="filesystem", transport="streamable_http", url=url, timeout=5.0)
            ],
            policy=ToolPolicy({}),
            model=model,
        )
        app.dependency_overrides[get_settings] = lambda: _settings()

        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/tasks", json={"task": "leia a.txt"}, headers={"X-API-Key": _API_KEY}
                )

        assert response.status_code == 200
        body = response.json()
        assert body["result"] == "o arquivo contem: content of a.txt"
        trace = body["trace"]
        assert trace["finish_reason"] == "completed"
        assert trace["iterations"] == 1
        assert trace["used_tools"] == ["filesystem.read_file"]
        assert trace["steps"][0]["status"] == "success"
        assert trace["request_id"]
        assert trace["duration_ms"] >= 0


async def test_post_tasks_rejects_invalid_api_key_before_invoking_the_graph() -> None:
    model = _AssertNeverCalledModel()
    app = create_app(server_configs=[], policy=ToolPolicy({}), model=model)
    app.dependency_overrides[get_settings] = lambda: _settings()

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/tasks", json={"task": "qualquer tarefa"}, headers={"X-API-Key": "wrong-key"}
            )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert model.calls == 0


async def test_post_tasks_returns_request_timeout_with_the_partial_trace_so_far() -> None:
    model = _SlowThenHangModel(
        AIMessage(
            content="",
            tool_calls=[{"name": "read_file", "args": {"path": "a.txt"}, "id": "1"}],
        )
    )
    app = create_app(
        server_configs=[],
        tools_by_server={"filesystem": [_FakeReadFileTool()]},
        policy=ToolPolicy({}),
        model=model,
    )
    app.dependency_overrides[get_settings] = lambda: _settings(request_timeout_s=1)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/tasks", json={"task": "leia a.txt"}, headers={"X-API-Key": _API_KEY}
            )

    assert response.status_code == 504
    body = response.json()
    assert body["error"]["code"] == "REQUEST_TIMEOUT"
    trace = body["trace"]
    assert trace["finish_reason"] == "error"
    assert trace["steps"][0]["status"] == "success"
    assert trace["steps"][0]["tool"] == "read_file"
