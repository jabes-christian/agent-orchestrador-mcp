"""Testes unitários de orchestrator.graph.nodes -- nós `prepare`, `agent` e `tools`, e
`route_after_agent` (MCPO-01, MCPO-03 AC1, MCPO-04 AC2, MCPO-05 AC1/AC2/AC3, MCPO-05 AC5)."""

import asyncio
from collections.abc import Sequence

import httpx
import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from orchestrator.graph.nodes import (
    make_agent_node,
    make_prepare_node,
    make_route_after_agent,
    make_tools_node,
)
from orchestrator.graph.prompts import ToolCatalogEntry, build_system_prompt
from orchestrator.llm.provider import LlmProviderError

_CATALOG: list[ToolCatalogEntry] = [
    {"server": "filesystem", "name": "read_file", "description": "Le o conteudo de um arquivo."},
]


class _FakeModel:
    """Dublê roteirizado de `Runnable[LanguageModelInput, AIMessage]` (mesmo padrão de
    `test_provider.py`): só implementa `ainvoke`, o único método que `agent` usa."""

    def __init__(self, response: AIMessage | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


async def test_prepare_seeds_messages_with_the_system_prompt_and_the_task() -> None:
    prepare = make_prepare_node(_CATALOG)

    result = await prepare({"task": "liste os arquivos", "request_id": "r1", "started_at": 0.0})

    messages = result["messages"]
    assert isinstance(messages, list)
    assert messages[0] == SystemMessage(content=build_system_prompt(_CATALOG))
    assert messages[1] == HumanMessage(content="liste os arquivos")


async def test_prepare_initializes_the_rest_of_the_state() -> None:
    prepare = make_prepare_node(_CATALOG)

    result = await prepare({"task": "t", "request_id": "r1", "started_at": 0.0})

    assert result["iterations"] == 0
    assert result["steps"] == []
    assert result["used_tools"] == []
    assert result["finish_reason"] is None
    assert result["error"] is None


async def test_agent_records_the_llm_decision_in_state() -> None:
    expected = AIMessage(content="resposta final")
    agent = make_agent_node(_FakeModel(response=expected))

    result = await agent({"messages": [HumanMessage(content="t")]})

    assert result["messages"] == [expected]


async def test_agent_propagates_llm_provider_error() -> None:
    agent = make_agent_node(_FakeModel(error=ValueError("boom")))

    with pytest.raises(LlmProviderError):
        await agent({"messages": [HumanMessage(content="t")]})


def _state_with_last_message(message: AIMessage, iterations: int, used_tools: list[str]) -> dict:
    return {"messages": [message], "iterations": iterations, "used_tools": used_tools}


def test_route_after_agent_goes_to_guard_when_tool_calls_pending_and_under_the_limit() -> None:
    route = make_route_after_agent(max_iterations=5)
    message = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "1"}])

    result = route(_state_with_last_message(message, iterations=0, used_tools=[]))

    assert result == "guard"


def test_route_after_agent_goes_to_max_iterations_reached_at_the_limit() -> None:
    route = make_route_after_agent(max_iterations=5)
    message = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "1"}])
    state = _state_with_last_message(message, iterations=5, used_tools=["filesystem.read_file"])

    result = route(state)

    assert result == "max_iterations_reached"


def test_route_after_agent_goes_to_no_suitable_server_when_no_tool_calls_and_none_used() -> None:
    route = make_route_after_agent(max_iterations=5)
    message = AIMessage(content="resposta direta", tool_calls=[])

    result = route(_state_with_last_message(message, iterations=0, used_tools=[]))

    assert result == "no_suitable_server"


def test_route_after_agent_goes_to_completed_when_no_tool_calls_and_some_used() -> None:
    route = make_route_after_agent(max_iterations=5)
    message = AIMessage(content="resposta final", tool_calls=[])
    state = _state_with_last_message(message, iterations=1, used_tools=["filesystem.read_file"])

    result = route(state)

    assert result == "completed"


_CALL = {"name": "read_file", "args": {"path": "a.txt"}, "id": "call_1"}


def _state_with_pending_call(**overrides: object) -> dict:
    base = {
        "messages": [AIMessage(content="", tool_calls=[_CALL])],
        "iterations": 0,
        "steps": [],
        "used_tools": [],
    }
    base.update(overrides)
    return base


class _ScriptedTool:
    """Dublê de `BaseTool`: uma resposta ou exceção por tentativa, na ordem do script."""

    def __init__(self, script: list[ToolMessage | Exception]) -> None:
        self._script = list(script)
        self.calls = 0

    async def ainvoke(self, call: dict) -> ToolMessage:
        outcome = self._script[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _SlowTool:
    """Dublê de `BaseTool` que demora `delay` segundos a responder -- prova que o timeout
    configurado é de fato respeitado (`asyncio.wait_for` cancela antes do fim do sleep)."""

    def __init__(self, delay: float) -> None:
        self._delay = delay
        self.calls = 0

    async def ainvoke(self, call: dict) -> ToolMessage:
        self.calls += 1
        await asyncio.sleep(self._delay)
        return ToolMessage(content="nunca alcancado", status="success", tool_call_id=call["id"])


def _success_message(content: str = "ok") -> ToolMessage:
    return ToolMessage(content=content, status="success", tool_call_id=_CALL["id"])


def _error_message(content: str = "arquivo nao encontrado") -> ToolMessage:
    return ToolMessage(content=content, status="error", tool_call_id=_CALL["id"])


async def test_tools_node_records_a_success_step_and_used_tool() -> None:
    tool = _ScriptedTool([_success_message()])
    tools_node = make_tools_node(
        tools_by_name={"read_file": tool}, server_by_tool={"read_file": "filesystem"}, timeout_s=5.0
    )

    result = await tools_node(_state_with_pending_call())

    steps = result["steps"]
    assert steps[-1]["status"] == "success"
    assert steps[-1]["attempt"] == 1
    assert steps[-1]["server"] == "filesystem"
    assert steps[-1]["tool"] == "read_file"
    assert result["used_tools"] == ["filesystem.read_file"]
    assert result["iterations"] == 1
    assert result["error"] is None
    assert tool.calls == 1


async def test_tools_node_retries_once_on_timeout_then_succeeds() -> None:
    tool = _ScriptedTool([TimeoutError("timeout"), _success_message()])
    tools_node = make_tools_node(
        tools_by_name={"read_file": tool}, server_by_tool={"read_file": "filesystem"}, timeout_s=5.0
    )

    result = await tools_node(_state_with_pending_call())

    assert tool.calls == 2
    assert result["steps"][-1]["status"] == "success"
    assert result["steps"][-1]["attempt"] == 2
    assert result["error"] is None


async def test_tools_node_returns_mcp_tool_timeout_after_retry_exhausted() -> None:
    tool = _ScriptedTool([TimeoutError("timeout 1"), TimeoutError("timeout 2")])
    tools_node = make_tools_node(
        tools_by_name={"read_file": tool}, server_by_tool={"read_file": "filesystem"}, timeout_s=5.0
    )

    result = await tools_node(_state_with_pending_call())

    assert tool.calls == 2
    assert result["steps"][-1]["status"] == "failure"
    assert result["steps"][-1]["attempt"] == 2
    assert result["error"] == {"code": "MCP_TOOL_TIMEOUT", "message": "timeout 2"}


async def test_tools_node_returns_mcp_server_unavailable_after_connection_error_persists() -> None:
    tool = _ScriptedTool(
        [httpx.ConnectError("conexao recusada"), httpx.ConnectError("conexao recusada")]
    )
    tools_node = make_tools_node(
        tools_by_name={"read_file": tool}, server_by_tool={"read_file": "filesystem"}, timeout_s=5.0
    )

    result = await tools_node(_state_with_pending_call())

    assert result["steps"][-1]["status"] == "failure"
    assert result["error"] == {"code": "MCP_SERVER_UNAVAILABLE", "message": "conexao recusada"}


async def test_tools_node_respects_the_configured_timeout() -> None:
    tool = _SlowTool(delay=1.0)
    tools_node = make_tools_node(
        tools_by_name={"read_file": tool},
        server_by_tool={"read_file": "filesystem"},
        timeout_s=0.02,
    )

    result = await tools_node(_state_with_pending_call())

    assert tool.calls == 2
    assert result["error"]["code"] == "MCP_TOOL_TIMEOUT"


async def test_tools_node_records_application_failure_without_retry() -> None:
    tool = _ScriptedTool([_error_message()])
    tools_node = make_tools_node(
        tools_by_name={"read_file": tool}, server_by_tool={"read_file": "filesystem"}, timeout_s=5.0
    )

    result = await tools_node(_state_with_pending_call())

    assert tool.calls == 1
    assert result["steps"][-1]["status"] == "failure"
    assert result["steps"][-1]["attempt"] == 1
    assert result["used_tools"] == []
    assert result["error"] is None
    assert result["messages"] == [tool._script[0]]


async def test_tools_node_preserves_prior_steps_and_increments_iterations() -> None:
    tool = _ScriptedTool([_success_message()])
    tools_node = make_tools_node(
        tools_by_name={"read_file": tool}, server_by_tool={"read_file": "filesystem"}, timeout_s=5.0
    )
    prior_step = {
        "step": 1,
        "server": "github",
        "tool": "get_issue",
        "arguments": {},
        "duration_ms": 10,
        "attempt": 1,
        "status": "success",
    }
    state = _state_with_pending_call(
        steps=[prior_step], used_tools=["github.get_issue"], iterations=1
    )

    result = await tools_node(state)

    assert result["steps"][0] == prior_step
    assert result["steps"][1]["step"] == 2
    assert result["used_tools"] == ["github.get_issue", "filesystem.read_file"]
    assert result["iterations"] == 2
