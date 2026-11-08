"""Tests for the Vercel Blob protocol review store."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.clients.document_store import DocumentStoreError
from backend.clients.protocol_blob_store import BlobProtocolStore
from backend.clients.protocol_db import (
    OfferedValue,
    ProtocolDb,
    ProtocolRecord,
    ProtocolReview,
    ReviewStore,
    StoredField,
)
from tests.fake_blob import FakeBlobBackend

PROTOCOL_ID = "proto-1"
UPLOADED_AT = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
CHANGED_AT = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
RECORD = ProtocolRecord(PROTOCOL_ID, "Trial", 98, UPLOADED_AT)
FIELD = "comparison.hba1c_upper_bound"
OTHER_FIELD = "comparison.bmi_upper_bound"
OFFER = OfferedValue(
    field=FIELD,
    value=10.5,
    unit="%",
    decision_id="cmp-hba1c_upper_bound",
    option_id="cmp-hba1c_upper_bound-recent",
    rationale="10.5% is in line with 23 recent peer trials.",
)
OTHER_OFFER = replace(OFFER, field=OTHER_FIELD, value=35.0, unit="kg/m2")
PROTOCOL_FIELDS = [StoredField("design.phase", "PHASE3", page=1)]
PROTOCOL_PATH = f"reviews/{PROTOCOL_ID}/protocol.json"
CHANGES_PREFIX = f"reviews/{PROTOCOL_ID}/changes/"


async def _stored_protocol(store: ReviewStore) -> None:
    await store.save_protocol(RECORD, PROTOCOL_FIELDS)
    await store.save_offers(
        PROTOCOL_ID,
        [StoredField(FIELD, "11", unit="%")],
        [OFFER, OTHER_OFFER],
    )


def _change_paths(fake_blob: FakeBlobBackend) -> list[str]:
    return [p for p in fake_blob.objects if p.startswith(CHANGES_PREFIX)]


async def test_saved_protocol_loads_back_with_its_fields(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()
    await _stored_protocol(store)

    review = await store.load_review(PROTOCOL_ID)

    assert review is not None
    assert review.protocol == RECORD
    assert review.fields == [
        StoredField(FIELD, "11", unit="%"),
        PROTOCOL_FIELDS[0],
    ]
    assert review.changes == []


async def test_has_protocol_is_false_until_saved(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()

    assert not await store.has_protocol(PROTOCOL_ID)
    await store.save_protocol(RECORD, PROTOCOL_FIELDS)

    assert await store.has_protocol(PROTOCOL_ID)


async def test_unknown_protocol_has_no_review_and_no_offers(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()

    assert await store.load_review("missing") is None
    assert await store.offers_for("missing", FIELD) == []


async def test_second_save_offers_replaces_the_first(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()
    await _stored_protocol(store)
    newer = replace(OFFER, value=9.0)

    await store.save_offers(PROTOCOL_ID, [], [newer])

    assert await store.offers_for(PROTOCOL_ID, FIELD) == [newer]
    assert await store.offers_for(PROTOCOL_ID, OTHER_FIELD) == []


async def test_starting_field_is_ignored_when_protocol_has_the_field(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()
    await store.save_protocol(RECORD, [StoredField(FIELD, "12")])
    await store.save_offers(PROTOCOL_ID, [StoredField(FIELD, "11")], [])

    review = await store.load_review(PROTOCOL_ID)

    assert review is not None
    assert review.fields == [StoredField(FIELD, "12")]


async def test_starting_field_is_used_when_protocol_lacks_the_field(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()
    await store.save_protocol(RECORD, [])
    await store.save_offers(PROTOCOL_ID, [StoredField(FIELD, "11")], [])

    review = await store.load_review(PROTOCOL_ID)

    assert review is not None
    assert review.fields == [StoredField(FIELD, "11")]


async def test_applied_change_is_returned_and_shown_in_the_review(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()
    await _stored_protocol(store)

    change = await store.apply_change(
        PROTOCOL_ID, StoredField(FIELD, "10.5", unit="%"), OFFER, CHANGED_AT
    )

    assert change is not None
    assert change.change_id == 1
    assert change.old_value == "11"
    assert change.new_value == "10.5"
    review = await store.load_review(PROTOCOL_ID)
    assert review is not None
    assert review.changes == [change]
    assert StoredField(FIELD, "10.5", unit="%") in review.fields


async def test_retried_change_with_same_value_writes_no_blob(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()
    await _stored_protocol(store)
    new_field = StoredField(FIELD, "10.5", unit="%")
    await store.apply_change(PROTOCOL_ID, new_field, OFFER, CHANGED_AT)
    blob_count = len(fake_blob.objects)

    retried = await store.apply_change(
        PROTOCOL_ID, new_field, OFFER, CHANGED_AT + timedelta(seconds=1)
    )

    assert retried is None
    assert len(fake_blob.objects) == blob_count


async def test_changes_are_numbered_in_time_order(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()
    await _stored_protocol(store)
    later = CHANGED_AT + timedelta(minutes=5)
    await store.apply_change(
        PROTOCOL_ID, StoredField(OTHER_FIELD, "35"), OTHER_OFFER, later
    )
    await store.apply_change(
        PROTOCOL_ID, StoredField(FIELD, "10.5"), OFFER, CHANGED_AT
    )

    review = await store.load_review(PROTOCOL_ID)

    assert review is not None
    assert [(c.change_id, c.field) for c in review.changes] == [
        (1, FIELD),
        (2, OTHER_FIELD),
    ]


async def test_second_instance_sees_the_first_instances_writes(
    fake_blob: FakeBlobBackend,
) -> None:
    first_instance = BlobProtocolStore()
    second_instance = BlobProtocolStore()
    await _stored_protocol(first_instance)

    change = await second_instance.apply_change(
        PROTOCOL_ID, StoredField(FIELD, "10.5", unit="%"), OFFER, CHANGED_AT
    )

    assert await second_instance.has_protocol(PROTOCOL_ID)
    review = await first_instance.load_review(PROTOCOL_ID)
    assert review is not None
    assert review.changes == [change]
    retried = await first_instance.apply_change(
        PROTOCOL_ID, StoredField(FIELD, "10.5", unit="%"), OFFER, CHANGED_AT
    )
    assert retried is None


async def test_concurrent_changes_to_different_fields_both_persist(
    fake_blob: FakeBlobBackend,
) -> None:
    first_instance = BlobProtocolStore()
    second_instance = BlobProtocolStore()
    await _stored_protocol(first_instance)

    await asyncio.gather(
        first_instance.apply_change(
            PROTOCOL_ID, StoredField(FIELD, "10.5"), OFFER, CHANGED_AT
        ),
        second_instance.apply_change(
            PROTOCOL_ID,
            StoredField(OTHER_FIELD, "35"),
            OTHER_OFFER,
            CHANGED_AT,
        ),
    )

    review = await first_instance.load_review(PROTOCOL_ID)
    assert review is not None
    values = {item.field: item.value for item in review.fields}
    assert values[FIELD] == "10.5"
    assert values[OTHER_FIELD] == "35"
    assert len(review.changes) == 2
    assert len(_change_paths(fake_blob)) == 2


async def test_corrupt_protocol_blob_raises_naming_protocol_and_path(
    fake_blob: FakeBlobBackend,
) -> None:
    fake_blob.objects[PROTOCOL_PATH] = b'{"title": 3}'
    store = BlobProtocolStore()

    with pytest.raises(DocumentStoreError) as error:
        await store.load_review(PROTOCOL_ID)

    assert PROTOCOL_ID in str(error.value)
    assert PROTOCOL_PATH in str(error.value)


async def test_apply_change_to_unknown_protocol_raises(
    fake_blob: FakeBlobBackend,
) -> None:
    store = BlobProtocolStore()

    with pytest.raises(DocumentStoreError, match="missing"):
        await store.apply_change(
            "missing", StoredField(FIELD, "10.5"), OFFER, CHANGED_AT
        )


async def _run_scenario(store: ReviewStore) -> ProtocolReview | None:
    await _stored_protocol(store)
    await store.apply_change(
        PROTOCOL_ID, StoredField(FIELD, "10.5", unit="%"), OFFER, CHANGED_AT
    )
    await store.apply_change(
        PROTOCOL_ID,
        StoredField(OTHER_FIELD, "35", unit="kg/m2"),
        OTHER_OFFER,
        CHANGED_AT + timedelta(minutes=1),
    )
    await store.apply_change(
        PROTOCOL_ID,
        StoredField(FIELD, "9", unit="%"),
        OFFER,
        CHANGED_AT + timedelta(minutes=2),
    )
    await store.apply_change(  # retry: no-op
        PROTOCOL_ID,
        StoredField(FIELD, "9", unit="%"),
        OFFER,
        CHANGED_AT + timedelta(minutes=3),
    )
    await store.save_offers(  # re-run must not undo accepted changes
        PROTOCOL_ID, [StoredField(FIELD, "11", unit="%")], [OFFER]
    )
    return await store.load_review(PROTOCOL_ID)


@pytest.mark.parametrize("scenario_name", ["accept-and-rerun"])
async def test_blob_store_matches_sqlite_store_semantics(
    scenario_name: str, tmp_path: Path, fake_blob: FakeBlobBackend
) -> None:
    sqlite_review = await _run_scenario(ProtocolDb(tmp_path / "db.sqlite"))
    blob_review = await _run_scenario(BlobProtocolStore())

    assert sqlite_review is not None
    assert blob_review is not None
    assert blob_review.fields == sqlite_review.fields
    assert blob_review.changes == sqlite_review.changes
    assert blob_review == sqlite_review


async def test_latest_protocol_is_the_last_one_saved_in_both_stores(
    tmp_path: Path, fake_blob: FakeBlobBackend
) -> None:
    stores: list[ReviewStore] = [
        ProtocolDb(tmp_path / "db.sqlite"),
        BlobProtocolStore(),
    ]
    for store in stores:
        assert await store.latest_protocol_id() is None
        await _stored_protocol(store)  # offers.json must not count
        later = replace(
            RECORD,
            protocol_id="proto-2",
            uploaded_at=UPLOADED_AT + timedelta(hours=1),
        )
        await store.save_protocol(later, PROTOCOL_FIELDS)
        await store.save_offers(PROTOCOL_ID, [], [OFFER])

        assert await store.latest_protocol_id() == "proto-2"
