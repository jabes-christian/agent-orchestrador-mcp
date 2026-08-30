"""TraceRecorder: accumulates the audit trail for one request and renders it per the API
contract (MCPO-04 AC1/AC2)."""

import time
import uuid
from typing import Literal, TypedDict


class TraceStep(TypedDict):
    """One entry of `trace.steps` (spec.md -> Contrato da API)."""

    step: int
    server: str
    tool: str
    arguments: dict[str, object]
    duration_ms: int
    attempt: int
    status: Literal["success", "failure", "blocked"]


class TraceRecorder:
    """Accumulates `trace.steps`/`trace.used_tools` for one request and renders the final
    `trace` dict (spec.md -> Contrato da API)."""

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
        """Append one step to the trace, in call order."""
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
        """Unique `server.tool` identifiers for steps that actually succeeded.

        A `blocked` step never reached the MCP server; a `failure` step produced no usable
        result -- neither counts as a tool the task actually used to reach its answer.
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
        """Render the final `trace` dict, in the exact shape of the API contract."""
        return {
            "request_id": self.request_id,
            "iterations": self.iterations,
            "steps": self.steps,
            "used_tools": self.used_tools,
            "finish_reason": finish_reason,
            "duration_ms": self.duration_ms,
        }
