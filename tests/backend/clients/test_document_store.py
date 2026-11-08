"""Tests for the shared protocol document store (Blob mocked)."""

import pytest
from vercel import blob

from backend.clients import document_store
from backend.clients.document_store import (
    BlobDocumentStore,
    DocumentStoreError,
    MemoryDocumentStore,
    blob_pathname,
    get_document_store,
    set_document_store,
)
from backend.shared.messages import PageText, ProtocolDocument
from tests.fake_blob import FakeBlobBackend

PROTOCOL_ID = "proto-abc12345"


def _document(protocol_id: str = PROTOCOL_ID) -> ProtocolDocument:
    return ProtocolDocument(
        protocol_id=protocol_id,
        title="Trial",
        page_count=1,
        pages=[PageText(page_number=1, text="Page one text.")],
    )


@pytest.fixture
def backend(fake_blob: FakeBlobBackend) -> FakeBlobBackend:
    return fake_blob


async def test_blob_store_returns_the_saved_document(
    backend: FakeBlobBackend,
) -> None:
    store = BlobDocumentStore()

    await store.save(_document())

    assert blob_pathname(PROTOCOL_ID) in backend.objects
    assert await store.load(PROTOCOL_ID) == _document()


async def test_blob_store_returns_none_for_an_unknown_protocol(
    backend: FakeBlobBackend,
) -> None:
    assert await BlobDocumentStore().load("proto-missing0") is None


async def test_blob_store_retries_a_transient_failure_then_succeeds(
    backend: FakeBlobBackend,
) -> None:
    backend.failures = [blob.BlobServiceNotAvailable()]
    store = BlobDocumentStore()

    await store.save(_document())

    assert backend.call_count == 2
    assert await store.load(PROTOCOL_ID) == _document()


async def test_blob_store_gives_up_after_max_retries(
    backend: FakeBlobBackend,
) -> None:
    backend.failures = [
        blob.BlobServiceRateLimited()
        for _ in range(document_store.MAX_RETRIES)
    ]

    with pytest.raises(DocumentStoreError, match=PROTOCOL_ID):
        await BlobDocumentStore().save(_document())

    assert backend.call_count == document_store.MAX_RETRIES


async def test_blob_store_does_not_retry_a_permanent_failure(
    backend: FakeBlobBackend,
) -> None:
    backend.failures = [blob.BlobStoreSuspendedError()]

    with pytest.raises(DocumentStoreError, match=PROTOCOL_ID):
        await BlobDocumentStore().save(_document())

    assert backend.call_count == 1


async def test_blob_store_rejects_a_corrupt_stored_document(
    backend: FakeBlobBackend,
) -> None:
    backend.objects[blob_pathname(PROTOCOL_ID)] = b'{"title": 3}'

    with pytest.raises(DocumentStoreError, match="not a valid"):
        await BlobDocumentStore().load(PROTOCOL_ID)


async def test_memory_store_round_trips_and_misses() -> None:
    store = MemoryDocumentStore()

    await store.save(_document())

    assert await store.load(PROTOCOL_ID) == _document()
    assert await store.load("proto-missing0") is None


def test_store_is_blob_when_token_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(document_store.BLOB_TOKEN_ENV_VAR, "token")
    set_document_store(None)

    assert isinstance(get_document_store(), BlobDocumentStore)


def test_store_is_memory_when_token_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(document_store.BLOB_TOKEN_ENV_VAR, raising=False)
    set_document_store(None)

    assert isinstance(get_document_store(), MemoryDocumentStore)
