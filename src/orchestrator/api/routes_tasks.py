"""Rota `POST /tasks` (MCPO-01, MCPO-04, MCPO-05 AC4, MCPO-06).

Único ponto do gateway que invoca o grafo compilado (T24). O grafo e o `recursion_limit`
correspondente são montados uma única vez no `lifespan` de `main.py` (T14/T25) a partir do
`registry` já descoberto -- esta rota só lê `request.app.state.graph`, no mesmo padrão que
`GET /servers` (T15) já usa para `request.app.state.registry`.

SPEC_DEVIATION: design.md Seção 1.5 nomeava literalmente `graph.ainvoke(...)` envolvido por
`asyncio.timeout(...)`, mas exigia no mesmo parágrafo que a resposta de timeout carregasse "o
trace parcial acumulado até o ponto do cancelamento (steps já executados continuam no
trace)" -- cancelar um `ainvoke()` não devolve nenhum estado parcial, as duas frases eram
incompatíveis. Reason: para cumprir a exigência de trace parcial (MCPO-04 AC1/AC2, contrato
de API), esta rota usa `graph.astream(..., stream_mode="values")` e guarda o último snapshot
de estado emitido a cada passo do grafo; se o timeout estourar no meio da execução, esse
último snapshot vira a base do `trace` de erro. `design.md` Seção 1.5 e a tabela de Error
Handling Strategy foram corrigidas para nomear `astream` (decisão do usuário, ver AD-009 em
`STATE.md`).
"""

import asyncio
import time
import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from langgraph.graph.state import CompiledStateGraph

from orchestrator.api.auth import get_settings, require_api_key
from orchestrator.api.schemas import ErrorDetail, ErrorResponse, TaskRequest, TaskResponse, Trace
from orchestrator.graph.state import OrchestratorState
from orchestrator.settings import Settings

router = APIRouter()

# Códigos que `graph.nodes.guard`/`graph.nodes.tools` podem preencher em `state["error"]`
# (design.md -> Error Handling Strategy). `LLM_PROVIDER_ERROR` não aparece aqui porque
# `llm.provider.ainvoke` o levanta como exceção (T17), nunca via `state["error"]` -- propaga
# direto para o handler genérico de `McpClientError` (T13).
_STATE_ERROR_HTTP_STATUS = {
    "MCP_SERVER_UNAVAILABLE": 502,
    "MCP_TOOL_TIMEOUT": 504,
    "TOOL_NOT_ALLOWED": 403,
}


def get_graph(request: Request) -> CompiledStateGraph:
    """O grafo compilado montado pelo `lifespan` da app (`main.py`, T14/T25)."""
    graph: CompiledStateGraph = request.app.state.graph
    return graph


def get_recursion_limit(request: Request) -> int:
    """O `recursion_limit` (design.md Seção 1.5) coerente com `MAX_REACT_ITERATIONS`,
    computado uma única vez pelo `lifespan` da app."""
    limit: int = request.app.state.graph_recursion_limit
    return limit


def _trace_from_state(request_id: str, state: OrchestratorState | None, duration_ms: int) -> Trace:
    """Monta o `Trace` de resposta a partir do estado do grafo -- completo (sucesso ou erro
    de negócio) ou parcial (timeout cancelou a execução antes de `finalize`)."""
    if state is None:
        return Trace(
            request_id=request_id,
            iterations=0,
            steps=[],
            used_tools=[],
            finish_reason="error",
            duration_ms=duration_ms,
        )
    return Trace(
        request_id=request_id,
        iterations=state["iterations"],
        steps=cast(list, state["steps"]),
        used_tools=state["used_tools"],
        finish_reason=state["finish_reason"] or "error",
        duration_ms=duration_ms,
    )


def _error_response(status_code: int, code: str, message: str, trace: Trace) -> JSONResponse:
    envelope = ErrorResponse(error=ErrorDetail(code=code, message=message), trace=trace)
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


@router.post("/tasks", dependencies=[Depends(require_api_key)], response_model=None)
async def post_tasks(
    body: TaskRequest,
    graph: Annotated[CompiledStateGraph, Depends(get_graph)],
    recursion_limit: Annotated[int, Depends(get_recursion_limit)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TaskResponse | JSONResponse:
    """`require_api_key` (T12) roda como dependency de rota -- resolvida pelo FastAPI antes
    do corpo desta função, então uma autenticação inválida nunca chega a invocar o grafo."""
    request_id = str(uuid.uuid4())
    started_at = time.monotonic()
    initial_state = {"task": body.task, "request_id": request_id, "started_at": started_at}

    last_state: OrchestratorState | None = None
    try:
        async with asyncio.timeout(settings.request_timeout_s):
            async for state in graph.astream(
                initial_state,
                config={"recursion_limit": recursion_limit},
                stream_mode="values",
            ):
                last_state = cast(OrchestratorState, state)
    except TimeoutError:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        trace = _trace_from_state(request_id, last_state, duration_ms)
        return _error_response(
            504,
            "REQUEST_TIMEOUT",
            "o request excedeu o tempo limite configurado",
            trace,
        )

    assert last_state is not None
    duration_ms = int((time.monotonic() - started_at) * 1000)
    trace = _trace_from_state(request_id, last_state, duration_ms)

    error = last_state["error"]
    if error is not None:
        status_code = _STATE_ERROR_HTTP_STATUS.get(error["code"], 500)
        return _error_response(status_code, error["code"], error["message"], trace)

    return TaskResponse(result=last_state["result"] or "", trace=trace)
