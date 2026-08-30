"""Estado do grafo LangGraph (MCPO-03, MCPO-04): `OrchestratorState` e `ErrorInfo`.

`TraceStep` é reaproveitado de `observability.trace` (T5) -- mesmo formato de passo usado
tanto no estado interno do grafo quanto no `trace` final da resposta (via `TraceRecorder`),
sem duplicar a definição.
"""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from orchestrator.observability.trace import TraceStep

FinishReason = Literal["completed", "no_suitable_server", "max_iterations_reached", "error"]


class ErrorInfo(TypedDict):
    """Erro que terminou o grafo, presente só quando `finish_reason == "error"` (spec.md ->
    catálogo de erros)."""

    code: str
    message: str


class OrchestratorState(TypedDict):
    """Estado propagado entre os nós do `StateGraph` (design.md Sec 1.6)."""

    task: str
    request_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    iterations: int
    steps: list[TraceStep]
    used_tools: list[str]
    finish_reason: FinishReason | None
    error: ErrorInfo | None
    started_at: float
    # Escrito só por `graph.nodes.finalize` (T23); extraído do texto da ultima `AIMessage` com
    # conteudo, nao um espelho literal de `messages[-1].content` -- ver o docstring de
    # `make_finalize_node` para o motivo (caminho `max_iterations_reached` pode terminar numa
    # `AIMessage` so com `tool_calls`, `content` vazio).
    result: str | None
