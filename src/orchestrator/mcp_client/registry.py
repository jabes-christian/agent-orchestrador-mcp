"""Registry: lê config/servers.yaml, descobre as ferramentas de cada servidor MCP e expõe o
status de saúde para GET /servers (MCPO-02 AC1/AC2/AC3).

Este módulo e `config/servers.yaml` são o único lugar autorizado a nomear um servidor MCP
(AD-005, STATE.md) -- `graph/` nunca importa este módulo em busca de um servidor/ferramenta
específico, apenas consome a lista de ferramentas já resolvida.
"""

import asyncio
from pathlib import Path
from typing import Literal, TypedDict

import yaml
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel

DEFAULT_SERVERS_CONFIG_PATH = Path("config/servers.yaml")


class ServerConfig(BaseModel):
    """Uma entrada de `config/servers.yaml`."""

    name: str
    transport: str
    url: str
    timeout: float
    enabled: bool = True


class ToolInfo(TypedDict):
    """Uma entrada de `ServerInfo.tools` (spec.md -> `GET /servers`)."""

    name: str
    description: str
    # NOTA: a classificação de escrita vive em `mcp_client.policy` (T9/T10), do qual este módulo
    # não depende (ver tasks.md T8 "Depends on"). Aqui o valor é sempre False; `GET /servers`
    # (task T15, ainda não implementada) é o único lugar autorizado a sobrepor o valor real vindo
    # de `policy.is_write()` antes de responder ao cliente.
    write: bool


class ServerInfo(TypedDict):
    """Uma entrada da resposta de `GET /servers` (spec.md -> Contrato da API)."""

    name: str
    status: Literal["healthy", "unhealthy"]
    tools: list[ToolInfo]


def load_server_configs(path: Path = DEFAULT_SERVERS_CONFIG_PATH) -> list[ServerConfig]:
    """Faz o parse de `config/servers.yaml` para uma lista de `ServerConfig`."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [ServerConfig(**entry) for entry in raw.get("servers", [])]


class McpRegistry:
    """Descobre os servidores MCP declarados em `config/servers.yaml` e rastreia sua
    saúde/ferramentas."""

    def __init__(self, server_configs: list[ServerConfig]) -> None:
        self._server_configs = server_configs
        self._client = MultiServerMCPClient(
            {
                cfg.name: {
                    "transport": "streamable_http",
                    "url": cfg.url,
                    "timeout": cfg.timeout,
                    # `sse_read_timeout` NÃO é suficiente sozinho (ver AD-014, STATE.md): contra
                    # um backend Streamable HTTP real que entrega os headers (200 OK, sessão
                    # aberta) mas nunca escreve o primeiro evento SSE, o SDK `mcp` subjacente não
                    # aplica esse timeout de fato -- a leitura trava indefinidamente. Mantido aqui
                    # como defesa em profundidade (funciona para outros modos de falha, ex.:
                    # stream que já começou a entregar dados e depois para), mas o enforcement
                    # real vem do `asyncio.wait_for` em `discover()`, abaixo.
                    "sse_read_timeout": cfg.timeout,
                }
                for cfg in server_configs
                if cfg.enabled
            }
        )
        self._tools_by_server: dict[str, list[BaseTool]] = {}
        self._healthy: dict[str, bool] = {cfg.name: False for cfg in server_configs}

    async def discover(self) -> None:
        """Conecta a cada servidor habilitado declarado na configuração.

        Uma falha em um servidor (conexão recusada, timeout ou qualquer outro erro de transporte)
        fica isolada àquele servidor -- ele é marcado como unhealthy e a descoberta continua com
        os demais (MCPO-02 AC2). Um servidor com `enabled: false` nunca é contatado e permanece
        unhealthy, com lista de ferramentas vazia.

        `get_tools()` é envolvido em `asyncio.wait_for(..., timeout=cfg.timeout)` -- não confiar
        só no `sse_read_timeout` do `MultiServerMCPClient` (ver AD-014, STATE.md). Encontrado
        validando `docker compose up -d` de ponta a ponta contra o MCP server `filesystem` real
        (T33): o handshake abre a sessão Streamable HTTP (200 OK, `mcp-session-id` presente) mas
        o SDK `mcp` subjacente não interrompe a leitura sozinho se o primeiro evento SSE nunca
        chegar -- sem este `wait_for`, `discover()` trava indefinidamente e o gateway nunca sai
        de "Waiting for application startup", nenhum outro server chega a ser tentado.
        """
        for cfg in self._server_configs:
            if not cfg.enabled:
                continue
            try:
                tools = await asyncio.wait_for(
                    self._client.get_tools(server_name=cfg.name), timeout=cfg.timeout
                )
            except Exception:
                self._healthy[cfg.name] = False
                continue
            self._tools_by_server[cfg.name] = tools
            self._healthy[cfg.name] = True

    def servers(self) -> list[ServerInfo]:
        """Estado atual da descoberta, para `GET /servers` (MCPO-02 AC3)."""
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
        """Todas as ferramentas descobertas em todos os servidores saudáveis, para o nó
        `prepare` do grafo."""
        all_tools: list[BaseTool] = []
        for tools in self._tools_by_server.values():
            all_tools.extend(tools)
        return all_tools

    def tools_by_server(self) -> dict[str, list[BaseTool]]:
        """Ferramentas descobertas, agrupadas por servidor -- para `graph/builder.py` (T24)
        montar o catálogo do prompt e o mapeamento tool->server sem depender de casar por nome
        duas estruturas moldadas diferente (`get_tools()` achata tudo, perdendo a atribuição de
        servidor; `servers()` tem a atribuição mas não os objetos `BaseTool` reais)."""
        return dict(self._tools_by_server)
