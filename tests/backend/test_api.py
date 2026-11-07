"""Behavioural and edge-case tests for the backend HTTP API."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import DEMO_PROTOCOL_ID, reset_mock_state
from backend.main import app


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None]:
    """Ensure in-memory mock state is clean for every test."""
    reset_mock_state()
    yield
    reset_mock_state()


@pytest.fixture
def client() -> TestClient:
    """Return a FastAPI test client instance."""
    return TestClient(app)


def test_health_returns_ok(client: TestClient) -> None:
    """Health check endpoint returns status ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_protocols_returns_seeded_demo_protocol(
    client: TestClient,
) -> None:
    """Protocols listing contains the pre-seeded diabetes trial."""
    response = client.get("/api/protocols")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(item["protocol_id"] == DEMO_PROTOCOL_ID for item in data)


def test_create_and_fetch_protocol(client: TestClient) -> None:
    """Creating a protocol returns 201 and makes it fetchable by ID."""
    payload = {
        "title": "Oncology Phase 2 Protocol",
        "data": {"indication": "NSCLC", "phase": "Phase 2"},
    }
    create_resp = client.post("/api/protocols", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    protocol_id = created["protocol_id"]
    assert created["title"] == payload["title"]
    assert created["status"] == "uploaded"
    assert created["data"] == payload["data"]

    fetch_resp = client.get(f"/api/protocols/{protocol_id}")
    assert fetch_resp.status_code == 200
    assert fetch_resp.json() == created


def test_create_protocol_rejects_empty_title(client: TestClient) -> None:
    """Protocol creation fails validation when title is empty string."""
    response = client.post("/api/protocols", json={"title": ""})
    assert response.status_code == 422


def test_get_unknown_protocol_returns_404(client: TestClient) -> None:
    """Fetching an unregistered protocol ID yields a 404 response."""
    response = client.get("/api/protocols/proto-unknown-999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_recommendations_returns_all_pipeline_steps(
    client: TestClient,
) -> None:
    """Recommendations cover completeness, comparison, and cohort steps."""
    response = client.get(f"/api/protocols/{DEMO_PROTOCOL_ID}/recommendations")
    assert response.status_code == 200
    recs = response.json()
    assert len(recs) == 3
    steps = {r["source_step"] for r in recs}
    assert steps == {"completeness", "comparison", "cohort"}


def test_update_recommendation_decision_persists_status_and_comment(
    client: TestClient,
) -> None:
    """Updating decision status and comment modifies the recommendation."""
    list_resp = client.get(
        f"/api/protocols/{DEMO_PROTOCOL_ID}/recommendations"
    )
    first_rec = list_resp.json()[0]
    rec_id = first_rec["recommendation_id"]

    patch_payload = {
        "status": "accepted",
        "comment": "Approved by clinical team for v2 revision.",
    }
    patch_resp = client.patch(
        f"/api/protocols/{DEMO_PROTOCOL_ID}/recommendations/{rec_id}",
        json=patch_payload,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["status"] == "accepted"
    assert updated["comment"] == patch_payload["comment"]

    # Verify persistence on subsequent retrieval
    fetch_resp = client.get(
        f"/api/protocols/{DEMO_PROTOCOL_ID}/recommendations"
    )
    persisted = next(
        r for r in fetch_resp.json() if r["recommendation_id"] == rec_id
    )
    assert persisted["status"] == "accepted"
    assert persisted["comment"] == patch_payload["comment"]


def test_update_recommendation_status_only_succeeds(
    client: TestClient,
) -> None:
    """Updating status without comment field succeeds (as frontend does)."""
    list_resp = client.get(
        f"/api/protocols/{DEMO_PROTOCOL_ID}/recommendations"
    )
    first_rec = list_resp.json()[0]
    rec_id = first_rec["recommendation_id"]

    patch_resp = client.patch(
        f"/api/protocols/{DEMO_PROTOCOL_ID}/recommendations/{rec_id}",
        json={"status": "accepted"},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["status"] == "accepted"


def test_update_unknown_recommendation_returns_404(
    client: TestClient,
) -> None:
    """Updating a non-existent recommendation ID yields 404."""
    response = client.patch(
        f"/api/protocols/{DEMO_PROTOCOL_ID}/recommendations/rec-unknown-000",
        json={"status": "rejected", "comment": "Invalid item"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
