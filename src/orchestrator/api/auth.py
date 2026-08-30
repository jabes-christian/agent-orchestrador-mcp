"""Autenticação por API key (MCPO-06).

`require_api_key` é uma dependency do FastAPI: qualquer rota que a declare exige o header
`X-API-Key` presente e igual ao valor configurado em `ORCHESTRATOR_API_KEY` (Settings, T3).
`UnauthorizedError` estende `McpClientError` (T7) só para reaproveitar o mesmo mecanismo de
`error_code`/`http_status` que os exception handlers de `api.errors` (T13) já sabem traduzir --
nenhum handler específico de autenticação precisa existir.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header

from orchestrator.mcp_client.exceptions import McpClientError
from orchestrator.settings import Settings


class UnauthorizedError(McpClientError):
    """`X-API-Key` ausente ou incorreto (spec.md -> catálogo de erros)."""

    error_code = "UNAUTHORIZED"
    http_status = 401


@lru_cache
def get_settings() -> Settings:
    """Instância única de `Settings`, sobrescrevível em teste via
    `app.dependency_overrides`."""
    # pydantic-settings le os campos obrigatorios do .env/ambiente em runtime.
    return Settings()  # type: ignore[call-arg]


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Levanta `UnauthorizedError` se `x_api_key` estiver ausente ou não bater com a chave
    configurada."""
    if x_api_key is None or x_api_key != settings.orchestrator_api_key:
        raise UnauthorizedError("X-API-Key ausente ou invalida")
