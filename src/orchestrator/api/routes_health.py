"""Rota `GET /health` (MCPO-11, P3).

Agrega o próprio estado do gateway com o estado de descoberta de cada MCP server já mantido
por `registry.servers()` (T8) -- reaproveita só nome/status de cada `ServerInfo`, sem a lista
de tools (fora do escopo do health, já coberta por `GET /servers`, T15).
"""

from typing import Annotated, Literal, TypedDict

from fastapi import APIRouter, Depends, Request

from orchestrator.mcp_client.registry import McpRegistry

router = APIRouter()


class ServerHealth(TypedDict):
    """Status individual de um MCP server na resposta de `GET /health`."""

    name: str
    status: Literal["healthy", "unhealthy"]


class HealthResponse(TypedDict):
    """Corpo de `GET /health` (spec.md -> Contrato da API, MCPO-11 AC1)."""

    status: Literal["ok", "degraded"]
    servers: list[ServerHealth]


def get_registry(request: Request) -> McpRegistry:
    """O `McpRegistry` populado pelo `lifespan` da app (`main.py`, T14)."""
    registry: McpRegistry = request.app.state.registry
    return registry


@router.get("/health")
async def get_health(registry: Annotated[McpRegistry, Depends(get_registry)]) -> HealthResponse:
    """`status` agregado é `"ok"` só quando todo MCP server declarado está `healthy`; um único
    server `unhealthy` já basta para `"degraded"`, sem derrubar a rota (MCPO-11 AC1)."""
    servers: list[ServerHealth] = [
        {"name": server["name"], "status": server["status"]} for server in registry.servers()
    ]
    aggregate: Literal["ok", "degraded"] = (
        "ok" if all(server["status"] == "healthy" for server in servers) else "degraded"
    )
    return {"status": aggregate, "servers": servers}
