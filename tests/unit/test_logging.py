"""Unit tests for orchestrator.observability.logging (MCPO-04 AC3)."""

import json
import logging

from orchestrator.observability.logging import (
    JsonFormatter,
    bind_request_id,
    configure_logging,
    get_logger,
    reset_request_id,
)


def _make_record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_format_emits_valid_json_with_required_fields():
    formatter = JsonFormatter()
    record = _make_record("hello")

    line = formatter.format(record)
    payload = json.loads(line)  # raises if not valid JSON

    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert "timestamp" in payload
    assert "request_id" in payload


def test_request_id_present_when_bound():
    formatter = JsonFormatter()
    token = bind_request_id("req-123")
    try:
        payload = json.loads(formatter.format(_make_record("inside request")))
    finally:
        reset_request_id(token)

    assert payload["request_id"] == "req-123"


def test_request_id_does_not_leak_across_bindings():
    formatter = JsonFormatter()

    token_a = bind_request_id("req-a")
    payload_a = json.loads(formatter.format(_make_record("a")))
    reset_request_id(token_a)

    token_b = bind_request_id("req-b")
    payload_b = json.loads(formatter.format(_make_record("b")))
    reset_request_id(token_b)

    assert payload_a["request_id"] == "req-a"
    assert payload_b["request_id"] == "req-b"


def test_configure_logging_emits_json_lines_with_request_id(capsys):
    configure_logging()
    logger = get_logger("orchestrator.test")

    token = bind_request_id("req-integration")
    try:
        logger.info("processing task")
    finally:
        reset_request_id(token)

    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    payload = json.loads(line)

    assert payload["request_id"] == "req-integration"
    assert payload["message"] == "processing task"
    assert payload["level"] == "INFO"
    assert "timestamp" in payload
