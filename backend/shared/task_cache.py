"""Run each keyed async job once and share its result with every caller."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

LOGGED_KEY_LENGTH = 12  # enough of a hash to tell entries apart in logs

# Any is the coroutine's send/yield type, which callers never use.
type JobFactory[ResultT] = Callable[[], Coroutine[Any, Any, ResultT]]


class SharedTaskCache[ResultT]:
    """In-memory, per-process cache of async jobs keyed by content.

    The first request for a key starts the job; requests that arrive while
    it runs wait for the same job; later requests get the stored result.
    A failed or cancelled job is forgotten so the next request retries it.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        # A running task is an in-flight job; a finished one is the cache.
        self._tasks: dict[str, asyncio.Task[ResultT]] = {}

    async def get_or_run(
        self, key: str, start: JobFactory[ResultT]
    ) -> ResultT:
        """Return the job's result for key, starting the job only once.

        Raises:
            Whatever the job raises; the failure is not cached.
        """
        task = self._tasks.get(key)
        is_hit = task is not None
        if task is None:
            task = asyncio.create_task(start())
            self._tasks[key] = task
            task.add_done_callback(
                lambda finished: self._forget_if_failed(key, finished)
            )
        logger.info(
            "%s cache %s: key=%s done=%s",
            self._name,
            "hit" if is_hit else "miss",
            key[:LOGGED_KEY_LENGTH],
            task.done(),
        )
        # shield: one caller giving up must not cancel the shared job.
        return await asyncio.shield(task)

    def _forget_if_failed(
        self, key: str, finished: asyncio.Task[ResultT]
    ) -> None:
        has_failed = finished.cancelled() or finished.exception() is not None
        if has_failed and self._tasks.get(key) is finished:
            del self._tasks[key]
