"""Tests for the run-once task cache shared by the parser and the check."""

import asyncio

import pytest

from backend.shared.task_cache import SharedTaskCache

KEY = "protocol-content-hash"


class _CountingJob:
    """Job factory that counts starts and fails the first N of them."""

    def __init__(self, failures: int = 0) -> None:
        self.start_count = 0
        self._failures = failures

    async def __call__(self) -> str:
        self.start_count += 1
        await asyncio.sleep(0)
        if self.start_count <= self._failures:
            raise RuntimeError(f"job failed on start {self.start_count}")
        return f"result {self.start_count}"


async def test_request_joins_the_job_started_in_the_background() -> None:
    cache = SharedTaskCache[str]("test")
    job = _CountingJob()

    cache.run_in_background(KEY, job)
    result = await cache.get_or_run(KEY, job)

    assert result == "result 1"
    assert job.start_count == 1


async def test_failed_background_job_is_logged_and_retried(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache = SharedTaskCache[str]("test")
    job = _CountingJob(failures=1)

    cache.run_in_background(KEY, job)
    for _ in range(3):  # let the job fail and its done callback run
        await asyncio.sleep(0)
    result = await cache.get_or_run(KEY, job)

    assert result == "result 2"
    assert "test job failed, next request retries it" in caplog.text


async def test_unreusable_result_is_returned_but_run_again_next_time() -> None:
    cache = SharedTaskCache[str](
        "test", is_reusable=lambda result: result != "result 1"
    )
    job = _CountingJob()

    first = await cache.get_or_run(KEY, job)
    second = await cache.get_or_run(KEY, job)
    third = await cache.get_or_run(KEY, job)

    assert (first, second, third) == ("result 1", "result 2", "result 2")
    assert job.start_count == 2
