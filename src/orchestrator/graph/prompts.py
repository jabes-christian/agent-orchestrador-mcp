"""Montagem dinâmica do system prompt a partir do catálogo de tools (MCPO-01, MCPO-02 AC4).

Nenhum nome de MCP server ou de tool aparece hardcoded aqui (AD-005, `STATE.md`) -- o prompt é
construído inteiramente a partir do catálogo recebido como parâmetro pelo nó `prepare` (T19).
Adicionar, remover ou renomear uma tool no catálogo de entrada muda o prompt sem exigir
nenhuma alteração neste arquivo.
"""

from typing import TypedDict

_INSTRUCTIONS = (
    "Voce e um agente que resolve tarefas usando as tools disponiveis abaixo, cada uma "
    "exposta por um MCP server. Para cada tool, o identificador e 'server.tool'. Encadeie "
    "quantas chamadas forem necessarias, reavaliando o progresso apos cada resultado. Se "
    "nenhuma tool listada cobrir a tarefa, responda diretamente sem chamar nenhuma tool."
)

_NO_TOOLS_NOTICE = "Nenhuma tool esta disponivel nesta execucao."


class ToolCatalogEntry(TypedDict):
    """Uma entrada do catálogo de tools passado para a montagem do prompt."""

    server: str
    name: str
    description: str


def build_system_prompt(tools: list[ToolCatalogEntry]) -> str:
    """Monta o system prompt do nó `agent` a partir do catálogo de tools resolvido em
    runtime (design.md -> nó `prepare`)."""
    if not tools:
        return f"{_INSTRUCTIONS}\n\n{_NO_TOOLS_NOTICE}"
    catalog = "\n".join(
        f"- {tool['server']}.{tool['name']}: {tool['description']}" for tool in tools
    )
    return f"{_INSTRUCTIONS}\n\nTools disponiveis:\n{catalog}"
