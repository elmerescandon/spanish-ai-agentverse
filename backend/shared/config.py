"""Typed application settings loaded from environment or .env file."""

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
ENV_FILE_PATH = ".env"
ENV_FILE_ENCODING = "utf-8"


class _CommaSeparatedEnvSource(EnvSettingsSource):
    """Decode comma-separated strings for list settings from environment."""

    def decode_complex_value(
        self,
        field_name: str,
        field_info: FieldInfo,
        value: Any,
    ) -> Any:
        try:
            return super().decode_complex_value(field_name, field_info, value)
        except Exception:
            if field_name == "allowed_origins" and isinstance(value, str):
                return [
                    origin.strip()
                    for origin in value.split(",")
                    if origin.strip()
                ]
            raise


class _CommaSeparatedDotEnvSource(
    DotEnvSettingsSource, _CommaSeparatedEnvSource
):
    """Decode comma-separated strings for list settings from .env file."""


class Settings(BaseSettings):
    """Application configuration for backend server, LLM, and data sources."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding=ENV_FILE_ENCODING,
        # An empty key in .env falls back to its default value
        env_ignore_empty=True,
        extra="ignore",
    )

    # Next.js proxy URL
    fastapi_url: str = "http://127.0.0.1:8000"

    # FastAPI Server & CORS
    backend_host: str = DEFAULT_HOST
    backend_port: int = DEFAULT_PORT
    allowed_origins: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS)
    )

    # LLM Provider (Google Gemini)
    gemini_api_key: SecretStr | None = None
    gemini_model: str = DEFAULT_GEMINI_MODEL

    # Clinical Data Sources
    aact_db_url: SecretStr | None = None
    mimic_data_path: str | None = None
    synthea_data_path: str | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Inject comma-separated list parsers for environment sources."""
        return (
            init_settings,
            _CommaSeparatedEnvSource(settings_cls),
            _CommaSeparatedDotEnvSource(
                settings_cls,
                env_file=ENV_FILE_PATH,
                env_file_encoding=ENV_FILE_ENCODING,
            ),
            file_secret_settings,
        )

    def require_gemini_api_key(self) -> str:
        """Return decrypted Gemini API key or fail loudly if missing."""
        if self.gemini_api_key is None:
            raise ValueError(
                "GEMINI_API_KEY is not set. Set it in .env or environment."
            )
        return self.gemini_api_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()  # type: ignore[call-arg]


def load_settings() -> Settings:
    """Load a fresh application settings instance from environment."""
    return Settings()  # type: ignore[call-arg]
