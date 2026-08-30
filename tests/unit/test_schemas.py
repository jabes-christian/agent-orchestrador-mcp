"""Testes unitários de orchestrator.api.schemas (MCPO-01, MCPO-04, edge case INVALID_TASK)."""

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas import (
    ErrorDetail,
    ErrorResponse,
    TaskRequest,
    TaskResponse,
    Trace,
    TraceStep,
)

SAMPLE_TRACE = {
    "request_id": "11111111-1111-1111-1111-111111111111",
    "iterations": 1,
    "steps": [
        {
            "step": 1,
            "server": "filesystem",
            "tool": "read_file",
            "arguments": {"path": "a.txt"},
            "duration_ms": 10,
            "attempt": 1,
            "status": "success",
        }
    ],
    "used_tools": ["filesystem.read_file"],
    "finish_reason": "completed",
    "duration_ms": 15,
}


def test_task_request_accepts_a_valid_task():
    request = TaskRequest(task="liste os arquivos do diretorio de trabalho")

    assert request.task == "liste os arquivos do diretorio de trabalho"


def test_task_request_rejects_empty_task():
    with pytest.raises(ValidationError):
        TaskRequest(task="")


def test_task_request_rejects_whitespace_only_task():
    with pytest.raises(ValidationError):
        TaskRequest(task="   \n\t  ")


def test_task_request_rejects_task_above_4000_chars():
    with pytest.raises(ValidationError):
        TaskRequest(task="a" * 4001)


def test_task_request_accepts_task_at_exactly_4000_chars():
    request = TaskRequest(task="a" * 4000)

    assert len(request.task) == 4000


def test_task_request_rejects_missing_task_field():
    with pytest.raises(ValidationError):
        TaskRequest()


def test_trace_round_trips_the_trace_recorder_contract_fields():
    trace = Trace(**SAMPLE_TRACE)

    assert trace.model_dump() == SAMPLE_TRACE


def test_task_response_serializes_result_and_trace():
    response = TaskResponse(result="pronto", trace=Trace(**SAMPLE_TRACE))

    payload = response.model_dump()

    assert payload["result"] == "pronto"
    assert payload["trace"]["finish_reason"] == "completed"


def test_error_response_serializes_code_message_and_trace():
    error_trace = {**SAMPLE_TRACE, "finish_reason": "error"}

    response = ErrorResponse(
        error=ErrorDetail(code="UNAUTHORIZED", message="chave invalida"),
        trace=Trace(**error_trace),
    )
    payload = response.model_dump()

    assert payload["error"] == {"code": "UNAUTHORIZED", "message": "chave invalida"}
    assert payload["trace"]["finish_reason"] == "error"


def test_trace_step_requires_all_contract_fields():
    with pytest.raises(ValidationError):
        TraceStep(step=1, server="filesystem", tool="read_file")
