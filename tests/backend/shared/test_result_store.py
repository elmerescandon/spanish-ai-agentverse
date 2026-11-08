"""Tests for the generic on-disk JSON result store."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.shared.result_store import ResultStore

KEY = "protocol-content-hash"
VERSION = "code-v1"


class _Sample(BaseModel):
    name: str
    score: float


SAMPLE = _Sample(name="trial-a", score=88.5)


def _store(directory: Path, version: str = VERSION) -> ResultStore[_Sample]:
    return ResultStore(directory, _Sample, version=version)


def _only_entry(directory: Path) -> Path:
    [entry] = directory.glob("*.json")
    return entry


def test_saved_value_loads_back_equal(tmp_path: Path) -> None:
    store = _store(tmp_path)

    store.save(KEY, SAMPLE)

    assert store.load(KEY) == SAMPLE


def test_missing_key_is_a_miss(tmp_path: Path) -> None:
    assert _store(tmp_path).load(KEY) is None


def test_entry_saved_by_another_version_is_a_miss(tmp_path: Path) -> None:
    _store(tmp_path, version="code-v1").save(KEY, SAMPLE)

    assert _store(tmp_path, version="code-v2").load(KEY) is None


def test_corrupt_file_is_a_miss_and_the_next_save_replaces_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = _store(tmp_path)
    store.save(KEY, SAMPLE)
    _only_entry(tmp_path).write_text("{", encoding="utf-8")

    assert store.load(KEY) is None
    assert "result store entry unreadable" in caplog.text

    store.save(KEY, SAMPLE)
    assert store.load(KEY) == SAMPLE


@pytest.mark.parametrize(
    "content",
    [b'{"name": "x"}', b"\xff\xfe{"],
    ids=["old_schema", "invalid_utf8"],
)
def test_unparseable_entry_is_a_miss(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, content: bytes
) -> None:
    store = _store(tmp_path)
    store.save(KEY, SAMPLE)
    _only_entry(tmp_path).write_bytes(content)

    assert store.load(KEY) is None
    assert "result store entry unreadable" in caplog.text


def test_unwritable_directory_logs_and_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("file", encoding="utf-8")

    _store(blocking_file).save(KEY, SAMPLE)

    assert "result store write failed" in caplog.text


def test_save_leaves_no_temporary_files(tmp_path: Path) -> None:
    _store(tmp_path).save(KEY, SAMPLE)

    assert [path.suffix for path in tmp_path.iterdir()] == [".json"]
