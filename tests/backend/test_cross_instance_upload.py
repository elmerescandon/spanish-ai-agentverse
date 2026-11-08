"""Uploads must be usable from another server instance.

On Vercel the upload and the recommendation requests can land on
different instances, each with its own memory and its own SQLite file.
The tests simulate that by keeping the document store and swapping in an
empty database between the upload and the recommendation.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import agent_runners
from backend.api.routes import reset_mock_state
from backend.clients.document_store import (
    DocumentStoreError,
    set_document_store,
)
from backend.clients.protocol_db import ProtocolDb, set_protocol_db
from backend.main import app
from backend.shared.messages import ProtocolDocument
from tests.conftest import flagged_demo_comparison, make_pdf

READABLE_PAGE = (
    "This clinical trial protocol evaluates glycemic control in adults "
    "with type 2 diabetes mellitus across multiple investigative sites."
)
MISSING_PROTOCOL_ID = "proto-00000000"
RECOMMENDATION_PATHS = [
    "/api/checklist-recommendation",
    "/api/protocol-recommendation",
    "/api/cohort-recommendation",
]


@pytest.fixture(autouse=True)
def _flagged_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None]:
    monkeypatch.setattr(
        agent_runners, "compare_demo_draft", flagged_demo_comparison
    )
    reset_mock_state()
    yield
    reset_mock_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _upload(client: TestClient, tmp_path: Path) -> str:
    pdf_path = make_pdf(tmp_path, [READABLE_PAGE])
    response = client.post(
        "/api/upload-file",
        files={
            "file": ("trial.pdf", pdf_path.read_bytes(), "application/pdf")
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["protocol_id"])


def _switch_to_another_instance(tmp_path: Path) -> None:
    """A new instance: same shared document store, empty local database."""
    set_protocol_db(ProtocolDb(tmp_path / "other-instance.db"))


def test_protocol_comparison_works_on_an_instance_that_did_not_upload(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)
    _switch_to_another_instance(tmp_path)

    response = client.post(
        "/api/protocol-recommendation", json={"protocol_id": protocol_id}
    )

    assert response.status_code == 200, response.text


def test_cohort_and_checklist_work_on_an_instance_that_did_not_upload(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)
    _switch_to_another_instance(tmp_path)

    for path in (
        "/api/checklist-recommendation",
        "/api/cohort-recommendation",
    ):
        response = client.post(path, json={"protocol_id": protocol_id})
        assert response.status_code != 404, (path, response.text)


@pytest.mark.parametrize("path", RECOMMENDATION_PATHS)
def test_unknown_protocol_id_is_still_answered_with_404(
    client: TestClient, path: str
) -> None:
    response = client.post(path, json={"protocol_id": MISSING_PROTOCOL_ID})

    assert response.status_code == 404
    assert MISSING_PROTOCOL_ID in response.json()["detail"]


class FailingDocumentStore:
    async def save(self, document: ProtocolDocument) -> None:
        raise DocumentStoreError("blob down")

    async def load(self, protocol_id: str) -> ProtocolDocument | None:
        raise DocumentStoreError(f"blob down for {protocol_id}")


def test_store_outage_is_answered_with_503_not_a_false_404(
    client: TestClient,
) -> None:
    set_document_store(FailingDocumentStore())

    response = client.post(
        "/api/protocol-recommendation",
        json={"protocol_id": MISSING_PROTOCOL_ID},
    )

    assert response.status_code == 503
    assert "document store failed" in response.json()["detail"]
