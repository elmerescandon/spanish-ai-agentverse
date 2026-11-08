"""SQLite store for protocol fields, offered values and accepted changes.

All SQL lives here. Every call opens its own connection in a worker
thread, so the event loop never blocks and no connection is shared
between threads. The database is the record of the review, so errors are
raised as ProtocolStoreError, never swallowed.
"""

import asyncio
import logging
import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.shared.config import load_settings

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_SECONDS = 10.0  # wait for another writer instead of failing
FIELD_COLUMNS = "(protocol_id, field, value, unit, page)"
UPSERT_FIELD_SQL = (
    f"INSERT OR REPLACE INTO protocol_fields {FIELD_COLUMNS} "
    "VALUES (?, ?, ?, ?, ?)"
)
INSERT_NEW_FIELD_SQL = (
    f"INSERT OR IGNORE INTO protocol_fields {FIELD_COLUMNS} "
    "VALUES (?, ?, ?, ?, ?)"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS protocols (
    protocol_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS protocol_fields (
    protocol_id TEXT NOT NULL REFERENCES protocols(protocol_id),
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    unit TEXT,
    page INTEGER,
    PRIMARY KEY (protocol_id, field)
);
CREATE TABLE IF NOT EXISTS offered_values (
    protocol_id TEXT NOT NULL REFERENCES protocols(protocol_id),
    field TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    decision_id TEXT NOT NULL,
    option_id TEXT NOT NULL,
    rationale TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS field_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol_id TEXT NOT NULL REFERENCES protocols(protocol_id),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    option_id TEXT NOT NULL,
    rationale TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
"""


class ProtocolStoreError(RuntimeError):
    """Raised when the protocol database cannot be read or written."""


@dataclass(frozen=True)
class ProtocolRecord:
    """An uploaded protocol's identity."""

    protocol_id: str
    title: str
    page_count: int
    uploaded_at: datetime


@dataclass(frozen=True)
class StoredField:
    """One named field of a protocol, as short text."""

    field: str
    value: str
    unit: str | None = None
    page: int | None = None


@dataclass(frozen=True)
class OfferedValue:
    """A value an agent proposed for a field, from real data."""

    field: str
    value: float
    unit: str | None
    decision_id: str
    option_id: str
    rationale: str


@dataclass(frozen=True)
class FieldChangeRecord:
    """One change a reviewer accepted."""

    change_id: int
    field: str
    old_value: str | None
    new_value: str
    decision_id: str
    option_id: str
    rationale: str
    changed_at: datetime


@dataclass(frozen=True)
class ProtocolReview:
    """A protocol's current fields and the changes accepted so far."""

    protocol: ProtocolRecord
    fields: list[StoredField]
    changes: list[FieldChangeRecord]


def _change_from_row(
    row: sqlite3.Row | tuple[object, ...],
) -> FieldChangeRecord:
    (
        change_id,
        field,
        old_value,
        new_value,
        decision_id,
        option_id,
        rationale,
        changed_at,
    ) = row
    return FieldChangeRecord(
        change_id=int(str(change_id)),
        field=str(field),
        old_value=None if old_value is None else str(old_value),
        new_value=str(new_value),
        decision_id=str(decision_id),
        option_id=str(option_id),
        rationale=str(rationale),
        changed_at=datetime.fromisoformat(str(changed_at)),
    )


class ProtocolDb:
    """Async access to the protocol review database at one path."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def _run[ResultT](
        self, operation: Callable[[sqlite3.Connection], ResultT]
    ) -> ResultT:
        """Run operation in one transaction on a worker thread.

        Raises:
            ProtocolStoreError: SQLite or the file system failed.
        """

        def run_in_thread() -> ResultT:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with closing(
                sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_SECONDS)
            ) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.executescript(SCHEMA)
                with connection:
                    return operation(connection)

        try:
            return await asyncio.to_thread(run_in_thread)
        except (sqlite3.Error, OSError) as error:
            logger.exception("protocol database failed: path=%s", self._path)
            raise ProtocolStoreError(
                f"protocol database at {self._path} failed: {error}"
            ) from error

    async def save_protocol(
        self, record: ProtocolRecord, fields: Sequence[StoredField]
    ) -> None:
        """Store an uploaded protocol and its parsed fields."""

        def save(connection: sqlite3.Connection) -> None:
            connection.execute(
                "INSERT OR REPLACE INTO protocols VALUES (?, ?, ?, ?)",
                (
                    record.protocol_id,
                    record.title,
                    record.page_count,
                    record.uploaded_at.isoformat(),
                ),
            )
            connection.executemany(
                UPSERT_FIELD_SQL,
                [
                    (
                        record.protocol_id,
                        item.field,
                        item.value,
                        item.unit,
                        item.page,
                    )
                    for item in fields
                ],
            )

        await self._run(save)
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

        A starting field is written only if the field does not exist yet,
        so a re-run never overwrites a change the reviewer accepted. The
        offers replace the protocol's previous offers.
        """

        def save(connection: sqlite3.Connection) -> None:
            connection.executemany(
                INSERT_NEW_FIELD_SQL,
                [
                    (protocol_id, item.field, item.value, item.unit, item.page)
                    for item in starting_fields
                ],
            )
            connection.execute(
                "DELETE FROM offered_values WHERE protocol_id = ?",
                (protocol_id,),
            )
            connection.executemany(
                "INSERT INTO offered_values VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        protocol_id,
                        offer.field,
                        offer.value,
                        offer.unit,
                        offer.decision_id,
                        offer.option_id,
                        offer.rationale,
                    )
                    for offer in offers
                ],
            )

        await self._run(save)
        logger.info(
            "offers stored: protocol_id=%s starting_fields=%d offers=%d",
            protocol_id,
            len(starting_fields),
            len(offers),
        )

    async def has_protocol(self, protocol_id: str) -> bool:
        """True if the protocol was uploaded and stored."""
        return await self._run(
            lambda connection: (
                connection.execute(
                    "SELECT 1 FROM protocols WHERE protocol_id = ?",
                    (protocol_id,),
                ).fetchone()
                is not None
            )
        )

    async def offers_for(
        self, protocol_id: str, field: str
    ) -> list[OfferedValue]:
        """The values currently offered for one field of a protocol."""
        rows = await self._run(
            lambda connection: connection.execute(
                "SELECT field, value, unit, decision_id, option_id, "
                "rationale FROM offered_values "
                "WHERE protocol_id = ? AND field = ?",
                (protocol_id, field),
            ).fetchall()
        )
        return [OfferedValue(*row) for row in rows]

    async def apply_change(
        self,
        protocol_id: str,
        new_field: StoredField,
        offer: OfferedValue,
        changed_at: datetime,
    ) -> FieldChangeRecord | None:
        """Set a field to an offered value and log the change.

        Returns None, and logs nothing, when the field already holds the
        value, so a retried request never records the change twice.
        """

        def apply(connection: sqlite3.Connection) -> FieldChangeRecord | None:
            row = connection.execute(
                "SELECT value FROM protocol_fields "
                "WHERE protocol_id = ? AND field = ?",
                (protocol_id, new_field.field),
            ).fetchone()
            old_value = None if row is None else str(row[0])
            if old_value == new_field.value:
                return None
            connection.execute(
                UPSERT_FIELD_SQL,
                (
                    protocol_id,
                    new_field.field,
                    new_field.value,
                    new_field.unit,
                    new_field.page,
                ),
            )
            cursor = connection.execute(
                "INSERT INTO field_changes (protocol_id, field, old_value, "
                "new_value, decision_id, option_id, rationale, changed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    protocol_id,
                    new_field.field,
                    old_value,
                    new_field.value,
                    offer.decision_id,
                    offer.option_id,
                    offer.rationale,
                    changed_at.isoformat(),
                ),
            )
            assert cursor.lastrowid is not None
            return FieldChangeRecord(
                change_id=cursor.lastrowid,
                field=new_field.field,
                old_value=old_value,
                new_value=new_field.value,
                decision_id=offer.decision_id,
                option_id=offer.option_id,
                rationale=offer.rationale,
                changed_at=changed_at,
            )

        change = await self._run(apply)
        logger.info(
            "field change: protocol_id=%s field=%s value=%s is_new=%s",
            protocol_id,
            new_field.field,
            new_field.value,
            change is not None,
        )
        return change

    async def load_review(self, protocol_id: str) -> ProtocolReview | None:
        """A protocol's fields and accepted changes; None if unknown."""

        def load(connection: sqlite3.Connection) -> ProtocolReview | None:
            protocol_row = connection.execute(
                "SELECT protocol_id, title, page_count, uploaded_at "
                "FROM protocols WHERE protocol_id = ?",
                (protocol_id,),
            ).fetchone()
            if protocol_row is None:
                return None
            field_rows = connection.execute(
                "SELECT field, value, unit, page FROM protocol_fields "
                "WHERE protocol_id = ? ORDER BY field",
                (protocol_id,),
            ).fetchall()
            change_rows = connection.execute(
                "SELECT change_id, field, old_value, new_value, "
                "decision_id, option_id, rationale, changed_at "
                "FROM field_changes WHERE protocol_id = ? "
                "ORDER BY change_id",
                (protocol_id,),
            ).fetchall()
            title, page_count, uploaded_at = protocol_row[1:]
            return ProtocolReview(
                protocol=ProtocolRecord(
                    protocol_id=protocol_id,
                    title=title,
                    page_count=page_count,
                    uploaded_at=datetime.fromisoformat(uploaded_at),
                ),
                fields=[StoredField(*row) for row in field_rows],
                changes=[_change_from_row(row) for row in change_rows],
            )

        return await self._run(load)


_protocol_db: ProtocolDb | None = None


def get_protocol_db() -> ProtocolDb:
    """The app's database, at the configured path, created on first use."""
    global _protocol_db
    if _protocol_db is None:
        _protocol_db = ProtocolDb(load_settings().protocol_db_path)
    return _protocol_db


def set_protocol_db(protocol_db: ProtocolDb | None) -> None:
    """Replace the app's database (tests); None resets it."""
    global _protocol_db
    _protocol_db = protocol_db
