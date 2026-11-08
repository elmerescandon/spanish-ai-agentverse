"""Unit tests for the Gemini Interactions API client wrapper."""

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx2
import pytest
from google import genai
from google.genai.errors import ContinuationInterruptedError
from pydantic import BaseModel

from backend.clients.gemini import (
    LLM_TIMEOUT_SECONDS,
    MAX_CONCURRENT_CALLS,
    MAX_RETRIES,
    APITimeoutError,
    BadRequestError,
    GeminiClient,
    InternalServerError,
    LlmCallFailedError,
    RateLimitError,
    ThinkingLevel,
)

TEST_API_KEY = "fake-api-key-for-unit-tests"
TEST_MODEL = "gemini-4-argon"
TEST_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
HTTP_BAD_REQUEST = 400
HTTP_RATE_LIMIT = 429
HTTP_SERVICE_UNAVAILABLE = 503
SAMPLE_COUNT = 42


class SampleOutput(BaseModel):
    """Minimal schema used to exercise GeminiClient JSON validation."""

    label: str
    count: int


@dataclass
class _FakeInteraction:
    """Minimal stand-in for an SDK Interaction response."""

    output_text: str


class _FakeAsyncInteractions:
    """Test double for client.aio.interactions."""

    def __init__(self, steps: list[str | Exception]) -> None:
        self._steps: list[str | Exception] = list(steps)
        # kwargs can hold str, dict, or float values passed to create()
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeInteraction:
        self.calls.append(kwargs)
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return _FakeInteraction(output_text=step)


class _FakeAio:
    """Test double for client.aio."""

    def __init__(self, interactions: _FakeAsyncInteractions) -> None:
        self.interactions = interactions


class _FakeSdkClient:
    """Test double for google.genai.Client."""

    def __init__(self, steps: list[str | Exception]) -> None:
        self.interactions_double = _FakeAsyncInteractions(steps)
        self.aio = _FakeAio(self.interactions_double)


def _make_request() -> httpx2.Request:
    return httpx2.Request("POST", TEST_URL)


def _make_response(status_code: int) -> httpx2.Response:
    return httpx2.Response(status_code, request=_make_request())


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fast_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("backend.clients.gemini.asyncio.sleep", _fast_sleep)


async def test_returns_validated_model() -> None:
    sdk = _FakeSdkClient(['{"label": "alpha", "count": 42}'])
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    result = await client.generate_json(
        prompt="Extract sample",
        response_model=SampleOutput,
        thinking_level=ThinkingLevel.HIGH,
    )

    assert result == SampleOutput(label="alpha", count=SAMPLE_COUNT)
    assert len(sdk.interactions_double.calls) == 1
    call = sdk.interactions_double.calls[0]
    assert call["model"] == TEST_MODEL
    assert call["generation_config"] == {"thinking_level": "high"}
    assert "Extract sample" in call["input"]
    assert "SampleOutput" in call["input"]


async def test_strips_code_fences() -> None:
    fenced = '```json\n{"label": "fenced", "count": 42}\n```'
    sdk = _FakeSdkClient([fenced])
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    result = await client.generate_json(
        prompt="Extract fenced",
        response_model=SampleOutput,
    )

    assert result == SampleOutput(label="fenced", count=SAMPLE_COUNT)


async def test_retries_server_error_then_succeeds() -> None:
    server_err = InternalServerError(
        "service unavailable",
        response=_make_response(HTTP_SERVICE_UNAVAILABLE),
        body=None,
    )
    sdk = _FakeSdkClient([server_err, '{"label": "ok", "count": 42}'])
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    result = await client.generate_json(
        prompt="Retry 503",
        response_model=SampleOutput,
    )

    assert result.label == "ok"
    assert len(sdk.interactions_double.calls) == 2


async def test_retries_rate_limit_then_succeeds() -> None:
    rate_err = RateLimitError(
        "quota exceeded",
        response=_make_response(HTTP_RATE_LIMIT),
        body=None,
    )
    sdk = _FakeSdkClient([rate_err, '{"label": "ok", "count": 42}'])
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    result = await client.generate_json(
        prompt="Retry 429",
        response_model=SampleOutput,
    )

    assert result.label == "ok"
    assert len(sdk.interactions_double.calls) == 2


async def test_retries_timeout_then_succeeds() -> None:
    timeout_err = APITimeoutError(_make_request())
    sdk = _FakeSdkClient([timeout_err, '{"label": "ok", "count": 42}'])
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    result = await client.generate_json(
        prompt="Retry timeout",
        response_model=SampleOutput,
    )

    assert result.label == "ok"
    assert len(sdk.interactions_double.calls) == 2


async def test_retries_invalid_json_with_error_in_next_prompt() -> None:
    sdk = _FakeSdkClient(
        [
            '{"label": "bad", "count": "not-an-int"}',
            '{"label": "repaired", "count": 42}',
        ]
    )
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    result = await client.generate_json(
        prompt="Validate JSON",
        response_model=SampleOutput,
    )

    assert result.label == "repaired"
    assert len(sdk.interactions_double.calls) == 2
    second_prompt = str(sdk.interactions_double.calls[1]["input"])
    assert "previous response failed validation:" in second_prompt


async def test_gives_up_after_max_retries() -> None:
    server_err = InternalServerError(
        "persistent 503",
        response=_make_response(HTTP_SERVICE_UNAVAILABLE),
        body=None,
    )
    sdk = _FakeSdkClient([server_err, server_err, server_err])
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    with pytest.raises(LlmCallFailedError, match="after 3 attempts"):
        await client.generate_json(
            prompt="Always fails",
            response_model=SampleOutput,
        )

    assert len(sdk.interactions_double.calls) == MAX_RETRIES


async def test_bad_request_is_not_retried() -> None:
    bad_req = BadRequestError(
        "invalid argument",
        response=_make_response(HTTP_BAD_REQUEST),
        body=None,
    )
    sdk = _FakeSdkClient([bad_req])
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    with pytest.raises(LlmCallFailedError, match="400") as exc_info:
        await client.generate_json(
            prompt="Bad request",
            response_model=SampleOutput,
        )

    assert exc_info.value.__cause__ is bad_req
    assert len(sdk.interactions_double.calls) == 1


async def test_exhausted_time_budget_is_not_retried() -> None:
    interrupted_err = ContinuationInterruptedError(
        "continuation deadline exceeded"
    )
    sdk = _FakeSdkClient([interrupted_err])
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=sdk,  # type: ignore[arg-type]
    )

    with pytest.raises(
        LlmCallFailedError,
        match=rf"time budget.*{TEST_MODEL}.*{LLM_TIMEOUT_SECONDS}",
    ) as exc_info:
        await client.generate_json(
            prompt="Long decode",
            response_model=SampleOutput,
        )

    assert exc_info.value.__cause__ is interrupted_err
    assert len(sdk.interactions_double.calls) == 1


async def test_sdk_does_not_retry_on_its_own() -> None:
    request_count = 0

    def _always_503(_request: httpx2.Request) -> httpx2.Response:
        nonlocal request_count
        request_count += 1
        return httpx2.Response(
            HTTP_SERVICE_UNAVAILABLE,
            json={
                "error": {
                    "code": HTTP_SERVICE_UNAVAILABLE,
                    "message": "Backend unavailable",
                }
            },
        )

    client = GeminiClient(api_key=TEST_API_KEY, model=TEST_MODEL)
    mock_http = httpx2.AsyncClient(transport=httpx2.MockTransport(_always_503))
    sdk_client: genai.Client = client._sdk_client
    sdk_client._api_client._async_httpx_client = mock_http

    try:
        with pytest.raises(LlmCallFailedError, match="after 3 attempts"):
            await client.generate_json(
                prompt="Check SDK retry count",
                response_model=SampleOutput,
            )
    finally:
        await mock_http.aclose()

    assert request_count == MAX_RETRIES


# Captured at import, before the autouse fixture replaces asyncio.sleep with a
# no-op: overlapping calls are only observable if a call really yields.
REAL_SLEEP = asyncio.sleep
TRACKED_CALL_SECONDS = 0.01
CAPPED_CONCURRENCY = 2
CONCURRENT_REQUESTS = 5


class _ConcurrencyTrackingInteractions:
    """Fake interactions.create() recording how many calls overlap."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.peak_in_flight = 0
        self.call_count = 0

    async def create(self, **kwargs: Any) -> _FakeInteraction:
        self.call_count += 1
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        await REAL_SLEEP(TRACKED_CALL_SECONDS)
        self.in_flight -= 1
        return _FakeInteraction(output_text='{"label": "ok", "count": 42}')


class _TrackingSdkClient:
    """Test double for google.genai.Client with a tracking create()."""

    def __init__(self, tracker: _ConcurrencyTrackingInteractions) -> None:
        self.aio = _FakeAio(tracker)  # type: ignore[arg-type]


async def _run_concurrently(client: GeminiClient, count: int) -> None:
    await asyncio.gather(
        *(
            client.generate_json(prompt="Overlap", response_model=SampleOutput)
            for _ in range(count)
        )
    )


async def test_concurrent_calls_never_exceed_the_cap() -> None:
    tracker = _ConcurrencyTrackingInteractions()
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=_TrackingSdkClient(tracker),  # type: ignore[arg-type]
        max_concurrent_calls=CAPPED_CONCURRENCY,
    )

    await _run_concurrently(client, CONCURRENT_REQUESTS)

    assert tracker.call_count == CONCURRENT_REQUESTS
    assert tracker.peak_in_flight == CAPPED_CONCURRENCY


async def test_default_cap_lets_one_full_parse_run_in_parallel() -> None:
    tracker = _ConcurrencyTrackingInteractions()
    client = GeminiClient(
        api_key=TEST_API_KEY,
        model=TEST_MODEL,
        sdk_client=_TrackingSdkClient(tracker),  # type: ignore[arg-type]
    )

    await _run_concurrently(client, MAX_CONCURRENT_CALLS + 2)

    assert tracker.peak_in_flight == MAX_CONCURRENT_CALLS


def test_cap_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_concurrent_calls"):
        GeminiClient(
            api_key=TEST_API_KEY, model=TEST_MODEL, max_concurrent_calls=0
        )
