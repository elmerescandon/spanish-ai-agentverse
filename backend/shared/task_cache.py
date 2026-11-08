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
    A failed or cancelled job, or a result that is_reusable rejects, is
    forgotten so the next request runs it again.
    """

    def __init__(
        self,
        name: str,
        is_reusable: Callable[[ResultT], bool] = lambda _result: True,
    ) -> None:
        self._name = name
        self._is_reusable = is_reusable
        # A running task is an in-flight job; a finished one is the cache.
        self._tasks: dict[str, asyncio.Task[ResultT]] = {}

    def run_in_background(self, key: str, start: JobFactory[ResultT]) -> None:
        """Start the job for key without waiting, unless it already exists.

        A later get_or_run() for the same key joins this job.
        """
        self._task_for(key, start)

    async def get_or_run(
        self, key: str, start: JobFactory[ResultT]
    ) -> ResultT:
        """Return the job's result for key, starting the job only once.

        Raises:
            Whatever the job raises; the failure is not cached.
        """
        # shield: one caller giving up must not cancel the shared job.
        return await asyncio.shield(self._task_for(key, start))

    def _task_for(
        self, key: str, start: JobFactory[ResultT]
    ) -> asyncio.Task[ResultT]:
        task = self._tasks.get(key)
        is_hit = task is not None
        if task is None:
            task = asyncio.create_task(start())
            self._tasks[key] = task
            task.add_done_callback(
                lambda finished: self._forget_unless_reusable(key, finished)
            )
        logger.info(
            "%s cache %s: key=%s done=%s",
            self._name,
            "hit" if is_hit else "miss",
            key[:LOGGED_KEY_LENGTH],
            task.done(),
        )
        return task

    def _forget_unless_reusable(
        self, key: str, finished: asyncio.Task[ResultT]
    ) -> None:
        if finished.cancelled():
            error: BaseException | None = asyncio.CancelledError()
        else:
            # Reading the exception also marks it as retrieved, so a
            # background job nobody awaited fails in the log, not silently.
            error = finished.exception()
        if error is not None:
            logger.warning(
                "%s job failed, next request retries it: key=%s error=%r",
                self._name,
                key[:LOGGED_KEY_LENGTH],
                error,
            )
        elif self._is_reusable(finished.result()):
            return
        else:
            logger.info(
                "%s result incomplete, next request reruns it: key=%s",
                self._name,
                key[:LOGGED_KEY_LENGTH],
            )
        if self._tasks.get(key) is finished:
            del self._tasks[key]
