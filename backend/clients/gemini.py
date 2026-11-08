"""Gemini Interactions API client with retries, timeouts and validation."""

import asyncio
import json
import logging
import re
from enum import StrEnum
from typing import Protocol

from google import genai
from google.genai import types

# [TO REFACTOR:(alex)]: google.genai._interactions is a private module
from google.genai._interactions import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from google.genai.errors import ContinuationInterruptedError
from pydantic import BaseModel, ValidationError

__all__ = [
    "LLM_TIMEOUT_SECONDS",
    "MAX_CONCURRENT_CALLS",
    "MAX_RETRIES",
    "APIConnectionError",
    "APIStatusError",
    "APITimeoutError",
    "BadRequestError",
    "ContinuationInterruptedError",
    "GeminiClient",
    "InternalServerError",
    "JsonGenerator",
    "LlmCallFailedError",
    "RateLimitError",
    "ThinkingLevel",
]

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = (
    2.0  # delay is RETRY_BASE_DELAY_SECONDS * 2**attempt
)
LLM_TIMEOUT_SECONDS = 300  # upper bound for 100k+ token protocol calls
MILLISECONDS_PER_SECOND = 1000
SDK_SINGLE_ATTEMPT = 1  # disables the SDK's built-in retry loop
# One full protocol parse (six facets) runs in parallel; anything beyond
# that queues instead of tripping Gemini's rate limit (HTTP 429).
MAX_CONCURRENT_CALLS = 6
HTTP_RATE_LIMIT_STATUS = 429
HTTP_SERVER_ERROR_MIN_STATUS = 500

CODE_FENCE_PATTERN = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?\s*```$",
    re.DOTALL | re.IGNORECASE,
)


class ThinkingLevel(StrEnum):
    """Reasoning budget passed to Gemini Interactions generation_config."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LlmCallFailedError(RuntimeError):
    """Raised when an LLM call fails immediately or after all retries."""


class JsonGenerator(Protocol):
    """Protocol for generating and validating structured JSON via an LLM."""

    async def generate_json[ModelT: BaseModel](
        self,
        prompt: str,
        response_model: type[ModelT],
        thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM,
    ) -> ModelT:
        """Generate structured output validated against response_model."""
        ...


def strip_markdown_code_fences(raw_text: str) -> str:
    """Remove surrounding markdown ``` or ```json code fences if present."""
    stripped = raw_text.strip()
    match = CODE_FENCE_PATTERN.match(stripped)
    if match is not None:
        return match.group(1).strip()
    return stripped


def _build_schema_prompt(
    base_prompt: str,
    schema_json: str,
    validation_error: str | None = None,
) -> str:
    """Append the JSON schema instruction and optional validation error."""
    parts = [
        base_prompt,
        f"Return ONLY JSON matching this schema: {schema_json}",
    ]
    if validation_error is not None:
        parts.append(
            f"previous response failed validation: {validation_error}"
        )
    return "\n\n".join(parts)


def _is_retryable_status(status_code: int | None) -> bool:
    """Return True if an HTTP status code is 429 or 5xx."""
    if status_code is None:
        return False
    return (
        status_code == HTTP_RATE_LIMIT_STATUS
        or status_code >= HTTP_SERVER_ERROR_MIN_STATUS
    )


class GeminiClient:
    """Async wrapper around the Google GenAI Interactions API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        sdk_client: genai.Client | None = None,
        max_concurrent_calls: int = MAX_CONCURRENT_CALLS,
    ) -> None:
        if max_concurrent_calls < 1:
            raise ValueError(
                "max_concurrent_calls must be at least 1, "
                f"got {max_concurrent_calls}"
            )
        self._model = model
        # Shared by every call on this client; held only during the API
        # request itself, never during retry backoff.
        self._call_slots = asyncio.Semaphore(max_concurrent_calls)
        if sdk_client is not None:
            self._sdk_client = sdk_client
        else:
            self._sdk_client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=LLM_TIMEOUT_SECONDS * MILLISECONDS_PER_SECOND,
                    retry_options=types.HttpRetryOptions(
                        attempts=SDK_SINGLE_ATTEMPT
                    ),
                ),
            )

    async def generate_json[ModelT: BaseModel](
        self,
        prompt: str,
        response_model: type[ModelT],
        thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM,
    ) -> ModelT:
        """Call Interactions API and validate JSON reply with retries."""
        schema_json = json.dumps(response_model.model_json_schema())
        validation_feedback: str | None = None
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            attempt_number = attempt + 1
            full_prompt = _build_schema_prompt(
                base_prompt=prompt,
                schema_json=schema_json,
                validation_error=validation_feedback,
            )
            try:
                async with self._call_slots:
                    interactions = self._sdk_client.aio.interactions
                    interaction = await interactions.create(
                        model=self._model,
                        input=full_prompt,
                        generation_config={
                            "thinking_level": thinking_level.value
                        },
                        timeout=float(LLM_TIMEOUT_SECONDS),
                    )
                raw_text: str = getattr(interaction, "output_text", None) or ""
                cleaned_text = strip_markdown_code_fences(raw_text)
                return response_model.model_validate_json(cleaned_text)
            except ContinuationInterruptedError as error:
                raise LlmCallFailedError(
                    "LLM call time budget exhausted: "
                    f"model={self._model} "
                    f"timeout_seconds={LLM_TIMEOUT_SECONDS}"
                ) from error
            except APIStatusError as error:
                if not _is_retryable_status(error.status_code):
                    raise LlmCallFailedError(
                        "LLM call rejected with non-retryable status: "
                        f"model={self._model} status_code={error.status_code}"
                    ) from error
                last_error = error
                retry_reason = f"status_code={error.status_code}"
            except APIConnectionError as error:
                last_error = error
                retry_reason = f"connection_error={type(error).__name__}"
            except ValidationError as error:
                last_error = error
                validation_feedback = str(error)
                retry_reason = f"validation_errors={error.error_count()}"

            logger.warning(
                "llm call failed, retrying: model=%s schema=%s "
                "attempt=%d/%d %s",
                self._model,
                response_model.__name__,
                attempt_number,
                MAX_RETRIES,
                retry_reason,
            )
            if attempt_number < MAX_RETRIES:
                delay_seconds = RETRY_BASE_DELAY_SECONDS * (2**attempt)
                await asyncio.sleep(delay_seconds)

        raise LlmCallFailedError(
            f"LLM call failed after {MAX_RETRIES} attempts: "
            f"model={self._model} schema={response_model.__name__} "
            f"last_error={last_error}"
        ) from last_error
