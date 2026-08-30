"""Structured JSON logging with request_id correlation (MCPO-04 AC3).

Every log line emitted through `configure_logging()` is a single JSON object with at least
`request_id`, `timestamp`, `level` and `message`. `request_id` is read from a
`contextvars.ContextVar` so call sites never have to pass it explicitly -- `bind_request_id()`
sets it once per request and every log record emitted while that context is active picks it up
automatically.
"""

import contextvars
import json
import logging
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class JsonFormatter(logging.Formatter):
    """Renders a `LogRecord` as one JSON line, correlated with the current `request_id`."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger. Call once at process startup."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib logger; formatting/JSON is handled by the handler installed above."""
    return logging.getLogger(name)


def bind_request_id(request_id: str) -> contextvars.Token[str | None]:
    """Bind `request_id` to the current context. Call `reset_request_id` with the returned token
    when the request finishes."""
    return request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    """Undo a `bind_request_id` call, restoring the previous context value."""
    request_id_var.reset(token)
