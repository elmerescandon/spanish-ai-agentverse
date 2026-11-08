"""Generic on-disk JSON store for Pydantic models."""

import logging
import re
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

logger = logging.getLogger(__name__)

SHA256_KEY_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LOG_KEY_PREFIX_LENGTH = 12


class ResultStore[ModelT: BaseModel]:
    """On-disk JSON store for one Pydantic model type.

    Read, validation, and write failures are logged as warnings and never
    raised, so a corrupt or unwritable cache only costs a fresh re-run.
    """

    def __init__(self, directory: Path, model: type[ModelT]) -> None:
        self._directory = directory
        self._model = model

    def _entry_path(self, key: str) -> Path:
        assert SHA256_KEY_PATTERN.match(key) is not None, (
            f"key must be a 64-character lowercase hex sha256, got {key!r}"
        )
        return self._directory / f"{key}.json"

    def load(self, key: str) -> ModelT | None:
        """Load and validate the cached model for key, or return None."""
        entry_path = self._entry_path(key)
        try:
            text = entry_path.read_text(encoding="utf-8")
            return self._model.model_validate_json(text)
        except FileNotFoundError:
            return None
        # ValueError covers invalid UTF-8 and pydantic's ValidationError.
        except (OSError, ValueError) as error:
            logger.warning(
                "result store entry unreadable, ignoring: store=%s "
                "key=%s error=%r",
                self._directory.name,
                key[:LOG_KEY_PREFIX_LENGTH],
                error,
            )
            return None

    def save(self, key: str, value: ModelT) -> None:
        """Atomically write value as JSON under key; log and ignore errors."""
        entry_path = self._entry_path(key)
        temp_path = self._directory / f"{key}.{uuid4().hex}.tmp"
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(value.model_dump_json(), encoding="utf-8")
            temp_path.replace(entry_path)
        except OSError as error:
            logger.warning(
                "result store write failed: store=%s key=%s error=%r",
                self._directory.name,
                key[:LOG_KEY_PREFIX_LENGTH],
                error,
            )
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)
