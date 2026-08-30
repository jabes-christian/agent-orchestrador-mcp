"""Application settings loaded from environment variables.

Every field maps 1:1 to an environment variable named after it (upper-cased). Defaults mirror the
values fixed in `spec.md` -> Assumptions & Open Questions. The three secrets below have no default
-- they must be supplied via `.env` or the process environment.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for the orchestrator gateway."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    orchestrator_api_key: str
    openrouter_api_key: str
    openrouter_model: str

    max_react_iterations: int = 5
    mcp_tool_timeout_s: int = 30
    request_timeout_s: int = 120
