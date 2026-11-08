"""Stores uploaded protocol documents where every server instance can read.

On Vercel each function instance has its own memory and disk, so a
document parsed by the upload request must live in shared storage for the
recommendation requests that follow. Vercel Blob is that storage; locally
(no ``BLOB_READ_WRITE_TOKEN``) an in-memory dict is enough.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Protocol

from pydantic import ValidationError
from vercel import blob

from backend.shared.messages import ProtocolDocument

logger = logging.getLogger(__name__)

BLOB_TOKEN_ENV_VAR = "BLOB_READ_WRITE_TOKEN"
BLOB_PATH_PREFIX = "protocols"
BLOB_CONTENT_TYPE = "application/json"
MAX_RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 30.0  # a parsed protocol is well under 10 MB
RETRY_BACKOFF_SECONDS = 0.5  # doubled after each failed attempt

# Blob failures worth retrying; anything else (bad token, missing store,
# suspended store) will not fix itself and must surface at once.
TRANSIENT_BLOB_ERRORS = (
    blob.BlobServiceNotAvailable,
    blob.BlobServiceRateLimited,
    blob.BlobUnknownError,
    TimeoutError,
)


class DocumentStoreError(RuntimeError):
    """Raised when a stored document cannot be written or read back."""


class DocumentStore(Protocol):
    """Saves and loads parsed protocol documents by protocol id."""

    async def save(self, document: ProtocolDocument) -> None:
        """Store the document, replacing any earlier copy."""
        ...

    async def load(self, protocol_id: str) -> ProtocolDocument | None:
        """Return the document, or None if no such protocol was stored."""
        ...


class MemoryDocumentStore:
    """Process-local store for local runs and tests."""

    def __init__(self) -> None:
        self._documents: dict[str, ProtocolDocument] = {}

    async def save(self, document: ProtocolDocument) -> None:
        self._documents[document.protocol_id] = document

    async def load(self, protocol_id: str) -> ProtocolDocument | None:
        return self._documents.get(protocol_id)


def blob_pathname(protocol_id: str) -> str:
    """Where a protocol's document lives inside the Blob store."""
    return f"{BLOB_PATH_PREFIX}/{protocol_id}.json"


class BlobDocumentStore:
    """Vercel Blob store, shared by all instances of the backend."""

    async def save(self, document: ProtocolDocument) -> None:
        """Write the document as JSON.

        Raises:
            DocumentStoreError: Blob rejected the write, or kept failing
                after MAX_RETRIES attempts.
        """
        pathname = blob_pathname(document.protocol_id)
        payload = document.model_dump_json().encode()

        async def put() -> None:
            # allow_overwrite makes a retried write safe to repeat.
            await blob.put_blob(
                pathname,
                payload,
                access="private",
                content_type=BLOB_CONTENT_TYPE,
                allow_overwrite=True,
            )

        await _with_retries("save", document.protocol_id, put)
        logger.info(
            "document stored: protocol_id=%s bytes=%d",
            document.protocol_id,
            len(payload),
        )

    async def load(self, protocol_id: str) -> ProtocolDocument | None:
        """Read the document back, or None if it was never stored.

        Raises:
            DocumentStoreError: Blob failed after MAX_RETRIES attempts, or
                the stored JSON is not a valid ProtocolDocument.
        """

        async def get() -> bytes | None:
            try:
                result = await blob.get_blob(
                    blob_pathname(protocol_id), access="private"
                )
            except blob.BlobNotFoundError:
                return None
            return result.body

        content = await _with_retries("load", protocol_id, get)
        if content is None:
            return None
        try:
            return ProtocolDocument.model_validate_json(content)
        except ValidationError as error:
            raise DocumentStoreError(
                f"stored document for protocol_id={protocol_id} is not a "
                f"valid ProtocolDocument: {error}"
            ) from error


async def _with_retries[ResultT](
    action: str,
    protocol_id: str,
    operation: Callable[[], Awaitable[ResultT]],
) -> ResultT:
    """Run one Blob call with a timeout, retrying transient failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                return await operation()
        except TRANSIENT_BLOB_ERRORS as error:
            logger.warning(
                "document store retry: action=%s protocol_id=%s "
                "attempt=%d/%d error=%r",
                action,
                protocol_id,
                attempt,
                MAX_RETRIES,
                error,
            )
            if attempt == MAX_RETRIES:
                raise DocumentStoreError(
                    f"could not {action} protocol_id={protocol_id} after "
                    f"{MAX_RETRIES} attempts: {error!r}"
                ) from error
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1))
        except blob.BlobError as error:
            raise DocumentStoreError(
                f"could not {action} protocol_id={protocol_id}: {error!r}"
            ) from error
    raise AssertionError("unreachable: the last attempt returns or raises")


_document_store: DocumentStore | None = None


def get_document_store() -> DocumentStore:
    """Blob when the token is set (Vercel), else memory; made on first use."""
    global _document_store
    if _document_store is None:
        _document_store = (
            BlobDocumentStore()
            if os.environ.get(BLOB_TOKEN_ENV_VAR)
            else MemoryDocumentStore()
        )
        logger.info(
            "document store chosen: store=%s",
            type(_document_store).__name__,
        )
    return _document_store


def set_document_store(document_store: DocumentStore | None) -> None:
    """Replace the app's document store (tests); None resets it."""
    global _document_store
    _document_store = document_store
