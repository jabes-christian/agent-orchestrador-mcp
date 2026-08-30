"""Builder do `StateGraph` do orquestrador (design.md -> Secao 1, MCPO-03 AC4).

Monta o grafo a partir dos nós de `graph/nodes.py` (T19-T23), resolvendo suas dependências
(catálogo de tools, modelo já `bind_tools`-ado, `policy`, mapeamento tool->server) a partir de
`tools_by_server` -- este módulo é o único ponto do pacote `graph/` que lê a saída de
`mcp_client.registry.McpRegistry.tools_by_server()`; nenhum nome de server/tool aparece
hardcoded aqui (AD-005) -- só se manipula a estrutura genérica recebida como parâmetro.

Arestas de erro não desenhadas no diagrama original de `design.md` Secao 1.2 (AD-008, T21):
`guard` e `tools` roteiam para `finalize` quando preenchem `state["error"]`, em vez de seguir o
caminho padrão (`guard` -> `tools`, `tools` -> `agent`).
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from orchestrator.graph.nodes import (
    make_agent_node,
    make_finalize_node,
    make_guard_node,
    make_prepare_node,
    make_route_after_agent,
    make_tools_node,
)
from orchestrator.graph.prompts import ToolCatalogEntry
from orchestrator.graph.state import OrchestratorState
from orchestrator.mcp_client.policy import ToolPolicy

# Passos por iteração do loop ReAct (agent -> guard -> tools) + prepare + finalize -- rede de
# segurança do runtime (design.md Secao 1.5), nunca o mecanismo primario de terminacao
# (route_after_agent, T20, ja garante isso via logica de negocio). Generoso de proposito: so
# deve disparar em caso de bug, nao em operacao normal.
_STEPS_PER_ITERATION = 3
_FIXED_STEPS = 2  # prepare + finalize


def compute_recursion_limit(max_iterations: int) -> int:
    """`recursion_limit` (design.md Secao 1.5) coerente com `MAX_REACT_ITERATIONS` -- aplicado
    por quem invoca o grafo compilado (`POST /tasks`, T25) via `RunnableConfig`, não em
    `compile()` (a API do LangGraph não aceita `recursion_limit` nesse ponto)."""
    return _FIXED_STEPS + max_iterations * _STEPS_PER_ITERATION


def build_graph(
    tools_by_server: dict[str, list[BaseTool]],
    policy: ToolPolicy,
    model: BaseChatModel,
    max_iterations: int,
    tool_timeout_s: float,
) -> CompiledStateGraph:
    """Monta e compila o `StateGraph` completo (design.md Secao 1.2):

    `START -> prepare -> agent -> route_after_agent -> {guard, finalize}`
    `guard -> {tools, finalize}` (erro de allowlist -> finalize; senão -> tools)
    `tools -> {agent, finalize}` (erro de transporte -> finalize; senão -> agent)
    `finalize -> END`
    """
    tool_catalog: list[ToolCatalogEntry] = [
        {"server": server, "name": tool.name, "description": tool.description or ""}
        for server, tools in tools_by_server.items()
        for tool in tools
    ]
    tools_by_name: dict[str, BaseTool] = {
        tool.name: tool for tools in tools_by_server.values() for tool in tools
    }
    server_by_tool: dict[str, str] = {
        tool.name: server for server, tools in tools_by_server.items() for tool in tools
    }
    bound_model = model.bind_tools(list(tools_by_name.values())) if tools_by_name else model
    route_after_agent = make_route_after_agent(max_iterations)

    graph = StateGraph(OrchestratorState)
    graph.add_node("prepare", make_prepare_node(tool_catalog))
    graph.add_node("agent", make_agent_node(bound_model))
    graph.add_node("guard", make_guard_node(policy, server_by_tool))
    graph.add_node("tools", make_tools_node(tools_by_name, server_by_tool, tool_timeout_s))
    graph.add_node("finalize", make_finalize_node(route_after_agent))

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "agent")
    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "guard": "guard",
            "completed": "finalize",
            "no_suitable_server": "finalize",
            "max_iterations_reached": "finalize",
        },
    )
    graph.add_conditional_edges(
        "guard", lambda state: "finalize" if state["error"] is not None else "tools"
    )
    graph.add_conditional_edges(
        "tools", lambda state: "finalize" if state["error"] is not None else "agent"
    )
    graph.add_edge("finalize", END)

    return graph.compile()
