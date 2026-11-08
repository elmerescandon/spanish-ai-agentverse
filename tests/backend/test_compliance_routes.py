"""HTTP tests for uploading a protocol PDF and running the checker."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import httpx
import pytest

from backend.api import routes
from backend.api.compliance_service import ComplianceService
from backend.api.routes import (
    DEMO_PROTOCOL_ID,
    apply_compliance_report,
    get_compliance_service,
    reset_mock_state,
)
from backend.api.schemas import ComplianceReportResponse
from backend.main import app
from backend.shared.messages import ComplianceReport
from tests.backend.test_compliance import _build_illustrative_example_report

PDF_BYTES = b"%PDF-1.7 fake protocol bytes"
BASE = f"/api/protocols/{DEMO_PROTOCOL_ID}"
MAX_POLLS = 50


async def _fake_analysis(pdf_path: Path) -> ComplianceReport:
    return _build_illustrative_example_report()


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None]:
    reset_mock_state()
    yield
    reset_mock_state()
    app.dependency_overrides.clear()


@pytest.fixture
async def client(tmp_path: Path) -> AsyncGenerator[httpx.AsyncClient]:
    service = ComplianceService(
        analyse=_fake_analysis,
        upload_directory=tmp_path,
        on_report=apply_compliance_report,
    )
    app.dependency_overrides[get_compliance_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as test_client:
        yield test_client


async def _upload(
    client: httpx.AsyncClient, content: bytes = PDF_BYTES
) -> httpx.Response:
    return await client.post(
        f"{BASE}/pdf",
        files={"file": ("protocol.pdf", content, "application/pdf")},
    )


async def _wait_until_done(client: httpx.AsyncClient) -> dict[str, object]:
    for _ in range(MAX_POLLS):
        status = (await client.get(f"{BASE}/compliance-report/status")).json()
        if status["state"] != "running":
            return dict(status)
        await asyncio.sleep(0)
    raise AssertionError("analysis did not finish")


async def test_upload_attaches_pdf_to_protocol(
    client: httpx.AsyncClient,
) -> None:
    response = await _upload(client)

    assert response.status_code == 200
    assert response.json()["protocol_id"] == DEMO_PROTOCOL_ID


async def test_upload_rejects_a_file_that_is_not_a_pdf(
    client: httpx.AsyncClient,
) -> None:
    response = await _upload(client, b"<html>not a pdf</html>")

    assert response.status_code == 415


async def test_upload_rejects_a_file_over_the_size_limit(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "MAX_UPLOAD_BYTES", 8)

    response = await _upload(client)

    assert response.status_code == 413


async def test_upload_to_unknown_protocol_is_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/protocols/missing/pdf",
        files={"file": ("p.pdf", PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 404


async def test_analysis_without_a_pdf_is_409(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(f"{BASE}/compliance-report")

    assert response.status_code == 409


async def test_report_before_any_analysis_is_404(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get(f"{BASE}/compliance-report")).status_code == 404
    status = await client.get(f"{BASE}/compliance-report/status")
    assert status.status_code == 404


async def test_full_flow_returns_report_and_real_cards(
    client: httpx.AsyncClient,
) -> None:
    await _upload(client)

    started = await client.post(f"{BASE}/compliance-report")
    status = await _wait_until_done(client)
    report = await client.get(f"{BASE}/compliance-report")
    cards = (await client.get(f"{BASE}/recommendations")).json()
    protocol = (await client.get(BASE)).json()

    assert started.status_code == 202
    assert status == {
        "protocol_id": DEMO_PROTOCOL_ID,
        "state": "done",
        "error": None,
    }
    assert report.status_code == 200
    ComplianceReportResponse.model_validate(report.json())
    completeness = [c for c in cards if c["source_step"] == "completeness"]
    assert [c["details"]["rule_id"] for c in completeness] == ["REG-27"]
    assert {c["source_step"] for c in cards} == {
        "completeness",
        "comparison",
        "cohort",
    }
    assert protocol["status"] == "ready"
