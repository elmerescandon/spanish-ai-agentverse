"""Tests for typed environment configuration and validation."""

import pytest

from backend.shared.config import (
    DEFAULT_ALLOWED_ORIGINS,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_HOST,
    DEFAULT_PORT,
    Settings,
    get_settings,
    load_settings,
)


def test_default_settings() -> None:
    """Settings loads standard defaults when no environment is provided."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.backend_host == DEFAULT_HOST
    assert settings.backend_port == DEFAULT_PORT
    assert settings.allowed_origins == list(DEFAULT_ALLOWED_ORIGINS)
    assert settings.gemini_model == DEFAULT_GEMINI_MODEL
    assert settings.gemini_api_key is None
    assert settings.aact_db_url is None
    assert settings.mimic_data_path is None
    assert settings.synthea_data_path is None


def test_custom_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings reads custom environment overrides correctly."""
    monkeypatch.setenv("FASTAPI_URL", "https://api.custom.com")
    monkeypatch.setenv("BACKEND_HOST", "127.0.0.1")
    monkeypatch.setenv("BACKEND_PORT", "9000")
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://preview.vercel.app, https://prod.vercel.app",
    )
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-pro")
    monkeypatch.setenv("AACT_DB_URL", "postgresql://user:pass@db:5432/aact")
    monkeypatch.setenv("MIMIC_DATA_PATH", "/data/mimic")
    monkeypatch.setenv("SYNTHEA_DATA_PATH", "/data/synthea")

    settings = load_settings()
    assert settings.fastapi_url == "https://api.custom.com"
    assert settings.backend_host == "127.0.0.1"
    assert settings.backend_port == 9000
    assert settings.allowed_origins == [
        "https://preview.vercel.app",
        "https://prod.vercel.app",
    ]
    assert settings.gemini_model == "gemini-1.5-pro"
    assert settings.require_gemini_api_key() == "super-secret-gemini-key"
    assert settings.mimic_data_path == "/data/mimic"
    assert settings.synthea_data_path == "/data/synthea"


def test_allowed_origins_single_and_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings parses single string and json array formats for origins."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://single.origin.com")
    assert load_settings().allowed_origins == ["https://single.origin.com"]

    monkeypatch.setenv("ALLOWED_ORIGINS", '["http://a.com", "http://b.com"]')
    assert load_settings().allowed_origins == [
        "http://a.com",
        "http://b.com",
    ]


def test_empty_env_var_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty env values fall back to defaults rather than empty strings."""
    monkeypatch.setenv("GEMINI_MODEL", "")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.gemini_model == DEFAULT_GEMINI_MODEL


def test_secret_values_masked_in_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secret fields are never exposed in string or repr representations."""
    raw_key = "sensitive-api-secret"
    monkeypatch.setenv("GEMINI_API_KEY", raw_key)
    monkeypatch.setenv("AACT_DB_URL", "postgresql://user:secret@localhost/db")

    settings = load_settings()
    settings_repr = repr(settings)

    assert raw_key not in settings_repr
    assert "secret" not in settings_repr
    assert "**********" in settings_repr


def test_require_gemini_api_key_raises_when_missing() -> None:
    """Calling require_gemini_api_key fails loudly if key is unset."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        gemini_api_key=None,
    )
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
        settings.require_gemini_api_key()


def test_get_settings_cached() -> None:
    """get_settings returns the same cached instance on repeated calls."""
    first = get_settings()
    second = get_settings()
    assert first is second
