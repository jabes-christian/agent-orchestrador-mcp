"""Rota `GET /servers` (MCPO-02 AC3).

Combina `registry.servers()` (estrutura: nome, status, tools) com `policy.is_write()`
(classificação real de escrita) para produzir `tools[].write` correto. `registry.py` não
conhece `tool_policy.yaml` e expõe um placeholder `write: False` para toda tool (ver AD-007,
`STATE.md`); esta rota é o único ponto autorizado a sobrescrever esse placeholder antes de
responder ao cliente.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from orchestrator.mcp_client.policy import ToolPolicy, load_tool_policy
from orchestrator.mcp_client.registry import McpRegistry, ServerInfo

router = APIRouter()


@lru_cache
def get_tool_policy() -> ToolPolicy:
    """Instância única de `ToolPolicy`, sobrescrevível em teste via
    `app.dependency_overrides`."""
    return load_tool_policy()


def get_registry(request: Request) -> McpRegistry:
    """O `McpRegistry` populado pelo `lifespan` da app (`main.py`, T14)."""
    registry: McpRegistry = request.app.state.registry
    return registry


@router.get("/servers")
async def get_servers(
    registry: Annotated[McpRegistry, Depends(get_registry)],
    policy: Annotated[ToolPolicy, Depends(get_tool_policy)],
) -> dict[str, list[ServerInfo]]:
    """Estado atual dos MCP servers descobertos, com `tools[].write` vindo de `policy`."""
    servers = registry.servers()
    for server in servers:
        for tool in server["tools"]:
            tool["write"] = policy.is_write(server["name"], tool["name"])
    return {"servers": servers}
