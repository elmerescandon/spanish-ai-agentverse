"""In-memory stand-in for the vercel.blob calls our stores make."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from vercel import blob


@dataclass(frozen=True)
class FakeGetResult:
    body: bytes


@dataclass(frozen=True)
class FakeListedBlob:
    pathname: str
    uploaded_at: datetime


class FakeBlobBackend:
    """Shared object storage, as every Vercel instance would see it.

    Queue exceptions in ``failures`` to make the next calls fail in order.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploaded_at: dict[str, datetime] = {}
        self.failures: list[Exception] = []
        self.call_count = 0

    def _next_call(self) -> None:
        self.call_count += 1
        if self.failures:
            raise self.failures.pop(0)

    async def put_blob(
        self,
        pathname: str,
        body: bytes,
        *,
        allow_overwrite: bool = False,
        **_options: object,
    ) -> None:
        self._next_call()
        if pathname in self.objects and not allow_overwrite:
            raise blob.BlobError(f"blob already exists: {pathname}")
        self.objects[pathname] = bytes(body)
        # Strictly increasing, so the latest write always sorts last.
        previous = max(self.uploaded_at.values(), default=None)
        now = datetime.now(UTC)
        if previous is not None and now <= previous:
            now = previous + timedelta(microseconds=1)
        self.uploaded_at[pathname] = now

    async def get_blob(
        self, pathname: str, **_options: object
    ) -> FakeGetResult:
        self._next_call()
        if pathname not in self.objects:
            raise blob.BlobNotFoundError()
        return FakeGetResult(body=self.objects[pathname])

    async def delete_blob(self, pathname: str, **_options: object) -> None:
        self._next_call()
        self.objects.pop(pathname, None)
        self.uploaded_at.pop(pathname, None)

    def query_blobs(
        self, *, prefix: str | None = None, **_options: object
    ) -> AsyncIterator[FakeListedBlob]:
        self._next_call()
        matching = sorted(
            name for name in self.objects if name.startswith(prefix or "")
        )

        async def iterate() -> AsyncIterator[FakeListedBlob]:
            for name in matching:
                yield FakeListedBlob(
                    pathname=name, uploaded_at=self.uploaded_at[name]
                )

        return iterate()
