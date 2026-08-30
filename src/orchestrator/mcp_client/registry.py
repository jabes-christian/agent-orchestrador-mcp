"""Registry: reads config/servers.yaml, discovers each MCP server's tools and exposes health
status for GET /servers (MCPO-02 AC1/AC2/AC3).

This module and `config/servers.yaml` are the only place authorized to name an MCP server
(AD-005, STATE.md) -- `graph/` never imports this module for a specific server/tool name, only
consumes the already-resolved tool list.
"""

from pathlib import Path
from typing import Literal, TypedDict

import yaml
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel

DEFAULT_SERVERS_CONFIG_PATH = Path("config/servers.yaml")


class ServerConfig(BaseModel):
    """One entry of `config/servers.yaml`."""

    name: str
    transport: str
    url: str
    timeout: float
    enabled: bool = True


class ToolInfo(TypedDict):
    """One entry of `ServerInfo.tools` (spec.md -> `GET /servers`)."""

    name: str
    description: str
    # NOTE: write-classification lives in `mcp_client.policy` (T9/T10), which this module does
    # not depend on (see tasks.md T8 "Depends on"). Defaults to False here; the route/composition
    # layer that has both the registry and the policy loaded is responsible for overlaying the
    # real value before this reaches a client.
    write: bool


class ServerInfo(TypedDict):
    """One entry of the `GET /servers` response (spec.md -> Contrato da API)."""

    name: str
    status: Literal["healthy", "unhealthy"]
    tools: list[ToolInfo]


def load_server_configs(path: Path = DEFAULT_SERVERS_CONFIG_PATH) -> list[ServerConfig]:
    """Parse `config/servers.yaml` into a list of `ServerConfig`."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [ServerConfig(**entry) for entry in raw.get("servers", [])]


class McpRegistry:
    """Discovers MCP servers declared in `config/servers.yaml` and tracks their health/tools."""

    def __init__(self, server_configs: list[ServerConfig]) -> None:
        self._server_configs = server_configs
        self._client = MultiServerMCPClient(
            {
                cfg.name: {
                    "transport": "streamable_http",
                    "url": cfg.url,
                    "timeout": cfg.timeout,
                    # The underlying MCP client defaults the *read* timeout to 300s regardless
                    # of `timeout` above (which only bounds connect/write/pool) -- without this,
                    # a server that accepts the connection but never answers would hang for 5
                    # minutes instead of respecting the per-server `timeout` from servers.yaml.
                    "sse_read_timeout": cfg.timeout,
                }
                for cfg in server_configs
                if cfg.enabled
            }
        )
        self._tools_by_server: dict[str, list[BaseTool]] = {}
        self._healthy: dict[str, bool] = {cfg.name: False for cfg in server_configs}

    async def discover(self) -> None:
        """Connect to every enabled server declared in config.

        A failure on one server (refused connection, timeout, or any other transport error) is
        isolated to that server -- it is marked unhealthy and discovery continues with the rest
        (MCPO-02 AC2). A server with `enabled: false` is never contacted and stays unhealthy with
        an empty tool list.
        """
        for cfg in self._server_configs:
            if not cfg.enabled:
                continue
            try:
                tools = await self._client.get_tools(server_name=cfg.name)
            except Exception:
                self._healthy[cfg.name] = False
                continue
            self._tools_by_server[cfg.name] = tools
            self._healthy[cfg.name] = True

    def servers(self) -> list[ServerInfo]:
        """Current discovery state, for `GET /servers` (MCPO-02 AC3)."""
        result: list[ServerInfo] = []
        for cfg in self._server_configs:
            tools = self._tools_by_server.get(cfg.name, [])
            result.append(
                {
                    "name": cfg.name,
                    "status": "healthy" if self._healthy.get(cfg.name) else "unhealthy",
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "write": False,
                        }
                        for tool in tools
                    ],
                }
            )
        return result

    async def get_tools(self) -> list[BaseTool]:
        """All tools discovered across every healthy server, for the `prepare` graph node."""
        all_tools: list[BaseTool] = []
        for tools in self._tools_by_server.values():
            all_tools.extend(tools)
        return all_tools
