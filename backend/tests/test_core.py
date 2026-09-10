"""Smoke tests for core config and exceptions (Phase 1)."""

from app.core.config import Settings, get_settings
from app.core.exceptions import UnsupportedFileTypeError


def test_settings_load_without_secrets():
    settings = get_settings()
    assert settings.max_pages == 3
    assert settings.llm_provider in {"openai", "gemini", "anthropic"}


def test_unsupported_file_error_envelope():
    err = UnsupportedFileTypeError()
    body = err.to_error_body()
    assert body["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert err.http_status == 400
    assert "stack" not in str(body).lower()


def test_settings_active_key_does_not_require_env():
    settings = Settings(openai_api_key="", llm_provider="openai")
    assert settings.active_llm_api_key() == ""
    assert settings.active_llm_model()
