"""Wrapper de acesso ao LLM via OpenRouter (MCPO-05 AC5, AD-003).

`get_chat_model()` fabrica um `ChatOpenRouter` puro (`langchain-openrouter`, não
`ChatOpenAI(base_url=...)` -- AD-003) para o nó `agent` do grafo poder chamar `.bind_tools(...)`
normalmente. A tradução de erro fica isolada em `ainvoke()`: qualquer exceção do provider
(timeout, erro HTTP, erro de payload do SDK) vira `LlmProviderError`, que estende
`McpClientError` (T7) só para ser coberta pelo mesmo handler genérico que `api.errors` (T13) já
registra -- nenhum handler específico para `LLM_PROVIDER_ERROR` precisa existir.
"""

from collections.abc import Sequence

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from langchain_openrouter import ChatOpenRouter
from pydantic import SecretStr

from orchestrator.mcp_client.exceptions import McpClientError
from orchestrator.settings import Settings


class LlmProviderError(McpClientError):
    """OpenRouter indisponível ou retornou erro (spec.md -> catálogo de erros)."""

    error_code = "LLM_PROVIDER_ERROR"
    http_status = 502


def get_chat_model(settings: Settings | None = None) -> ChatOpenRouter:
    """Fábrica do modelo de chat via OpenRouter (AD-003). `settings=None` carrega a
    configuração real do ambiente; injetável em teste."""
    # pydantic-settings le os campos obrigatorios do .env/ambiente em runtime.
    resolved = settings or Settings()  # type: ignore[call-arg]
    return ChatOpenRouter(
        model=resolved.openrouter_model, api_key=SecretStr(resolved.openrouter_api_key)
    )


async def ainvoke(
    model: Runnable[LanguageModelInput, AIMessage], messages: Sequence[BaseMessage]
) -> AIMessage:
    """Invoca `model` (um `ChatOpenRouter` puro ou já `bind_tools`-ado) e converte qualquer
    falha do provider em `LlmProviderError`, para o nó `agent` (T19) nunca propagar uma exceção
    não classificada do SDK do OpenRouter."""
    try:
        return await model.ainvoke(messages)
    except Exception as exc:
        raise LlmProviderError(str(exc) or "erro no provider OpenRouter") from exc
