"""Exception handlers do catálogo de erros da API (MCPO-05 AC6, MCPO-04 AC1).

Registra um handler por *tipo* de exceção, não por `error.code` -- só existem 3 tipos de
exceção neste catálogo de 8 códigos:

1. `McpClientError` (T7) -- classe base cujos atributos `error_code`/`http_status` já carregam
   o código certo. Um único handler genérico cobre `MCP_SERVER_UNAVAILABLE`,
   `MCP_TOOL_TIMEOUT`, `TOOL_NOT_ALLOWED`, `UNAUTHORIZED` (`api.auth.UnauthorizedError`, T12) e
   `LLM_PROVIDER_ERROR` (subclasse futura de `llm.provider`, T17) sem precisar conhecer cada
   subclasse -- qualquer exceção nova que estenda `McpClientError` já sai coberta.
2. `RequestValidationError` do FastAPI -- corpo de request inválido (`task` vazio/ausente/
   >4000 chars, ou JSON malformado) vira sempre `INVALID_TASK`/422, o único schema de entrada
   desta API (T11).
3. `TimeoutError` (inclui `asyncio.TimeoutError`, que é o mesmo tipo desde o Python 3.11) --
   estouro do timeout global do request, mapeado para `REQUEST_TIMEOUT`/504.

Qualquer outra exceção não prevista é capturada pelo handler global de `Exception` e vira
`INTERNAL_ERROR`/500 -- a regra fixa de MCPO-05 AC6 (nunca um 500 sem `error.code` do catálogo).

Em todo caso, a resposta carrega um `trace` (MCPO-04 AC1): se a rota já colocou um
`TraceRecorder` em `request.state.trace_recorder` (ex.: `POST /tasks` após iniciar a execução
do grafo, T25), o trace parcial acumulado até a falha é usado; caso contrário, um `TraceRecorder`
vazio recém-criado garante que o campo nunca fique ausente.
"""

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from orchestrator.api.schemas import ErrorDetail, ErrorResponse, Trace
from orchestrator.mcp_client.exceptions import McpClientError
from orchestrator.observability.trace import TraceRecorder

logger = logging.getLogger(__name__)


def _build_trace(request: Request) -> Trace:
    """Usa o `TraceRecorder` parcial da requisição, se algum nó já tiver criado um; senão,
    cria um vazio -- o contrato exige `trace` presente mesmo antes de qualquer execução de
    tool."""
    recorder: TraceRecorder | None = getattr(request.state, "trace_recorder", None)
    if recorder is None:
        recorder = TraceRecorder()
    return Trace.model_validate(recorder.to_dict(finish_reason="error"))


def _error_response(request: Request, *, code: str, message: str, status_code: int) -> JSONResponse:
    envelope = ErrorResponse(
        error=ErrorDetail(code=code, message=message),
        trace=_build_trace(request),
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


async def _handle_mcp_client_error(request: Request, exc: Exception) -> JSONResponse:
    # `add_exception_handler` só invoca este handler para exceções registradas como
    # `McpClientError` (ou subclasse) -- o cast só documenta essa garantia para o mypy.
    mcp_error = cast(McpClientError, exc)
    return _error_response(
        request,
        code=mcp_error.error_code,
        message=str(mcp_error) or mcp_error.error_code,
        status_code=mcp_error.http_status,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    validation_error = cast(RequestValidationError, exc)
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in validation_error.errors()
    )
    return _error_response(
        request,
        code="INVALID_TASK",
        message=details or "corpo do request invalido",
        status_code=422,
    )


async def _handle_request_timeout(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(
        request,
        code="REQUEST_TIMEOUT",
        message=str(exc) or "o request excedeu o tempo limite configurado",
        status_code=504,
    )


async def _handle_unclassified_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("erro nao classificado no catalogo de erros", exc_info=exc)
    return _error_response(
        request,
        code="INTERNAL_ERROR",
        message="erro interno inesperado",
        status_code=500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos os handlers do catálogo de erros na app do FastAPI (usado por
    `main.py`, T14)."""
    app.add_exception_handler(McpClientError, _handle_mcp_client_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(TimeoutError, _handle_request_timeout)
    app.add_exception_handler(Exception, _handle_unclassified_error)
