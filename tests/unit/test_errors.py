"""Testes unitários de orchestrator.api.errors (MCPO-05 AC6, MCPO-04 AC1)."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from orchestrator.api.auth import UnauthorizedError
from orchestrator.api.errors import register_exception_handlers
from orchestrator.api.schemas import TaskRequest
from orchestrator.mcp_client.exceptions import (
    McpClientError,
    ServerUnavailableError,
    ToolNotAllowedError,
    ToolTimeoutError,
)
from orchestrator.observability.trace import TraceRecorder


class _FakeLlmProviderError(McpClientError):
    """Dublê local: prova que o handler genérico de `McpClientError` também cobre
    `LLM_PROVIDER_ERROR`, cuja subclasse real só é definida em `llm.provider` (T17) --
    o handler não conhece essa classe especificamente, só a hierarquia."""

    error_code = "LLM_PROVIDER_ERROR"
    http_status = 502


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/task-body")
    async def _task_body(payload: TaskRequest) -> dict[str, str]:
        return {"task": payload.task}

    @app.get("/boom/unauthorized")
    async def _unauthorized() -> None:
        raise UnauthorizedError("X-API-Key ausente ou invalida")

    @app.get("/boom/server-unavailable")
    async def _server_unavailable() -> None:
        raise ServerUnavailableError("filesystem indisponivel")

    @app.get("/boom/tool-timeout")
    async def _tool_timeout() -> None:
        raise ToolTimeoutError("timeout apos retry")

    @app.get("/boom/tool-not-allowed")
    async def _tool_not_allowed() -> None:
        raise ToolNotAllowedError("write_file fora da allowlist")

    @app.get("/boom/llm-provider")
    async def _llm_provider() -> None:
        raise _FakeLlmProviderError("openrouter indisponivel")

    @app.get("/boom/request-timeout")
    async def _request_timeout() -> None:
        raise TimeoutError("excedeu REQUEST_TIMEOUT_S")

    @app.get("/boom/internal")
    async def _internal() -> None:
        raise ValueError("algo nao classificado quebrou")

    @app.get("/boom/with-partial-trace")
    async def _with_partial_trace(request: Request) -> None:
        recorder = TraceRecorder(request_id="req-partial")
        recorder.record_step("filesystem", "read_file", {"path": "a.txt"}, 5, 1, "success")
        request.state.trace_recorder = recorder
        raise ServerUnavailableError("github indisponivel")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


def test_invalid_task_body_maps_to_422(client: TestClient) -> None:
    response = client.post("/task-body", json={"task": ""})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_TASK"
    assert "trace" in body


def test_missing_task_field_maps_to_invalid_task(client: TestClient) -> None:
    response = client.post("/task-body", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TASK"


def test_malformed_json_body_maps_to_invalid_task(client: TestClient) -> None:
    response = client.post(
        "/task-body", content=b"{not-json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TASK"


@pytest.mark.parametrize(
    ("path", "expected_status", "expected_code"),
    [
        ("/boom/unauthorized", 401, "UNAUTHORIZED"),
        ("/boom/server-unavailable", 502, "MCP_SERVER_UNAVAILABLE"),
        ("/boom/tool-timeout", 504, "MCP_TOOL_TIMEOUT"),
        ("/boom/tool-not-allowed", 403, "TOOL_NOT_ALLOWED"),
        ("/boom/llm-provider", 502, "LLM_PROVIDER_ERROR"),
        ("/boom/request-timeout", 504, "REQUEST_TIMEOUT"),
        ("/boom/internal", 500, "INTERNAL_ERROR"),
    ],
)
def test_each_cataloged_error_maps_to_its_http_status_and_code(
    client: TestClient, path: str, expected_status: int, expected_code: str
) -> None:
    response = client.get(path)

    assert response.status_code == expected_status
    body = response.json()
    assert body["error"]["code"] == expected_code
    assert "trace" in body


def test_error_response_always_carries_a_parseable_trace_even_without_a_recorder(
    client: TestClient,
) -> None:
    response = client.get("/boom/server-unavailable")

    trace = response.json()["trace"]
    assert trace["finish_reason"] == "error"
    assert trace["steps"] == []
    assert isinstance(trace["request_id"], str)


def test_error_response_uses_the_partial_trace_already_accumulated_on_the_request(
    client: TestClient,
) -> None:
    response = client.get("/boom/with-partial-trace")

    trace = response.json()["trace"]
    assert trace["request_id"] == "req-partial"
    assert trace["finish_reason"] == "error"
    assert len(trace["steps"]) == 1
    assert trace["steps"][0]["tool"] == "read_file"
