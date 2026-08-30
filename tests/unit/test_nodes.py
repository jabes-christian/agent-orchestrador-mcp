"""Testes unitários de orchestrator.graph.nodes -- nós `prepare` e `agent` (MCPO-01, MCPO-05
AC5)."""

from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from orchestrator.graph.nodes import make_agent_node, make_prepare_node
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
