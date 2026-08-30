"""Configurações da aplicação carregadas a partir de variáveis de ambiente.

Cada campo mapeia 1:1 para uma variável de ambiente nomeada a partir dele (em maiúsculas). Os
valores padrão espelham os valores fixados em `spec.md` -> Assumptions & Open Questions. Os três
segredos abaixo não têm valor padrão -- devem ser fornecidos via `.env` ou pela variável de
ambiente do processo.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração centralizada do gateway do orquestrador."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    orchestrator_api_key: str
    openrouter_api_key: str
    openrouter_model: str

    max_react_iterations: int = 5
    mcp_tool_timeout_s: int = 30
    request_timeout_s: int = 120
