"""Tests for the /demo upload and per-step recommendation endpoints."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agents.completeness.rules import load_rule_catalogue
from backend.agents.protocol_comparison.demo import DemoComparison
from backend.agents.protocol_comparison.peer_store import PeerStoreError
from backend.api import agent_runners, routes
from backend.api.protocol_pipeline import (
    AnalysisFailedError,
    CheckRun,
    set_protocol_pipeline,
)
from backend.api.routes import reset_mock_state
from backend.main import app
from backend.shared.messages import ProtocolDocument
from tests.conftest import (
    EmptyAnswersLlm,
    OfflineProtocolPipeline,
    make_pdf,
)

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


def test_check_step_reports_rules_with_evidence_and_review_fields(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]
    step = client.post(
        "/api/checklist-recommendation", json={"protocol_id": protocol_id}
    ).json()
    assert step["agent"] == "Completeness"
    assert step["headline"]["unit"] == "/100"
    labels = [metric["label"] for metric in step["metrics"]]
    assert labels[:4] == ["Present", "Weak", "Missing", "Contradictions"]
    [checklist] = step["tables"]
    rule_count = len(load_rule_catalogue().rules)
    assert len(checklist["rows"]) == rule_count
    assert step["duration_ms"] is not None
    for decision in step["decisions"]:
        assert decision["review_status"] == "pending"
        assert decision["options"] == []
        assert decision["proposed_change"] is None
        evidence_ids = {item["evidence_id"] for item in decision["evidence"]}
        for entry in decision["trace"]:
            assert set(entry["evidence_ids"]) <= evidence_ids


class _FailingPipeline(OfflineProtocolPipeline):
    """Pipeline whose analysis fails, as when Gemini is not configured."""

    async def parse(self, pdf_path: Path) -> ProtocolDocument:
        raise AnalysisFailedError("GEMINI_API_KEY is not set")

    async def check(self, document: ProtocolDocument) -> CheckRun:
        raise AnalysisFailedError("GEMINI_API_KEY is not set")


def test_check_failure_returns_503_with_the_reason(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]
    set_protocol_pipeline(_FailingPipeline())

    response = client.post(
        "/api/checklist-recommendation", json={"protocol_id": protocol_id}
    )

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_upload_parse_failure_returns_503_with_the_reason(
    client: TestClient, tmp_path: Path
) -> None:
    set_protocol_pipeline(_FailingPipeline())
    pdf_path = make_pdf(tmp_path, [READABLE_PAGE])

    response = client.post(
        "/api/upload-file",
        files={
            "file": ("trial.pdf", pdf_path.read_bytes(), "application/pdf")
        },
    )

    assert response.status_code == 503
    assert "protocol analysis failed" in response.json()["detail"]


class _RecordingPipeline(OfflineProtocolPipeline):
    """Offline pipeline that records which documents a check started for."""

    def __init__(self) -> None:
        super().__init__()
        self.started_protocol_ids: list[str] = []

    def start_check(self, document: ProtocolDocument) -> None:
        self.started_protocol_ids.append(document.protocol_id)


def test_upload_starts_the_check_for_the_stored_protocol(
    client: TestClient, tmp_path: Path
) -> None:
    pipeline = _RecordingPipeline()
    set_protocol_pipeline(pipeline)

    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]

    assert pipeline.started_protocol_ids == [protocol_id]


def test_upload_over_the_size_limit_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(routes, "MAX_UPLOAD_BYTES", 10)
    pdf_path = make_pdf(tmp_path, [READABLE_PAGE])

    response = client.post(
        "/api/upload-file",
        files={
            "file": ("trial.pdf", pdf_path.read_bytes(), "application/pdf")
        },
    )

    assert response.status_code == 413


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
    # A complete check is reused; an incomplete one reruns by design.
    set_protocol_pipeline(OfflineProtocolPipeline(llm=EmptyAnswersLlm()))
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]
    first = client.post(route, json={"protocol_id": protocol_id})
    second = client.post(route, json={"protocol_id": protocol_id})
    assert first.json() == second.json()


def test_check_with_failed_gemini_calls_warns_to_retry(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]

    body = client.post(
        "/api/checklist-recommendation", json={"protocol_id": protocol_id}
    ).json()

    assert "gemini_calls_failed" in {w["code"] for w in body["warnings"]}


def test_protocol_recommendation_serves_the_comparison_agent(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]
    body = client.post(
        "/api/protocol-recommendation", json={"protocol_id": protocol_id}
    ).json()
    assert body["agent"] == "protocol_comparison"
    assert body["data_sources"][0]["source"] == "aact"
    assert body["data_sources"][0]["record_count"] > 0
    assert all(
        decision["decision_id"].startswith("comparison-")
        for decision in body["decisions"]
    )


def test_protocol_recommendation_returns_500_when_peer_cache_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def missing_peers() -> DemoComparison:
        raise PeerStoreError("expected cached demo peers, found none")

    monkeypatch.setattr(agent_runners, "compare_demo_draft", missing_peers)
    client = TestClient(app, raise_server_exceptions=False)
    protocol_id = upload_pdf(client, tmp_path)["protocol_id"]
    response = client.post(
        "/api/protocol-recommendation", json={"protocol_id": protocol_id}
    )
    assert response.status_code == 500
