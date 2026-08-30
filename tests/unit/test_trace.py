"""Testes unitários de orchestrator.observability.trace.TraceRecorder (MCPO-04 AC1/AC2)."""

import json
import time
import uuid

from orchestrator.observability.trace import TraceRecorder


def test_steps_accumulate_in_order():
    recorder = TraceRecorder()

    recorder.record_step("filesystem", "read_file", {"path": "a.txt"}, 10, 1, "success")
    recorder.record_step("github", "get_file", {"repo": "x"}, 20, 1, "success")

    steps = recorder.steps
    assert [s["step"] for s in steps] == [1, 2]
    assert steps[0]["server"] == "filesystem"
    assert steps[0]["tool"] == "read_file"
    assert steps[0]["arguments"] == {"path": "a.txt"}
    assert steps[0]["duration_ms"] == 10
    assert steps[0]["attempt"] == 1
    assert steps[0]["status"] == "success"
    assert steps[1]["server"] == "github"
    assert steps[1]["tool"] == "get_file"


def test_used_tools_dedupes_repeated_successful_calls():
    recorder = TraceRecorder()

    recorder.record_step("filesystem", "read_file", {"path": "a.txt"}, 10, 1, "success")
    recorder.record_step("filesystem", "read_file", {"path": "b.txt"}, 12, 1, "success")

    assert recorder.used_tools == ["filesystem.read_file"]


def test_used_tools_excludes_blocked_and_failed_steps():
    recorder = TraceRecorder()

    recorder.record_step("filesystem", "write_file", {"path": "a.txt"}, 0, 1, "blocked")
    recorder.record_step("github", "get_file", {"repo": "x"}, 30000, 2, "failure")
    recorder.record_step("filesystem", "read_file", {"path": "a.txt"}, 10, 1, "success")

    assert recorder.used_tools == ["filesystem.read_file"]


def test_duration_ms_measures_elapsed_time_since_creation():
    recorder = TraceRecorder()
    time.sleep(0.01)

    assert recorder.duration_ms >= 10


def test_to_dict_is_json_serializable_with_contract_fields():
    recorder = TraceRecorder(request_id="req-123")
    recorder.iterations = 2
    recorder.record_step("filesystem", "read_file", {"path": "a.txt"}, 10, 1, "success")

    trace = recorder.to_dict(finish_reason="completed")
    serialized = json.dumps(trace)  # levanta exceção se não for serializável em JSON
    payload = json.loads(serialized)

    assert payload["request_id"] == "req-123"
    assert payload["iterations"] == 2
    assert payload["used_tools"] == ["filesystem.read_file"]
    assert payload["finish_reason"] == "completed"
    assert isinstance(payload["duration_ms"], int)
    assert len(payload["steps"]) == 1


def test_request_id_defaults_to_a_generated_uuid():
    recorder = TraceRecorder()

    uuid.UUID(recorder.request_id)  # levanta ValueError se não for uma string UUID válida
