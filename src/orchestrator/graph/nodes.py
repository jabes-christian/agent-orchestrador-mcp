"""Nós `prepare` e `agent` do StateGraph (design.md -> Secao 1.3).

Cada nó é fabricado por uma função `make_*_node`, que fecha sobre as dependências resolvidas em
tempo de build do grafo (catálogo de tools, modelo de chat já `bind_tools`-ado) --
`graph/builder.py` (T24) é quem monta essas dependências a partir de `mcp_client.registry` e
`llm.provider`; este módulo nunca importa nenhum dos dois diretamente (AD-005, STATE.md).
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal, cast

import httpx
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from orchestrator.graph.prompts import ToolCatalogEntry, build_system_prompt
from orchestrator.graph.state import ErrorInfo, OrchestratorState
from orchestrator.llm.provider import ainvoke
from orchestrator.mcp_client.policy import ToolPolicy
from orchestrator.observability.trace import TraceStep

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


def make_tools_node(
    tools_by_name: dict[str, BaseTool],
    server_by_tool: dict[str, str],
    timeout_s: float,
) -> NodeFn:
    """Fabrica o nó `tools`: executa cada `tool_call` pendente da última `AIMessage` via
    `BaseTool.ainvoke`, com timeout `MCP_TOOL_TIMEOUT_S` e 1 retry restrito a falha de
    transporte (`TimeoutError`, `ConnectionError`, `httpx.TransportError` -- MCPO-05 AC1).
    Falha de aplicação (a tool respondeu com erro de negócio, já convertida pelo próprio
    LangChain em `ToolMessage(status="error")`) nunca é retentada.

    `tools_by_name` e `server_by_tool` são resolvidos por `graph/builder.py` (T24) a partir do
    `mcp_client.registry`; este módulo nunca importa `registry` diretamente (AD-005).

    Uma falha de transporte que persiste após o retry aborta o processamento do restante da
    leva e preenche `error` no estado retornado, em vez de levantar exceção -- assim os `steps`
    já acumulados nesta chamada do nó não se perdem (`finalize`, T23, decide o desfecho HTTP a
    partir do estado, não de uma exceção).

    SPEC_DEVIATION: design.md Secao 1.2 desenha `tools` com uma única aresta de saída (de volta
    para `agent`). Levantar exceção aqui (como `agent` faz para `LLM_PROVIDER_ERROR`) perderia
    os `steps` desta chamada do nó, que LangGraph só mescla ao estado a partir do que um nó
    *retorna*. Reason: `graph/builder.py` (T24) precisa de uma aresta condicional extra depois
    de `tools` (`error` preenchido -> `finalize`), não desenhada no diagrama original."""

    async def tools_node(state: OrchestratorState) -> dict[str, object]:
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls if isinstance(last_message, AIMessage) else []

        steps: list[TraceStep] = list(state["steps"])
        used_tools = list(state["used_tools"])
        tool_messages: list[ToolMessage] = []
        error: ErrorInfo | None = None

        for call in tool_calls:
            tool_name = call["name"]
            server = server_by_tool.get(tool_name, "unknown")
            tool = tools_by_name[tool_name]

            result: ToolMessage | None = None
            transport_exc: Exception | None = None
            duration_ms = 0
            attempt = 1
            for attempt in (1, 2):  # noqa: B007 -- lido apos o loop, na montagem do step
                started = time.monotonic()
                try:
                    invoked = await asyncio.wait_for(tool.ainvoke(call), timeout=timeout_s)
                except (TimeoutError, ConnectionError, httpx.TransportError) as exc:
                    duration_ms = int((time.monotonic() - started) * 1000)
                    transport_exc = exc
                    continue
                duration_ms = int((time.monotonic() - started) * 1000)
                result = cast(ToolMessage, invoked)
                transport_exc = None
                break

            if transport_exc is not None:
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "server": server,
                        "tool": tool_name,
                        "arguments": call["args"],
                        "duration_ms": duration_ms,
                        "attempt": attempt,
                        "status": "failure",
                    }
                )
                error = (
                    {
                        "code": "MCP_TOOL_TIMEOUT",
                        "message": str(transport_exc) or "a chamada de tool excedeu o timeout",
                    }
                    if isinstance(transport_exc, TimeoutError)
                    else {
                        "code": "MCP_SERVER_UNAVAILABLE",
                        "message": str(transport_exc) or "o mcp server nao esta disponivel",
                    }
                )
                break

            assert result is not None
            status: Literal["success", "failure"] = (
                "success" if result.status == "success" else "failure"
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "server": server,
                    "tool": tool_name,
                    "arguments": call["args"],
                    "duration_ms": duration_ms,
                    "attempt": attempt,
                    "status": status,
                }
            )
            if status == "success":
                identifier = f"{server}.{tool_name}"
                if identifier not in used_tools:
                    used_tools.append(identifier)
            tool_messages.append(result)

        return {
            "messages": tool_messages,
            "steps": steps,
            "used_tools": used_tools,
            "iterations": state["iterations"] + 1,
            "error": error,
        }

    return tools_node


def make_guard_node(policy: ToolPolicy, server_by_tool: dict[str, str]) -> NodeFn:
    """Fabrica o nó `guard`: bloqueia a leva inteira de `tool_calls` pendente se QUALQUER uma
    delas for uma tool de escrita fora da allowlist (MCPO-08 AC2/AC3), antes de qualquer
    chamada ao MCP server -- nenhuma tool da leva executa nesse caso, nem as que seriam
    permitidas (design.md -> nó `guard`). Só as tools efetivamente reprovadas ganham um step
    `"blocked"`; as demais da mesma leva nunca chegam a ser tentadas, então não geram step.

    `policy` e `server_by_tool` são resolvidos por `graph/builder.py` (T24) a partir de
    `mcp_client.policy`/`mcp_client.registry`; este módulo nunca importa `registry` diretamente
    (AD-005) -- `mcp_client.policy` é dependência declarada de `graph.nodes` (design.md ->
    Components)."""

    async def guard(state: OrchestratorState) -> dict[str, object]:
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls if isinstance(last_message, AIMessage) else []

        steps: list[TraceStep] = list(state["steps"])
        error: ErrorInfo | None = None

        for call in tool_calls:
            tool_name = call["name"]
            server = server_by_tool.get(tool_name, "unknown")
            if policy.is_allowed(server, tool_name):
                continue
            steps.append(
                {
                    "step": len(steps) + 1,
                    "server": server,
                    "tool": tool_name,
                    "arguments": call["args"],
                    "duration_ms": 0,
                    "attempt": 1,
                    "status": "blocked",
                }
            )
            if error is None:
                error = {
                    "code": "TOOL_NOT_ALLOWED",
                    "message": f"a tool de escrita '{server}.{tool_name}' nao esta na allowlist",
                }

        if error is None:
            return {}
        return {"steps": steps, "error": error}

    return guard
