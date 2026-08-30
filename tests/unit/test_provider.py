"""Testes unitários de orchestrator.llm.provider (MCPO-05 AC5, AD-003)."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openrouter import ChatOpenRouter

from orchestrator.llm.provider import LlmProviderError, ainvoke, get_chat_model
from orchestrator.settings import Settings

SETTINGS = Settings(
    orchestrator_api_key="test-key",
    openrouter_api_key="test-openrouter-key",
    openrouter_model="test/model",
)


class _FakeModel:
    """Dublê de `Runnable[LanguageModelInput, AIMessage]`: só implementa `ainvoke`, o único
    método que `provider.ainvoke` usa."""

    def __init__(self, response: AIMessage | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    async def ainvoke(self, messages: list[BaseMessage]) -> Any:
        if self._error is not None:
            raise self._error
        return self._response


def test_get_chat_model_builds_a_chatopenrouter_from_settings() -> None:
    model = get_chat_model(SETTINGS)

    assert isinstance(model, ChatOpenRouter)
    assert model.model_name == "test/model"


async def test_ainvoke_returns_the_models_response_on_success() -> None:
    expected = AIMessage(content="ola")
    model = _FakeModel(response=expected)

    result = await ainvoke(model, [])

    assert result is expected


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timeout ao chamar o provider"),
        ConnectionError("conexao recusada pelo provider"),
        ValueError("OpenRouter API returned an error: rate limited (code: 429)"),
    ],
)
async def test_ainvoke_maps_any_provider_failure_to_llm_provider_error(error: Exception) -> None:
    model = _FakeModel(error=error)

    with pytest.raises(LlmProviderError) as exc_info:
        await ainvoke(model, [])

    assert exc_info.value.error_code == "LLM_PROVIDER_ERROR"
    assert exc_info.value.http_status == 502


async def test_ainvoke_wraps_the_original_exception_as_the_cause() -> None:
    original = ValueError("boom")
    model = _FakeModel(error=original)

    with pytest.raises(LlmProviderError) as exc_info:
        await ainvoke(model, [])

    assert exc_info.value.__cause__ is original
