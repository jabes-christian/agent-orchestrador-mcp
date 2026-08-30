"""Testes unitários de orchestrator.settings.Settings (ver spec.md -> Assumptions & Open
Questions)."""

import pytest
from pydantic import ValidationError

from orchestrator.settings import Settings

REQUIRED_ENV = {
    "ORCHESTRATOR_API_KEY": "test-api-key",
    "OPENROUTER_API_KEY": "test-openrouter-key",
    "OPENROUTER_MODEL": "test/model",
}

OVERRIDABLE_ENV = ("MAX_REACT_ITERATIONS", "MCP_TOOL_TIMEOUT_S", "REQUEST_TIMEOUT_S")


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Executa cada teste sem arquivo .env em disco e com um estado limpo para toda variável de
    ambiente relevante."""
    monkeypatch.chdir(tmp_path)
    for key in (*REQUIRED_ENV, *OVERRIDABLE_ENV):
        monkeypatch.delenv(key, raising=False)


def _set_required_env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def test_defaults_apply_without_env_overrides(monkeypatch):
    _set_required_env(monkeypatch)

    settings = Settings()

    assert settings.max_react_iterations == 5
    assert settings.mcp_tool_timeout_s == 30
    assert settings.request_timeout_s == 120


def test_env_overrides_defaults(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("MAX_REACT_ITERATIONS", "9")
    monkeypatch.setenv("MCP_TOOL_TIMEOUT_S", "45")
    monkeypatch.setenv("REQUEST_TIMEOUT_S", "200")

    settings = Settings()

    assert settings.max_react_iterations == 9
    assert settings.mcp_tool_timeout_s == 45
    assert settings.request_timeout_s == 200


def test_required_secrets_are_read_from_env(monkeypatch):
    _set_required_env(monkeypatch)

    settings = Settings()

    assert settings.orchestrator_api_key == "test-api-key"
    assert settings.openrouter_api_key == "test-openrouter-key"
    assert settings.openrouter_model == "test/model"


def test_missing_required_secret_raises(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    # ORCHESTRATOR_API_KEY deixado propositalmente sem valor.

    with pytest.raises(ValidationError):
        Settings()
