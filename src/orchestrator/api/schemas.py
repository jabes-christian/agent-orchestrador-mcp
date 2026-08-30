"""Schemas Pydantic do contrato HTTP da API (spec.md -> Contrato da API).

`Trace` espelha exatamente o formato produzido por `TraceRecorder.to_dict()` (T5) -- é o
schema de saída, nunca construído a mão fora dos testes. `TaskRequest` é o único schema de
entrada desta fase; sua validação implementa o edge case `INVALID_TASK` da spec (task vazia,
ausente, só espaços em branco, ou acima de 4000 caracteres).
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

TASK_MAX_LENGTH = 4000

FinishReason = Literal["completed", "no_suitable_server", "max_iterations_reached", "error"]
StepStatus = Literal["success", "failure", "blocked"]


class TaskRequest(BaseModel):
    """Corpo de `POST /tasks` (spec.md -> Contrato da API)."""

    task: str = Field(min_length=1, max_length=TASK_MAX_LENGTH)

    @field_validator("task")
    @classmethod
    def _reject_blank_task(cls, value: str) -> str:
        """Uma string só com espaços em branco conta como tarefa ausente."""
        if not value.strip():
            raise ValueError("task não pode ser vazia ou conter apenas espaços em branco")
        return value


class TraceStep(BaseModel):
    """Uma entrada de `trace.steps` (espelha `observability.trace.TraceStep`, T5)."""

    step: int
    server: str
    tool: str
    arguments: dict[str, object]
    duration_ms: int
    attempt: int
    status: StepStatus


class Trace(BaseModel):
    """O objeto `trace`, presente em toda resposta 200 e de erro (MCPO-04 AC1)."""

    request_id: str
    iterations: int
    steps: list[TraceStep]
    used_tools: list[str]
    finish_reason: FinishReason
    duration_ms: int


class TaskResponse(BaseModel):
    """Corpo de sucesso (HTTP 200) de `POST /tasks`."""

    result: str
    trace: Trace


class ErrorDetail(BaseModel):
    """Campo `error` do envelope de erro (spec.md -> catálogo de erros)."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Corpo de erro (4xx/5xx) de qualquer rota (spec.md -> Contrato da API)."""

    error: ErrorDetail
    trace: Trace
