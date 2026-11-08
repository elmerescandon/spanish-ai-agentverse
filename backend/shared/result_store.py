"""Generic on-disk JSON store for Pydantic models."""

import hashlib
import logging
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

logger = logging.getLogger(__name__)

LOGGED_KEY_LENGTH = 12  # enough of a key to tell entries apart in logs


class ResultStore[ModelT: BaseModel]:
    """On-disk JSON store for one Pydantic model type and code version.

    Entries are filed under a hash of the version and the key, so entries
    written by a different version are never read. Read, validation and
    write failures are logged and never raised, so a corrupt or unwritable
    cache only costs a fresh re-run.
    """

    def __init__(
        self, directory: Path, model: type[ModelT], version: str
    ) -> None:
        self._directory = directory
        self._model = model
        self._version = version

    def _entry_path(self, key: str) -> Path:
        name = hashlib.sha256(f"{self._version}:{key}".encode()).hexdigest()
        return self._directory / f"{name}.json"

    def load(self, key: str) -> ModelT | None:
        """Return the stored model for key, or None on a miss."""
        try:
            text = self._entry_path(key).read_text(encoding="utf-8")
            value = self._model.model_validate_json(text)
        except FileNotFoundError:
            return None
        # ValueError covers invalid UTF-8 and pydantic's ValidationError.
        except (OSError, ValueError) as error:
            logger.warning(
                "result store entry unreadable, ignoring: store=%s "
                "key=%s error=%r",
                self._directory.name,
                key[:LOGGED_KEY_LENGTH],
                error,
            )
            return None
        logger.info(
            "result store hit: store=%s key=%s",
            self._directory.name,
            key[:LOGGED_KEY_LENGTH],
        )
        return value

    def save(self, key: str, value: ModelT) -> None:
        """Atomically write value as JSON under key; log and ignore errors."""
        entry_path = self._entry_path(key)
        # A unique temp name, so concurrent saves never share a file.
        temp_path = entry_path.with_name(
            f"{entry_path.stem}.{uuid4().hex}.tmp"
        )
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(value.model_dump_json(), encoding="utf-8")
            temp_path.replace(entry_path)
        except OSError as error:
            logger.warning(
                "result store write failed: store=%s key=%s error=%r",
                self._directory.name,
                key[:LOGGED_KEY_LENGTH],
                error,
            )
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)
