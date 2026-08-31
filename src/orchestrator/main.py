"""App factory e lifespan do gateway (MCPO-02 AC1, edge case de configuração inválida).

`create_app()` monta a app do FastAPI, registra os exception handlers do catálogo de erros
(T13) e liga um `lifespan` que roda `registry.discover()` (T8) na subida. A partir de T25, o
mesmo `lifespan` também monta o `StateGraph` compilado (T24) a partir do catálogo de tools
recém-descoberto -- `app.state.graph`/`app.state.graph_recursion_limit` ficam prontos antes do
primeiro request, para `POST /tasks` (`api.routes_tasks`) só precisar lê-los de `request.app.state`,
no mesmo padrão que `GET /servers` (T15) já usa para `request.app.state.registry`. Depois da
descoberta, distingue dois motivos possíveis para um server ficar `unhealthy`:

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
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from orchestrator.api.auth import get_settings
from orchestrator.api.errors import register_exception_handlers
from orchestrator.api.routes_health import router as health_router
from orchestrator.api.routes_servers import router as servers_router
from orchestrator.api.routes_tasks import router as tasks_router
from orchestrator.graph.builder import build_graph, compute_recursion_limit
from orchestrator.llm.provider import get_chat_model
from orchestrator.mcp_client.policy import ToolPolicy, load_tool_policy
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


def create_app(
    server_configs: list[ServerConfig] | None = None,
    policy: ToolPolicy | None = None,
    model: BaseChatModel | None = None,
    tools_by_server: dict[str, list[BaseTool]] | None = None,
) -> FastAPI:
    """Monta a app do gateway.

    `server_configs`, `policy`, `model` e `tools_by_server` são injetáveis para teste
    (registry contra um MCP server falso em porta efêmera; `policy`/`model` para exercitar
    `POST /tasks` com um LLM roteirizado em vez do OpenRouter real, conforme design.md Seção 6
    -- "LLM falso via FakeChatModel/respostas roteiradas"; `tools_by_server` para montar o
    grafo com tools falsas -- sem nenhuma conexão MCP real -- no mesmo padrão de dublê que
    `tests/unit/test_builder.py` já usa, necessário para testes de `POST /tasks` que não
    precisam de uma conexão MCP real de ponta a ponta); em produção, `None` faz a app carregar
    `config/servers.yaml`/`config/tool_policy.yaml`/`ChatOpenRouter` normalmente, com as tools
    vindas do `registry` descoberto na subida.
    """
    resolved_configs = server_configs if server_configs is not None else load_server_configs()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry = McpRegistry(resolved_configs)
        await registry.discover()
        await _fail_fast_on_misconfigured_servers(registry, resolved_configs)
        app.state.registry = registry

        settings = get_settings()
        graph = build_graph(
            tools_by_server=(
                tools_by_server if tools_by_server is not None else registry.tools_by_server()
            ),
            policy=policy if policy is not None else load_tool_policy(),
            model=model if model is not None else get_chat_model(settings),
            max_iterations=settings.max_react_iterations,
            tool_timeout_s=settings.mcp_tool_timeout_s,
        )
        app.state.graph = graph
        app.state.graph_recursion_limit = compute_recursion_limit(settings.max_react_iterations)
        yield

    app = FastAPI(title="agent-orchestrator-mcp", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(servers_router)
    app.include_router(tasks_router)
    app.include_router(health_router)
    return app


app = create_app()
