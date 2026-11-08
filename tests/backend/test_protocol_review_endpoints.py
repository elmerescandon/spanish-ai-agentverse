"""Tests for storing protocols, accepting changes and the final pull."""

import asyncio
import io
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.agents.protocol_comparison.comparison import Category
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.api import agent_runners
from backend.api.protocol_fields import comparison_field, format_number
from backend.api.routes import reset_mock_state
from backend.clients.protocol_db import (
    ProtocolDb,
    get_protocol_db,
    set_protocol_db,
)
from backend.main import app
from tests.conftest import (
    OFFERED_HBA1C_VALUES,
    flagged_demo_comparison,
    make_pdf,
    out_of_line_demo_comparison,
)

READABLE_PAGE = (
    "This clinical trial protocol evaluates glycemic control in adults "
    "with type 2 diabetes mellitus across multiple investigative sites."
)
HBA1C_FIELD = comparison_field(DimensionId.HBA1C_UPPER_BOUND)
RECENT_VALUE = OFFERED_HBA1C_VALUES[Category.RECENT]


@pytest.fixture(autouse=True)
def _flagged_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None]:
    """The PEERS step offers HbA1c values, and mock state starts clean."""
    monkeypatch.setattr(
        agent_runners, "compare_with_registry_peers", flagged_demo_comparison
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


def _run_peers(client: TestClient, protocol_id: str) -> None:
    response = client.post(
        "/api/protocol-recommendation", json={"protocol_id": protocol_id}
    )
    assert response.status_code == 200, response.text


def _accept(
    client: TestClient, protocol_id: str, field: str, value: float
) -> httpx.Response:
    return client.post(
        f"/api/protocols/{protocol_id}/changes",
        json={"field": field, "value": value},
    )


def _offers_by_field(
    client: TestClient, protocol_id: str
) -> dict[str, list[float]]:
    """The distinct values offered per field, read back from the database."""
    review = asyncio.run(get_protocol_db().load_review(protocol_id))
    assert review is not None
    offers: dict[str, list[float]] = {}
    for field in {f.field for f in review.fields}:
        values = asyncio.run(get_protocol_db().offers_for(protocol_id, field))
        distinct = sorted({offer.value for offer in values}, reverse=True)
        if distinct:
            offers[field] = distinct
    return offers


def _fields(client: TestClient, protocol_id: str) -> dict[str, object]:
    response = client.get(f"/api/protocols/{protocol_id}/fields")
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _field_values(body: dict[str, object]) -> dict[str, str]:
    fields = body["fields"]
    assert isinstance(fields, list)
    return {item["field"]: item["value"] for item in fields}


def test_upload_stores_the_protocol(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)

    body = _fields(client, protocol_id)

    assert body["protocol_id"] == protocol_id
    assert body["title"] == "trial"
    assert body["changes"] == []


def test_peers_step_stores_the_comparison_fields_at_draft_values(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)

    _run_peers(client, protocol_id)

    assert _field_values(_fields(client, protocol_id))[HBA1C_FIELD] == "11"


def test_accepted_value_updates_the_field_and_is_logged_once(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)
    _run_peers(client, protocol_id)

    first = _accept(client, protocol_id, HBA1C_FIELD, RECENT_VALUE)
    retry = _accept(client, protocol_id, HBA1C_FIELD, RECENT_VALUE)

    assert first.status_code == 200, first.text
    assert first.json()["field"]["value"] == "10"
    change = first.json()["change"]
    assert (change["old_value"], change["new_value"]) == ("11", "10")
    assert change["option_id"].endswith("-recent")
    assert retry.status_code == 200
    assert retry.json()["change"] is None
    body = _fields(client, protocol_id)
    assert _field_values(body)[HBA1C_FIELD] == "10"
    assert body["changes"] == [change]


def test_peers_rerun_keeps_an_accepted_value(
    client: TestClient, tmp_path: Path
) -> None:
    protocol_id = _upload(client, tmp_path)
    _run_peers(client, protocol_id)
    _accept(client, protocol_id, HBA1C_FIELD, RECENT_VALUE)

    _run_peers(client, protocol_id)

    assert _field_values(_fields(client, protocol_id))[HBA1C_FIELD] == "10"


@pytest.mark.parametrize(
    ("field", "value", "runs_peers", "message"),
    [
        ("design.phase", 3.0, True, "expected field to be one of"),
        (HBA1C_FIELD, 9.0, True, "expected one of the offered values"),
        (HBA1C_FIELD, RECENT_VALUE, False, "run the PEERS step"),
    ],
    ids=["field_not_changeable", "value_not_offered", "peers_not_run"],
)
def test_change_that_was_not_offered_is_rejected_with_the_reason(
    client: TestClient,
    tmp_path: Path,
    field: str,
    value: float,
    runs_peers: bool,
    message: str,
) -> None:
    protocol_id = _upload(client, tmp_path)
    if runs_peers:
        _run_peers(client, protocol_id)

    response = _accept(client, protocol_id, field, value)

    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert _fields(client, protocol_id)["changes"] == []


def test_several_flagged_values_are_accepted_and_all_pulled(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent_runners,
        "compare_with_registry_peers",
        out_of_line_demo_comparison,
    )
    protocol_id = _upload(client, tmp_path)
    _run_peers(client, protocol_id)
    offers = _offers_by_field(client, protocol_id)
    flagged = {
        comparison_field(dimension): offers[comparison_field(dimension)]
        for dimension in (
            DimensionId.MINIMUM_AGE,
            DimensionId.MAXIMUM_AGE,
            DimensionId.ENROLLMENT,
        )
    }
    starting = _field_values(_fields(client, protocol_id))

    accepted = {
        field: _accept(client, protocol_id, field, values[0])
        for field, values in flagged.items()
    }

    assert all(r.status_code == 200 for r in accepted.values())
    body = _fields(client, protocol_id)
    current = _field_values(body)
    changes = body["changes"]
    assert isinstance(changes, list)
    assert [c["field"] for c in changes] == list(flagged)
    for field, values in flagged.items():
        assert current[field] == format_number(values[0])
        change = next(c for c in changes if c["field"] == field)
        assert change["old_value"] == starting[field]


def test_second_offer_for_the_same_field_replaces_the_first(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent_runners,
        "compare_with_registry_peers",
        out_of_line_demo_comparison,
    )
    protocol_id = _upload(client, tmp_path)
    _run_peers(client, protocol_id)
    field = comparison_field(DimensionId.MAXIMUM_AGE)
    first_value, second_value = _offers_by_field(client, protocol_id)[field]

    _accept(client, protocol_id, field, first_value)
    _accept(client, protocol_id, field, second_value)

    body = _fields(client, protocol_id)
    assert _field_values(body)[field] == format_number(second_value)
    changes = body["changes"]
    assert isinstance(changes, list)
    assert [(c["old_value"], c["new_value"]) for c in changes] == [
        ("99", format_number(first_value)),
        (format_number(first_value), format_number(second_value)),
    ]


def test_unknown_protocol_returns_404_with_the_id(client: TestClient) -> None:
    accept = _accept(client, "proto-missing", HBA1C_FIELD, RECENT_VALUE)
    pull = client.get("/api/protocols/proto-missing/fields")

    assert accept.status_code == pull.status_code == 404
    assert "proto-missing" in pull.json()["detail"]


def test_database_failure_returns_503_with_the_reason(
    tmp_path: Path,
) -> None:
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("file", encoding="utf-8")
    set_protocol_db(ProtocolDb(blocking_file / "protocols.db"))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/protocols/proto-1/fields")

    assert response.status_code == 503
    assert "protocol database failed" in response.json()["detail"]


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_report_pdf_is_404_before_any_upload(client: TestClient) -> None:
    response = client.get("/api/protocols/latest/report.pdf")

    assert response.status_code == 404
    assert "No uploaded protocol" in response.json()["detail"]


def test_report_pdf_holds_the_latest_upload_and_its_changes(
    client: TestClient, tmp_path: Path
) -> None:
    older_dir, latest_dir = tmp_path / "older", tmp_path / "latest"
    older_dir.mkdir()
    latest_dir.mkdir()
    older_id = _upload(client, older_dir)
    latest_id = _upload(client, latest_dir)
    _run_peers(client, latest_id)
    _accept(client, latest_id, HBA1C_FIELD, RECENT_VALUE)

    response = client.get("/api/protocols/latest/report.pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert f"{latest_id}-report.pdf" in response.headers["content-disposition"]
    text = _pdf_text(response.content)
    assert latest_id in text
    assert older_id not in text
    assert "Accepted changes (1)" in text
    assert f"{HBA1C_FIELD}: 11 -> 10" in text
