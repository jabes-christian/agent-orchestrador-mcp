"""TraceRecorder: acumula a trilha de auditoria de uma requisição e a renderiza conforme o
contrato da API (MCPO-04 AC1/AC2)."""

import time
import uuid
from typing import Literal, TypedDict


class TraceStep(TypedDict):
    """Uma entrada de `trace.steps` (spec.md -> Contrato da API)."""

    step: int
    server: str
    tool: str
    arguments: dict[str, object]
    duration_ms: int
    attempt: int
    status: Literal["success", "failure", "blocked"]


class TraceRecorder:
    """Acumula `trace.steps`/`trace.used_tools` de uma requisição e renderiza o dict final
    `trace` (spec.md -> Contrato da API)."""

    def __init__(self, request_id: str | None = None) -> None:
        self.request_id = request_id or str(uuid.uuid4())
        self.iterations = 0
        self._steps: list[TraceStep] = []
        self._started_at = time.monotonic()

    def record_step(
        self,
        server: str,
        tool: str,
        arguments: dict[str, object],
        duration_ms: int,
        attempt: int,
        status: Literal["success", "failure", "blocked"],
    ) -> None:
        """Adiciona um passo ao trace, na ordem em que as chamadas ocorrem."""
        self._steps.append(
            {
                "step": len(self._steps) + 1,
                "server": server,
                "tool": tool,
                "arguments": arguments,
                "duration_ms": duration_ms,
                "attempt": attempt,
                "status": status,
            }
        )

    @property
    def steps(self) -> list[TraceStep]:
        return list(self._steps)

    @property
    def used_tools(self) -> list[str]:
        """Identificadores únicos `server.tool` dos passos que de fato tiveram sucesso.

        Um passo `blocked` nunca chegou a alcançar o servidor MCP; um passo `failure` não
        produziu resultado utilizável -- nenhum dos dois conta como uma ferramenta que a tarefa
        efetivamente usou para chegar à resposta.
        """
        seen: list[str] = []
        for step in self._steps:
            if step["status"] != "success":
                continue
            identifier = f"{step['server']}.{step['tool']}"
            if identifier not in seen:
                seen.append(identifier)
        return seen

    @property
    def duration_ms(self) -> int:
        return int((time.monotonic() - self._started_at) * 1000)

    def to_dict(self, finish_reason: str) -> dict[str, object]:
        """Renderiza o dict final `trace`, exatamente no formato do contrato da API."""
        return {
            "request_id": self.request_id,
            "iterations": self.iterations,
            "steps": self.steps,
            "used_tools": self.used_tools,
            "finish_reason": finish_reason,
            "duration_ms": self.duration_ms,
        }
