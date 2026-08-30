"""Testes unitários de orchestrator.api.auth.require_api_key (MCPO-06)."""

import pytest

from orchestrator.api.auth import UnauthorizedError, require_api_key
from orchestrator.settings import Settings

SETTINGS = Settings(
    orchestrator_api_key="correct-key",
    openrouter_api_key="test-openrouter-key",
    openrouter_model="test/model",
)


def test_missing_header_is_rejected():
    with pytest.raises(UnauthorizedError):
        require_api_key(x_api_key=None, settings=SETTINGS)


def test_incorrect_header_is_rejected():
    with pytest.raises(UnauthorizedError):
        require_api_key(x_api_key="wrong-key", settings=SETTINGS)


def test_correct_header_passes_without_raising():
    require_api_key(x_api_key="correct-key", settings=SETTINGS)


def test_unauthorized_error_carries_the_catalog_code_and_http_status():
    error = UnauthorizedError("X-API-Key ausente ou invalida")

    assert error.error_code == "UNAUTHORIZED"
    assert error.http_status == 401
