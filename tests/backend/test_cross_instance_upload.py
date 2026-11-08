"""Uploads and reviews must be usable from another server instance.

On Vercel every request can land on a different instance, each with its
own memory and disk. The tests simulate that with fresh Blob-backed
stores over one shared fake Blob backend, as a new instance would build.
"""

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agents.protocol_comparison.comparison import Category
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.api import agent_runners
from backend.api.protocol_fields import comparison_field, format_number
from backend.api.routes import reset_mock_state
from backend.clients.document_store import (
    BlobDocumentStore,
    DocumentStoreError,
    set_document_store,
)
from backend.clients.protocol_blob_store import BlobProtocolStore
from backend.clients.protocol_db import get_protocol_db, set_protocol_db
from backend.main import app
from backend.shared.messages import ProtocolDocument
from tests.conftest import (
    OFFERED_HBA1C_VALUES,
    flagged_demo_comparison,
    make_pdf,
    out_of_line_demo_comparison,
)
from tests.fake_blob import FakeBlobBackend

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
HBA1C_FIELD = comparison_field(DimensionId.HBA1C_UPPER_BOUND)
RECENT_VALUE = OFFERED_HBA1C_VALUES[Category.RECENT]


def _switch_to_another_instance() -> None:
    """A new instance: empty memory, same shared Blob storage."""
    set_document_store(BlobDocumentStore())
    set_protocol_db(BlobProtocolStore())


@pytest.fixture(autouse=True)
def _flagged_comparison(
    monkeypatch: pytest.MonkeyPatch, fake_blob: FakeBlobBackend
) -> Generator[None]:
    monkeypatch.setattr(
        agent_runners, "compare_demo_draft", flagged_demo_comparison
    )
    reset_mock_state()
    _switch_to_another_instance()
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


def _run_peers(client: TestClient, protocol_id: str) -> None:
    response = client.post(
        "/api/protocol-recommendation", json={"protocol_id": protocol_id}
    )
    assert response.status_code == 200, response.text


def _accept(
    client: TestClient, protocol_id: str, field: str, value: float
) -> int:
    response = client.post(
        f"/api/protocols/{protocol_id}/changes",
        json={"field": field, "value": value},
    )
    return response.status_code


def _review(client: TestClient, protocol_id: str) -> dict[str, object]:
    response = client.get(f"/api/protocols/{protocol_id}/fields")
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _field_values(body: dict[str, object]) -> dict[str, str]:
    fields = body["fields"]
    assert isinstance(fields, list)
    return {item["field"]: item["value"] for item in fields}


def _first_offered_value(protocol_id: str, field: str) -> float:
    offers = asyncio.run(get_protocol_db().offers_for(protocol_id, field))
    assert offers, field
    return offers[0].value


def test_protocol_comparison_works_on_an_instance_that_did_not_upload(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)
    _switch_to_another_instance()

    response = client.post(
        "/api/protocol-recommendation", json={"protocol_id": protocol_id}
    )

    assert response.status_code == 200, response.text


def test_cohort_and_checklist_work_on_an_instance_that_did_not_upload(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)
    _switch_to_another_instance()

    for path in (
        "/api/checklist-recommendation",
        "/api/cohort-recommendation",
    ):
        response = client.post(path, json={"protocol_id": protocol_id})
        assert response.status_code != 404, (path, response.text)


def test_review_flow_spans_four_instances(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)
    _switch_to_another_instance()
    _run_peers(client, protocol_id)
    _switch_to_another_instance()
    assert _accept(client, protocol_id, HBA1C_FIELD, RECENT_VALUE) == 200
    _switch_to_another_instance()

    body = _review(client, protocol_id)

    assert _field_values(body)[HBA1C_FIELD] == format_number(RECENT_VALUE)
    changes = body["changes"]
    assert isinstance(changes, list)
    assert [(c["field"], c["new_value"]) for c in changes] == [
        (HBA1C_FIELD, format_number(RECENT_VALUE))
    ]


def test_accepts_of_different_fields_from_two_instances_are_both_kept(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_runners, "compare_demo_draft", out_of_line_demo_comparison
    )
    protocol_id = _upload(client, tmp_path)
    _run_peers(client, protocol_id)
    fields = [
        comparison_field(DimensionId.MINIMUM_AGE),
        comparison_field(DimensionId.ENROLLMENT),
    ]
    offered = {f: _first_offered_value(protocol_id, f) for f in fields}

    for field in fields:
        _switch_to_another_instance()
        assert _accept(client, protocol_id, field, offered[field]) == 200

    _switch_to_another_instance()
    body = _review(client, protocol_id)
    current = _field_values(body)
    changes = body["changes"]
    assert isinstance(changes, list)
    assert sorted(c["field"] for c in changes) == sorted(fields)
    for field in fields:
        assert current[field] == format_number(offered[field])


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
