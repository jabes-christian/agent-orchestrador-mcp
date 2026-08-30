"""Testes unitários de orchestrator.graph.builder -- grafo completo com dublês de LLM e tools
(MCPO-03 AC4, design.md Secao 1)."""

import time

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from orchestrator.graph.builder import build_graph, compute_recursion_limit
from orchestrator.mcp_client.policy import ToolPolicy


def test_compute_recursion_limit_scales_with_max_iterations() -> None:
    assert compute_recursion_limit(5) == 2 + 5 * 3
    assert compute_recursion_limit(1) == 2 + 1 * 3


class _ScriptedChatModel:
    """Dublê de `BaseChatModel`: uma `AIMessage` por chamada, na ordem do script.
    `bind_tools()` é um no-op que retorna o próprio dublê -- não precisa ligar tools de
    verdade para o teste exercitar o grafo."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def bind_tools(self, tools: object) -> "_ScriptedChatModel":
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        response = self._responses[self.calls]
        self.calls += 1
        return response


class _FakeReadFileTool:
    """Dublê de `BaseTool`: sempre responde com sucesso."""

    name = "read_file"
    description = "Le o conteudo de um arquivo."

    async def ainvoke(self, call: dict) -> ToolMessage:
        return ToolMessage(content="conteudo do arquivo", status="success", tool_call_id=call["id"])


class _FakeWriteFileTool:
    """Dublê de `BaseTool`: nunca deveria ser invocado nos testes de bloqueio do `guard`."""

    name = "write_file"
    description = "Escreve conteudo em um arquivo."

    async def ainvoke(self, call: dict) -> ToolMessage:
        raise AssertionError("guard deveria ter bloqueado esta chamada antes de invocar a tool")


def _initial_state() -> dict:
    return {"task": "leia a.txt", "request_id": "r1", "started_at": time.monotonic()}


async def test_build_graph_resolves_a_task_end_to_end_via_a_tool() -> None:
    model = _ScriptedChatModel(
        [
            AIMessage(
                content="", tool_calls=[{"name": "read_file", "args": {"path": "a.txt"}, "id": "1"}]
            ),
            AIMessage(content="o arquivo contem: conteudo do arquivo", tool_calls=[]),
        ]
    )
    graph = build_graph(
        tools_by_server={"filesystem": [_FakeReadFileTool()]},
        policy=ToolPolicy({}),
        model=model,
        max_iterations=5,
        tool_timeout_s=5.0,
    )

    result = await graph.ainvoke(_initial_state())

    assert result["finish_reason"] == "completed"
    assert result["result"] == "o arquivo contem: conteudo do arquivo"
    assert result["used_tools"] == ["filesystem.read_file"]
    assert result["error"] is None
    assert model.calls == 2


async def test_build_graph_short_circuits_to_no_suitable_server() -> None:
    answer = "Dom Casmurro foi escrito por Machado de Assis."
    model = _ScriptedChatModel([AIMessage(content=answer)])
    graph = build_graph(
        tools_by_server={},
        policy=ToolPolicy({}),
        model=model,
        max_iterations=5,
        tool_timeout_s=5.0,
    )

    result = await graph.ainvoke(_initial_state())

    assert result["finish_reason"] == "no_suitable_server"
    assert result["used_tools"] == []
    assert result["error"] is None


async def test_build_graph_blocks_a_disallowed_write_tool_via_guard() -> None:
    model = _ScriptedChatModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "write_file", "args": {"path": "a.txt"}, "id": "1"}],
            )
        ]
    )
    policy = ToolPolicy({"filesystem": {"write_tools": ["write_file"], "allowlist": []}})
    graph = build_graph(
        tools_by_server={"filesystem": [_FakeReadFileTool(), _FakeWriteFileTool()]},
        policy=policy,
        model=model,
        max_iterations=5,
        tool_timeout_s=5.0,
    )

    result = await graph.ainvoke(_initial_state())

    assert result["finish_reason"] == "error"
    assert result["error"] == {
        "code": "TOOL_NOT_ALLOWED",
        "message": "a tool de escrita 'filesystem.write_file' nao esta na allowlist",
    }
    assert result["steps"][-1]["status"] == "blocked"
    assert model.calls == 1
