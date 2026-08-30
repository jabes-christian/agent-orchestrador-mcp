"""Logging JSON estruturado com correlação por request_id (MCPO-04 AC3).

Toda linha de log emitida via `configure_logging()` é um único objeto JSON contendo ao menos
`request_id`, `timestamp`, `level` e `message`. O `request_id` é lido de uma
`contextvars.ContextVar`, então os pontos de chamada nunca precisam passá-lo explicitamente --
`bind_request_id()` o define uma vez por requisição e todo registro de log emitido enquanto esse
contexto está ativo o captura automaticamente.
"""

import contextvars
import json
import logging
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class JsonFormatter(logging.Formatter):
    """Renderiza um `LogRecord` como uma linha JSON, correlacionada com o `request_id` atual."""

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
    """Instala o formatter JSON no logger raiz. Chame uma única vez, na inicialização do
    processo."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger padrão da stdlib; a formatação/JSON é tratada pelo handler instalado
    acima."""
    return logging.getLogger(name)


def bind_request_id(request_id: str) -> contextvars.Token[str | None]:
    """Vincula `request_id` ao contexto atual. Chame `reset_request_id` com o token retornado
    quando a requisição terminar."""
    return request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    """Desfaz uma chamada a `bind_request_id`, restaurando o valor anterior do contexto."""
    request_id_var.reset(token)
