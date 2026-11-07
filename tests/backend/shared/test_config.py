"""Tests for loading typed settings from the environment."""

import pytest

from backend.shared.config import DEFAULT_GEMINI_MODEL, Settings


def test_empty_model_value_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("PARSER_AGENT_SEED", "test seed phrase config 0001")
    monkeypatch.setenv("GEMINI_MODEL", "")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.gemini_model == DEFAULT_GEMINI_MODEL
