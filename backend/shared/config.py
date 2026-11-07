"""Typed application settings loaded from the local .env file."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GEMINI_MODEL = "gemini-4-argon"
ENV_FILE_PATH = ".env"
ENV_FILE_ENCODING = "utf-8"


class Settings(BaseSettings):
    """Environment configuration for the protocol parser and Gemini client."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding=ENV_FILE_ENCODING,
        # A key copied empty from .env.example falls back to its default
        # instead of becoming "" (e.g. GEMINI_MODEL= would break every call).
        env_ignore_empty=True,
        extra="ignore",
    )

    gemini_api_key: SecretStr
    gemini_model: str = DEFAULT_GEMINI_MODEL
    parser_agent_seed: SecretStr


def load_settings() -> Settings:
    """Load and validate settings from .env or the process environment."""
    return Settings()  # type: ignore[call-arg]
