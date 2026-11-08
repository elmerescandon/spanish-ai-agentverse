"""Tests for the /demo upload and per-step recommendation endpoints."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import reset_mock_state
from backend.main import app
from tests.conftest import make_pdf

STEP_ROUTES = {
    "/api/checklist-recommendation": "check",
    "/api/protocol-recommendation": "peers",
    "/api/cohort-recommendation": "cohort",
}
READABLE_PAGE = (
    "This clinical trial protocol evaluates glycemic control in adults "
    "with type 2 diabetes mellitus across multiple investigative sites."
)


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None]:
    reset_mock_state()
    yield
    reset_mock_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def upload_pdf(client: TestClient, tmp_path: Path) -> dict[str, object]:
    """Upload a small readable PDF and return the JSON body."""
    pdf_path = make_pdf(tmp_path, [READABLE_PAGE, READABLE_PAGE])
    response = client.post(
        "/api/upload-file",
        files={
            "file": ("my_trial.pdf", pdf_path.read_bytes(), "application/pdf")
        },
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_upload_valid_pdf_returns_protocol_id_and_ingest_step(
    client: TestClient, tmp_path: Path
) -> None:
    body = upload_pdf(client, tmp_path)
    assert str(body["protocol_id"]).startswith("proto-")
    assert body["title"] == "my_trial"
    assert body["page_count"] == 2
    step = body["step"]
    assert isinstance(step, dict)
    assert step["id"] == "ingest"
    assert body["filename"] == "my_trial.pdf"
    assert isinstance(body["file_size_bytes"], int)
    assert body["file_size_bytes"] > 0


def test_step_optional_fields_default_to_empty_for_mock_runner(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]
    step = client.post(
        "/api/checklist-recommendation", json={"protocol_id": protocol_id}
    ).json()
    assert step["status"] == "completed"
    assert step["warnings"] == []
    assert step["tables"] == []
    assert step["charts"] == []
    assert step["details"] == {}
    decision = step["decisions"][0]
    assert decision["review_status"] == "pending"
    assert decision["options"] == []


def test_upload_non_pdf_is_rejected_with_expected_and_received(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/upload-file",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415
    assert "expected a PDF" in response.json()["detail"]
    assert "notes.txt" in response.json()["detail"]


def test_upload_pdf_named_file_without_pdf_bytes_is_rejected(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/upload-file",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 415


def test_upload_empty_file_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/upload-file",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 422
    assert "0 bytes" in response.json()["detail"]


def test_upload_pdf_without_text_is_rejected_as_unreadable(
    client: TestClient, tmp_path: Path
) -> None:
    pdf_path = make_pdf(tmp_path, [""])
    response = client.post(
        "/api/upload-file",
        files={"file": ("scan.pdf", pdf_path.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(("route", "step_id"), STEP_ROUTES.items())
def test_recommendation_route_returns_its_step_for_uploaded_protocol(
    client: TestClient, tmp_path: Path, route: str, step_id: str
) -> None:
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]
    response = client.post(route, json={"protocol_id": protocol_id})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == step_id
    assert body["decisions"]
    assert all(d["step_id"] == step_id for d in body["decisions"])


@pytest.mark.parametrize("route", STEP_ROUTES)
def test_recommendation_route_unknown_protocol_returns_404_with_id(
    client: TestClient, route: str
) -> None:
    response = client.post(route, json={"protocol_id": "proto-missing"})
    assert response.status_code == 404
    assert "proto-missing" in response.json()["detail"]


@pytest.mark.parametrize("route", STEP_ROUTES)
def test_recommendation_route_empty_protocol_id_returns_422(
    client: TestClient, route: str
) -> None:
    response = client.post(route, json={"protocol_id": ""})
    assert response.status_code == 422


@pytest.mark.parametrize("route", STEP_ROUTES)
def test_recommendation_route_called_twice_returns_same_result(
    client: TestClient, tmp_path: Path, route: str
) -> None:
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]
    first = client.post(route, json={"protocol_id": protocol_id})
    second = client.post(route, json={"protocol_id": protocol_id})
    assert first.json() == second.json()
