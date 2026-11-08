"""Review store on Vercel Blob that every server instance shares.

Blob has no conditional write, so one shared file updated by
read-modify-write would silently lose concurrent updates. Instead every
writer owns its blobs and no two requests ever write the same object.
Layout, all private JSON under ``reviews/{protocol_id}/``:

- ``protocol.json``: the protocol and its parsed fields (``save_protocol``).
- ``offers.json``: starting fields and offers (``save_offers``), replaced
  whole on each call.
- ``changes/{changed_at UTC}-{uuid}.json``: one new blob per accepted
  change, never rewritten. Names sort in time order.

Current field values are never stored: they are replayed from the
protocol, the starting fields and the changes in name order. Two
concurrent accepts therefore never lose data; for the same field the
change with the later name wins.
"""

import asyncio
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError
from vercel import blob

from backend.clients.document_store import (
    BLOB_CONTENT_TYPE,
    DocumentStoreError,
    with_blob_retries,
)
from backend.clients.protocol_db import (
    FieldChangeRecord,
    OfferedValue,
    ProtocolRecord,
    ProtocolReview,
    StoredField,
)

logger = logging.getLogger(__name__)

REVIEW_PATH_PREFIX = "reviews"
PROTOCOL_FILENAME = "protocol.json"
OFFERS_FILENAME = "offers.json"
CHANGES_DIRECTORY = "changes"
# Fixed width so names sort lexically in time order.
CHANGE_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S.%fZ"


class FieldBlob(BaseModel):
    """A stored field as it appears inside a blob."""

    field: str
    value: str
    unit: str | None = None
    page: int | None = None


class OfferBlob(BaseModel):
    """An offered value as it appears inside offers.json."""

    field: str
    value: float
    unit: str | None
    decision_id: str
    option_id: str
    rationale: str


class ProtocolBlob(BaseModel):
    """Contents of protocol.json."""

    protocol_id: str
    title: str
    page_count: int
    uploaded_at: datetime
    fields: list[FieldBlob]


class OffersBlob(BaseModel):
    """Contents of offers.json."""

    starting_fields: list[FieldBlob]
    offers: list[OfferBlob]


class ChangeBlob(BaseModel):
    """Contents of one change blob: all a replay needs."""

    new_field: FieldBlob
    old_value: str | None
    decision_id: str
    option_id: str
    rationale: str
    changed_at: datetime


def _protocol_path(protocol_id: str) -> str:
    return f"{REVIEW_PATH_PREFIX}/{protocol_id}/{PROTOCOL_FILENAME}"


def _offers_path(protocol_id: str) -> str:
    return f"{REVIEW_PATH_PREFIX}/{protocol_id}/{OFFERS_FILENAME}"


def _changes_prefix(protocol_id: str) -> str:
    return f"{REVIEW_PATH_PREFIX}/{protocol_id}/{CHANGES_DIRECTORY}/"


def _change_path(protocol_id: str, changed_at: datetime) -> str:
    """A unique, time-ordered path; a naive time is taken as UTC."""
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=UTC)
    stamp = changed_at.astimezone(UTC).strftime(CHANGE_TIMESTAMP_FORMAT)
    return f"{_changes_prefix(protocol_id)}{stamp}-{uuid.uuid4().hex}.json"


def _to_stored_field(item: FieldBlob) -> StoredField:
    return StoredField(item.field, item.value, item.unit, item.page)


def _to_field_blob(item: StoredField) -> FieldBlob:
    return FieldBlob(
        field=item.field, value=item.value, unit=item.unit, page=item.page
    )


def _to_change_record(change_id: int, change: ChangeBlob) -> FieldChangeRecord:
    return FieldChangeRecord(
        change_id=change_id,
        field=change.new_field.field,
        old_value=change.old_value,
        new_value=change.new_field.value,
        decision_id=change.decision_id,
        option_id=change.option_id,
        rationale=change.rationale,
        changed_at=change.changed_at,
    )


def replay_fields(
    protocol: ProtocolBlob,
    offers: OffersBlob | None,
    changes: Sequence[ChangeBlob],
) -> dict[str, StoredField]:
    """Current fields: protocol, then new starting fields, then changes."""
    current = {item.field: _to_stored_field(item) for item in protocol.fields}
    if offers is not None:
        for item in offers.starting_fields:
            current.setdefault(item.field, _to_stored_field(item))
    for change in changes:
        current[change.new_field.field] = _to_stored_field(change.new_field)
    return current


def _parse[ModelT: BaseModel](
    model: type[ModelT], content: bytes, protocol_id: str, path: str
) -> ModelT:
    try:
        return model.model_validate_json(content)
    except ValidationError as error:
        raise DocumentStoreError(
            f"stored blob for protocol_id={protocol_id} at {path} is not "
            f"a valid {model.__name__}: {error}"
        ) from error


class BlobProtocolStore:
    """ReviewStore backed by Vercel Blob, shared by all instances."""

    async def _put(
        self,
        protocol_id: str,
        path: str,
        model: BaseModel,
        *,
        allow_overwrite: bool,
    ) -> None:
        payload = model.model_dump_json().encode()

        async def put() -> None:
            await blob.put_blob(
                path,
                payload,
                access="private",
                content_type=BLOB_CONTENT_TYPE,
                allow_overwrite=allow_overwrite,
            )

        await with_blob_retries("save review", protocol_id, put)

    async def _get(self, protocol_id: str, path: str) -> bytes | None:
        async def get() -> bytes | None:
            try:
                result = await blob.get_blob(path, access="private")
            except blob.BlobNotFoundError:
                return None
            return result.body

        return await with_blob_retries("load review", protocol_id, get)

    async def _read[ModelT: BaseModel](
        self, model: type[ModelT], protocol_id: str, path: str
    ) -> ModelT | None:
        content = await self._get(protocol_id, path)
        if content is None:
            return None
        return _parse(model, content, protocol_id, path)

    async def _read_changes(self, protocol_id: str) -> list[ChangeBlob]:
        """All change blobs, in name (time) order."""

        async def list_paths() -> list[str]:
            return sorted(
                [
                    listed.pathname
                    async for listed in blob.query_blobs(
                        prefix=_changes_prefix(protocol_id)
                    )
                ]
            )

        paths = await with_blob_retries(
            "list changes", protocol_id, list_paths
        )
        contents = await asyncio.gather(
            *(self._get(protocol_id, path) for path in paths)
        )
        changes: list[ChangeBlob] = []
        for path, content in zip(paths, contents, strict=True):
            if content is None:
                raise DocumentStoreError(
                    f"change blob for protocol_id={protocol_id} listed "
                    f"but missing at {path}"
                )
            changes.append(_parse(ChangeBlob, content, protocol_id, path))
        return changes

    async def save_protocol(
        self, record: ProtocolRecord, fields: Sequence[StoredField]
    ) -> None:
        """Store an uploaded protocol and its parsed fields.

        Raises:
            DocumentStoreError: Blob failed after all retries.
        """
        await self._put(
            record.protocol_id,
            _protocol_path(record.protocol_id),
            ProtocolBlob(
                protocol_id=record.protocol_id,
                title=record.title,
                page_count=record.page_count,
                uploaded_at=record.uploaded_at,
                fields=[_to_field_blob(item) for item in fields],
            ),
            allow_overwrite=True,  # a retried upload must be safe
        )
        logger.info(
            "protocol stored: protocol_id=%s fields=%d",
            record.protocol_id,
            len(fields),
        )

    async def save_offers(
        self,
        protocol_id: str,
        starting_fields: Sequence[StoredField],
        offers: Sequence[OfferedValue],
    ) -> None:
        """Record an agent's starting values and the values it offers.

        The whole offers blob is replaced. Starting fields only count
        for fields the protocol lacks, so a re-run never overwrites an
        accepted change.

        Raises:
            DocumentStoreError: Blob failed after all retries.
        """
        await self._put(
            protocol_id,
            _offers_path(protocol_id),
            OffersBlob(
                starting_fields=[_to_field_blob(f) for f in starting_fields],
                offers=[
                    OfferBlob(
                        field=offer.field,
                        value=offer.value,
                        unit=offer.unit,
                        decision_id=offer.decision_id,
                        option_id=offer.option_id,
                        rationale=offer.rationale,
                    )
                    for offer in offers
                ],
            ),
            allow_overwrite=True,
        )
        logger.info(
            "offers stored: protocol_id=%s starting_fields=%d offers=%d",
            protocol_id,
            len(starting_fields),
            len(offers),
        )

    async def has_protocol(self, protocol_id: str) -> bool:
        """True if the protocol was uploaded and stored.

        Raises:
            DocumentStoreError: Blob failed after all retries.
        """
        content = await self._get(protocol_id, _protocol_path(protocol_id))
        return content is not None

    async def offers_for(
        self, protocol_id: str, field: str
    ) -> list[OfferedValue]:
        """The values currently offered for one field of a protocol.

        Raises:
            DocumentStoreError: Blob failed, or offers.json is corrupt.
        """
        path = _offers_path(protocol_id)
        offers = await self._read(OffersBlob, protocol_id, path)
        if offers is None:
            return []
        return [
            OfferedValue(**offer.model_dump())
            for offer in offers.offers
            if offer.field == field
        ]

    async def apply_change(
        self,
        protocol_id: str,
        new_field: StoredField,
        offer: OfferedValue,
        changed_at: datetime,
    ) -> FieldChangeRecord | None:
        """Set a field to an offered value and log the change.

        Returns None, and writes nothing, when the field already holds
        the value, so a retried request never records the change twice.

        Raises:
            DocumentStoreError: Blob failed, a blob is corrupt, or the
                protocol was never stored.
        """
        protocol_path = _protocol_path(protocol_id)
        protocol, offers, changes = await asyncio.gather(
            self._read(ProtocolBlob, protocol_id, protocol_path),
            self._read(OffersBlob, protocol_id, _offers_path(protocol_id)),
            self._read_changes(protocol_id),
        )
        if protocol is None:
            raise DocumentStoreError(
                f"cannot apply change: protocol_id={protocol_id} has no "
                f"blob at {protocol_path}"
            )
        current = replay_fields(protocol, offers, changes).get(new_field.field)
        old_value = None if current is None else current.value
        change: FieldChangeRecord | None = None
        if old_value != new_field.value:
            change_blob = ChangeBlob(
                new_field=_to_field_blob(new_field),
                old_value=old_value,
                decision_id=offer.decision_id,
                option_id=offer.option_id,
                rationale=offer.rationale,
                changed_at=changed_at,
            )
            await self._put(
                protocol_id,
                _change_path(protocol_id, changed_at),
                change_blob,
                allow_overwrite=False,  # the name is unique per call
            )
            change = _to_change_record(len(changes) + 1, change_blob)
        logger.info(
            "field change: protocol_id=%s field=%s value=%s is_new=%s",
            protocol_id,
            new_field.field,
            new_field.value,
            change is not None,
        )
        return change

    async def latest_protocol_id(self) -> str | None:
        """The most recently uploaded protocol's id; None if none yet.

        Raises:
            DocumentStoreError: Blob failed after all retries.
        """

        async def latest() -> str | None:
            newest_path: str | None = None
            newest_at: datetime | None = None
            async for listed in blob.query_blobs(
                prefix=f"{REVIEW_PATH_PREFIX}/"
            ):
                if not listed.pathname.endswith(f"/{PROTOCOL_FILENAME}"):
                    continue
                if newest_at is None or listed.uploaded_at > newest_at:
                    newest_path, newest_at = (
                        listed.pathname,
                        listed.uploaded_at,
                    )
            return None if newest_path is None else newest_path.split("/")[1]

        return await with_blob_retries("find latest", "*", latest)

    async def load_review(self, protocol_id: str) -> ProtocolReview | None:
        """A protocol's fields and accepted changes; None if unknown.

        Raises:
            DocumentStoreError: Blob failed, or a blob is corrupt.
        """
        protocol = await self._read(
            ProtocolBlob, protocol_id, _protocol_path(protocol_id)
        )
        if protocol is None:
            return None
        offers, changes = await asyncio.gather(
            self._read(OffersBlob, protocol_id, _offers_path(protocol_id)),
            self._read_changes(protocol_id),
        )
        current = replay_fields(protocol, offers, changes)
        return ProtocolReview(
            protocol=ProtocolRecord(
                protocol_id=protocol.protocol_id,
                title=protocol.title,
                page_count=protocol.page_count,
                uploaded_at=protocol.uploaded_at,
            ),
            fields=[current[name] for name in sorted(current)],
            changes=[
                _to_change_record(position, change)
                for position, change in enumerate(changes, start=1)
            ],
        )
