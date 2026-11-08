"""Tests for the SQLite protocol review store."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.clients.protocol_db import (
    OfferedValue,
    ProtocolDb,
    ProtocolRecord,
    ProtocolStoreError,
    StoredField,
)

PROTOCOL_ID = "proto-1"
UPLOADED_AT = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
CHANGED_AT = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
FIELD = "comparison.hba1c_upper_bound"
OFFER = OfferedValue(
    field=FIELD,
    value=10.5,
    unit="%",
    decision_id="cmp-hba1c_upper_bound",
    option_id="cmp-hba1c_upper_bound-recent",
    rationale="10.5% is in line with 23 recent peer trials.",
)


async def _stored_protocol(tmp_path: Path) -> ProtocolDb:
    db = ProtocolDb(tmp_path / "protocols.db")
    await db.save_protocol(
        ProtocolRecord(PROTOCOL_ID, "Trial", 98, UPLOADED_AT),
        [StoredField("design.phase", "PHASE3", page=1)],
    )
    await db.save_offers(
        PROTOCOL_ID, [StoredField(FIELD, "11", unit="%")], [OFFER]
    )
    return db


async def test_saved_protocol_loads_back_with_its_fields(
    tmp_path: Path,
) -> None:
    db = await _stored_protocol(tmp_path)

    review = await db.load_review(PROTOCOL_ID)

    assert review is not None
    assert review.protocol.title == "Trial"
    assert review.protocol.uploaded_at == UPLOADED_AT
    assert StoredField("design.phase", "PHASE3", page=1) in review.fields
    assert StoredField(FIELD, "11", unit="%") in review.fields
    assert review.changes == []


async def test_unknown_protocol_loads_as_none(tmp_path: Path) -> None:
    db = ProtocolDb(tmp_path / "protocols.db")

    assert await db.load_review("proto-missing") is None
    assert not await db.has_protocol("proto-missing")


async def test_applied_change_updates_the_field_and_is_logged(
    tmp_path: Path,
) -> None:
    db = await _stored_protocol(tmp_path)

    change = await db.apply_change(
        PROTOCOL_ID, StoredField(FIELD, "10.5", unit="%"), OFFER, CHANGED_AT
    )

    review = await db.load_review(PROTOCOL_ID)
    assert review is not None
    assert change is not None
    assert (change.old_value, change.new_value) == ("11", "10.5")
    assert review.changes == [change]
    assert StoredField(FIELD, "10.5", unit="%") in review.fields


async def test_repeated_change_is_logged_once(tmp_path: Path) -> None:
    db = await _stored_protocol(tmp_path)
    new_field = StoredField(FIELD, "10.5", unit="%")

    first = await db.apply_change(PROTOCOL_ID, new_field, OFFER, CHANGED_AT)
    second = await db.apply_change(PROTOCOL_ID, new_field, OFFER, CHANGED_AT)

    review = await db.load_review(PROTOCOL_ID)
    assert review is not None
    assert first is not None
    assert second is None
    assert len(review.changes) == 1


async def test_rerun_keeps_an_accepted_value_and_replaces_offers(
    tmp_path: Path,
) -> None:
    db = await _stored_protocol(tmp_path)
    await db.apply_change(
        PROTOCOL_ID, StoredField(FIELD, "10.5", unit="%"), OFFER, CHANGED_AT
    )
    newer_offer = OfferedValue(FIELD, 10.0, "%", "d", "o", "newer")

    await db.save_offers(
        PROTOCOL_ID, [StoredField(FIELD, "11", unit="%")], [newer_offer]
    )

    review = await db.load_review(PROTOCOL_ID)
    assert review is not None
    assert StoredField(FIELD, "10.5", unit="%") in review.fields
    assert await db.offers_for(PROTOCOL_ID, FIELD) == [newer_offer]


async def test_data_survives_a_new_connection_object(tmp_path: Path) -> None:
    await _stored_protocol(tmp_path)

    reopened = ProtocolDb(tmp_path / "protocols.db")

    assert await reopened.has_protocol(PROTOCOL_ID)
    assert await reopened.offers_for(PROTOCOL_ID, FIELD) == [OFFER]


async def test_unusable_path_raises_a_store_error(tmp_path: Path) -> None:
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("file", encoding="utf-8")
    db = ProtocolDb(blocking_file / "protocols.db")

    with pytest.raises(ProtocolStoreError, match="protocols.db"):
        await db.has_protocol(PROTOCOL_ID)
