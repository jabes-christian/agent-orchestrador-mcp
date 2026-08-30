"""Nós `prepare` e `agent` do StateGraph (design.md -> Secao 1.3).

Cada nó é fabricado por uma função `make_*_node`, que fecha sobre as dependências resolvidas em
tempo de build do grafo (catálogo de tools, modelo de chat já `bind_tools`-ado) --
`graph/builder.py` (T24) é quem monta essas dependências a partir de `mcp_client.registry` e
`llm.provider`; este módulo nunca importa nenhum dos dois diretamente (AD-005, STATE.md).
"""

from collections.abc import Awaitable, Callable
from typing import Literal

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from orchestrator.graph.prompts import ToolCatalogEntry, build_system_prompt
from orchestrator.graph.state import OrchestratorState
from orchestrator.llm.provider import ainvoke

NodeFn = Callable[[OrchestratorState], Awaitable[dict[str, object]]]
RouteDecision = Literal["guard", "completed", "no_suitable_server", "max_iterations_reached"]
RouteFn = Callable[[OrchestratorState], RouteDecision]


def make_prepare_node(tool_catalog: list[ToolCatalogEntry]) -> NodeFn:
    """Fabrica o nó `prepare`: monta o system prompt uma única vez a partir do catálogo de
    tools resolvido no build do grafo, e semeia `messages` com a `task` de cada request."""
    system_prompt = build_system_prompt(tool_catalog)

    async def prepare(state: OrchestratorState) -> dict[str, object]:
        return {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=state["task"]),
            ],
            "iterations": 0,
            "steps": [],
            "used_tools": [],
            "finish_reason": None,
            "error": None,
        }

    return prepare


def make_agent_node(model: Runnable[LanguageModelInput, AIMessage]) -> NodeFn:
    """Fabrica o nó `agent`: invoca `model` (já `bind_tools`-ado por `graph/builder.py`) com o
    histórico corrente. Qualquer falha do provider já chega como `LlmProviderError` via
    `llm.provider.ainvoke` (T17) -- este nó não precisa tratá-la, só deixa propagar."""

    async def agent(state: OrchestratorState) -> dict[str, object]:
        response = await ainvoke(model, state["messages"])
        return {"messages": [response]}

    return agent


def make_route_after_agent(max_iterations: int) -> RouteFn:
    """Fabrica `route_after_agent`: a tabela-verdade dos 4 caminhos pós-`agent` (design.md ->
    Secao 1.4), exaustiva e determinística -- nenhum quinto caminho implícito. `max_iterations`
    é injetado por `graph/builder.py` (T24) a partir de `Settings.max_react_iterations`; este
    módulo nunca lê `Settings` diretamente."""

    def route_after_agent(state: OrchestratorState) -> RouteDecision:
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls if isinstance(last_message, AIMessage) else []

        if tool_calls:
            if state["iterations"] < max_iterations:
                return "guard"
            return "max_iterations_reached"

        if state["used_tools"]:
            return "completed"
        return "no_suitable_server"

    return route_after_agent
