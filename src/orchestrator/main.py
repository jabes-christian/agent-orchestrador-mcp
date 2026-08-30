"""App factory e lifespan do gateway (MCPO-02 AC1, edge case de configuração inválida).

`create_app()` monta a app do FastAPI, registra os exception handlers do catálogo de erros
(T13) e liga um `lifespan` que roda `registry.discover()` (T8) na subida. Depois da descoberta,
distingue dois motivos possíveis para um server ficar `unhealthy`:

- **Fora do ar / lento** (conexão recusada, timeout): o host declarado resolve por DNS
  normalmente -- é esperado que aconteça em produção (MCPO-02 AC2) e não impede a subida.
- **Misconfigurado**: o host declarado não resolve por DNS -- sinal de que nenhum serviço com
  esse nome existe na rede do compose (ex.: entrada em `servers.yaml` sem o serviço
  correspondente em `docker-compose.yml`). Este é o edge case da spec ("servidor declarado...
  não existe... falhar a inicialização") e aborta a subida do gateway com log explícito.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI

from orchestrator.api.errors import register_exception_handlers
from orchestrator.api.routes_servers import router as servers_router
from orchestrator.mcp_client.registry import McpRegistry, ServerConfig, load_server_configs

logger = logging.getLogger(__name__)


class ServerMisconfiguredError(RuntimeError):
    """Um server declarado em `config/servers.yaml` não resolve por DNS -- indício de que não
    existe um serviço correspondente no docker-compose.yml, distinto de um server que apenas
    está fora do ar (ver MCPO-02 AC2, que continua tolerando esse segundo caso)."""


async def _fails_dns_resolution(url: str) -> bool:
    """True se o host declarado em `url` não resolve por DNS.

    Conexão recusada e timeout resolvem por DNS normalmente (o host existe, só não responde
    ainda) -- só a falha de resolução em si indica que nenhum serviço com esse nome existe na
    rede do compose.
    """
    hostname = urlparse(url).hostname
    if hostname is None:
        return True
    loop = asyncio.get_running_loop()
    try:
        await loop.getaddrinfo(hostname, None)
    except OSError:
        return True
    return False


async def _fail_fast_on_misconfigured_servers(
    registry: McpRegistry, server_configs: list[ServerConfig]
) -> None:
    """Depois de `registry.discover()`, aborta a subida se algum server `unhealthy` for, na
    verdade, um erro de configuração (host inexistente), em vez de apenas fora do ar."""
    enabled_by_name = {cfg.name: cfg for cfg in server_configs if cfg.enabled}
    for server in registry.servers():
        cfg = enabled_by_name.get(server["name"])
        if cfg is None or server["status"] != "unhealthy":
            continue
        if await _fails_dns_resolution(cfg.url):
            message = (
                f"servidor MCP '{cfg.name}' declarado em servers.yaml nao resolve "
                f"('{cfg.url}') -- provavel servico ausente no docker-compose.yml"
            )
            logger.error(message)
            raise ServerMisconfiguredError(message)


def create_app(server_configs: list[ServerConfig] | None = None) -> FastAPI:
    """Monta a app do gateway.

    `server_configs` é injetável para teste (registry contra um MCP server falso em porta
    efêmera); em produção, `None` faz a app carregar `config/servers.yaml` normalmente.
    """
    resolved_configs = server_configs if server_configs is not None else load_server_configs()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry = McpRegistry(resolved_configs)
        await registry.discover()
        await _fail_fast_on_misconfigured_servers(registry, resolved_configs)
        app.state.registry = registry
        yield

    app = FastAPI(title="agent-orchestrator-mcp", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(servers_router)
    return app


app = create_app()
