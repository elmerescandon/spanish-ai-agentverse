"""Tests for the generic on-disk JSON result store."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.shared.result_store import ResultStore

KEY = "ab" * 32


class _Sample(BaseModel):
    name: str
    score: float


def test_saved_value_loads_back_equal(tmp_path: Path) -> None:
    store = ResultStore(tmp_path, _Sample)
    sample = _Sample(name="trial-a", score=88.5)

    store.save(KEY, sample)

    assert store.load(KEY) == sample


def test_missing_key_is_a_miss(tmp_path: Path) -> None:
    store = ResultStore(tmp_path, _Sample)

    assert store.load(KEY) is None


def test_corrupt_file_is_a_miss_and_the_next_save_replaces_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = ResultStore(tmp_path, _Sample)
    entry_path = tmp_path / f"{KEY}.json"
    entry_path.write_text("{", encoding="utf-8")
    sample = _Sample(name="trial-b", score=92.0)

    assert store.load(KEY) is None
    assert "result store entry unreadable" in caplog.text

    store.save(KEY, sample)
    assert store.load(KEY) == sample


def test_entry_from_an_old_schema_is_a_miss(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = ResultStore(tmp_path, _Sample)
    entry_path = tmp_path / f"{KEY}.json"
    entry_path.write_text('{"name": "x"}', encoding="utf-8")

    assert store.load(KEY) is None
    assert "result store entry unreadable" in caplog.text


def test_unwritable_directory_logs_and_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("file", encoding="utf-8")
    store = ResultStore(blocking_file, _Sample)
    sample = _Sample(name="trial-c", score=75.0)

    store.save(KEY, sample)

    assert "result store write failed" in caplog.text


def test_save_leaves_no_temporary_files(tmp_path: Path) -> None:
    store = ResultStore(tmp_path, _Sample)
    sample = _Sample(name="trial-d", score=95.0)

    store.save(KEY, sample)

    names = sorted(path.name for path in tmp_path.iterdir())
    assert names == [f"{KEY}.json"]


def test_entry_with_invalid_utf8_is_a_miss(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = ResultStore(tmp_path, _Sample)
    (tmp_path / f"{KEY}.json").write_bytes(b"\xff\xfe{")

    assert store.load(KEY) is None
    assert "result store entry unreadable" in caplog.text
