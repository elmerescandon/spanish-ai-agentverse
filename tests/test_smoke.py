"""Placeholder so CI has a test to run.

Replace with test_demo_path.py once the demo flow exists.
"""

import logging

import pytest

from backend.main import main


def test_main_starts_and_logs_startup(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    with caplog.at_level(logging.INFO):
        main()

    assert "backend started" in caplog.text
