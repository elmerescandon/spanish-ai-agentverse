"""End-of-PR smoke test: demo PDF -> /demo upload -> CHECK step.

Real Gemini calls on a full protocol (several minutes): run with
`make test-live`, once at the end of the PR.
"""

import logging
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest

from backend.agents.completeness.rules import load_rule_catalogue
from backend.api.protocol_pipeline import (
    ProtocolPipeline,
    set_protocol_pipeline,
)
from backend.api.routes import reset_mock_state
from backend.api.schemas import StepData, UploadFileResponse
from backend.main import app
from tests.conftest import make_live_gemini_client

logger = logging.getLogger(__name__)

DEMO_DIRECTORY = Path("data/protocols/demo")
# Both demo protocols are adult type 2 diabetes trials: FAME-D (meals)
# and a canagliflozin drug trial, so drug-only rules apply to one of them.
DEMO_PDF_PATHS = [
    DEMO_DIRECTORY / "NCT04828785_protocol.pdf",
    DEMO_DIRECTORY / "NCT03170518_protocol.pdf",
]
REQUEST_TIMEOUT_SECONDS = 1200.0  # full parse or full check, with margin


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None]:
    reset_mock_state()
    # Memory-only pipeline so the live test always calls Gemini and never
    # passes by reading an earlier cached run from data/cache.
    set_protocol_pipeline(ProtocolPipeline())
    yield
    reset_mock_state()


@pytest.mark.live
@pytest.mark.parametrize("pdf_path", DEMO_PDF_PATHS, ids=lambda p: p.stem)
async def test_demo_upload_and_check_fill_the_demo_sections(
    pdf_path: Path,
) -> None:
    make_live_gemini_client()  # skips the test when no API key is set
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        upload_response = await client.post(
            "/api/upload-file",
            files={
                "file": (
                    pdf_path.name,
                    pdf_path.read_bytes(),
                    "application/pdf",
                )
            },
        )
        assert upload_response.status_code == 200, upload_response.text
        upload = UploadFileResponse.model_validate(upload_response.json())
        check_response = await client.post(
            "/api/checklist-recommendation",
            json={"protocol_id": upload.protocol_id},
        )
        assert check_response.status_code == 200, check_response.text
        step = StepData.model_validate(check_response.json())

    logger.info(
        "live check: pdf=%s score=%s decisions=%d duration_seconds=%.0f",
        pdf_path.name,
        step.headline.value,
        len(step.decisions),
        (step.duration_ms or 0) / 1000,
    )
    ingest_metrics = {m.label: m.value for m in upload.step.metrics}
    assert int(ingest_metrics["Eligibility criteria"]) > 0
    [checklist] = step.tables
    assert len(checklist.rows) == len(load_rule_catalogue().rules)
    statuses = {row["rule_id"]: row["status"] for row in checklist.rows}
    assert statuses["DM-43"] == "not_applicable"  # type 1 only
    for decision in step.decisions:
        assert decision.step_id == "check"
        assert all(e.is_verified and e.page for e in decision.evidence)
        assert decision.evidence or decision.details["searched_locations"]
