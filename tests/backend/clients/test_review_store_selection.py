"""get_protocol_db picks the shared Blob store on Vercel, else SQLite."""

from collections.abc import Generator
from pathlib import Path

import pytest

from backend.clients import protocol_db
from backend.clients.document_store import BLOB_TOKEN_ENV_VAR
from backend.clients.protocol_blob_store import BlobProtocolStore
from backend.clients.protocol_db import (
    ProtocolDb,
    get_protocol_db,
    set_protocol_db,
)
from backend.shared.config import Settings


@pytest.fixture(autouse=True)
def _fresh_selection() -> Generator[None]:
    set_protocol_db(None)
    yield
    set_protocol_db(None)


def _use_database_path(
    monkeypatch: pytest.MonkeyPatch, database_path: Path
) -> None:
    monkeypatch.setattr(
        protocol_db,
        "load_settings",
        lambda: Settings(_env_file=None, protocol_db_path=database_path),
    )


def test_blob_store_is_chosen_when_the_blob_token_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BLOB_TOKEN_ENV_VAR, "test-token")

    assert isinstance(get_protocol_db(), BlobProtocolStore)


def test_sqlite_is_chosen_when_the_blob_token_is_not_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(BLOB_TOKEN_ENV_VAR, raising=False)
    _use_database_path(monkeypatch, tmp_path / "review.db")

    assert isinstance(get_protocol_db(), ProtocolDb)


def test_the_chosen_store_is_reused_between_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(BLOB_TOKEN_ENV_VAR, raising=False)
    _use_database_path(monkeypatch, tmp_path / "review.db")

    assert get_protocol_db() is get_protocol_db()
