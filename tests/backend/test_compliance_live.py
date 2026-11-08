"""End-of-PR smoke test: real PDF -> API -> parser -> checker -> report.

Real Gemini calls on a full protocol (several minutes): run with
`make test-live`, once at the end of the PR.
"""

import asyncio
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest

from backend.agents.completeness.rules import load_rule_catalogue
from backend.api.routes import DEMO_PROTOCOL_ID, reset_mock_state
from backend.api.schemas import ComplianceReportResponse
from backend.main import app
from tests.conftest import make_live_gemini_client

FAME_D_PDF_PATH = Path("data/protocols/demo/NCT04828785_protocol.pdf")
BASE = f"/api/protocols/{DEMO_PROTOCOL_ID}"
POLL_INTERVAL_SECONDS = 5.0
MAX_WAIT_SECONDS = 900.0  # full parse (11 facets) + checks, with margin


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None]:
    reset_mock_state()
    yield
    reset_mock_state()


@pytest.mark.live
async def test_fame_d_upload_produces_an_evidence_backed_report() -> None:
    make_live_gemini_client()  # skips the test when no API key is set
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=60.0
    ) as client:
        upload = await client.post(
            f"{BASE}/pdf",
            files={
                "file": (
                    FAME_D_PDF_PATH.name,
                    FAME_D_PDF_PATH.read_bytes(),
                    "application/pdf",
                )
            },
        )
        assert upload.status_code == 200, upload.text
        started = await client.post(f"{BASE}/compliance-report")
        assert started.status_code == 202, started.text

        state = "running"
        waited = 0.0
        while state == "running" and waited < MAX_WAIT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            waited += POLL_INTERVAL_SECONDS
            status = await client.get(f"{BASE}/compliance-report/status")
            state = status.json()["state"]
        assert state == "done", status.json()

        response = await client.get(f"{BASE}/compliance-report")
        report = ComplianceReportResponse.model_validate(response.json())

    assert report.run.rules_evaluated == len(load_rule_catalogue().rules)
    assert 0.0 <= report.before.score <= 100.0
    for finding in report.findings:
        has_support = (
            bool(finding.evidence or finding.searched_locations)
            or finding.status_reason
        )
        assert has_support, finding.rule_id
        assert all(c.is_verified for c in finding.evidence), finding.rule_id
    type_1_rule = next(f for f in report.findings if f.rule_id == "DM-43")
    assert type_1_rule.status == "not_applicable"
