"""End-of-PR smoke test: demo PDF -> /demo upload -> CHECK and PEERS steps.

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
# The draft's lab limits must be read from its parsed criteria.
UNREAD_DRAFT_LAB_WARNINGS = {"DRAFT_LABS_FAILED", "DRAFT_LABS_NOT_READ"}
# The full PEERS step is saved here (gitignored) to inspect after a run.
PEERS_OUTPUT_DIRECTORY = Path("scratch/live")
REPORT_COLUMNS = (
    "dimension",
    "draft_value",
    "finding",
    "peer_p10",
    "peer_p90",
)
QUOTE_PREVIEW_CHARS = 70


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
async def test_demo_upload_check_and_peers_fill_the_demo_sections(
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
        peers_response = await client.post(
            "/api/protocol-recommendation",
            json={"protocol_id": upload.protocol_id},
        )
        assert peers_response.status_code == 200, peers_response.text
        peers = StepData.model_validate(peers_response.json())

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
    output_path = PEERS_OUTPUT_DIRECTORY / f"peers_{pdf_path.stem}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(peers.model_dump_json(indent=2), encoding="utf-8")
    logger.info(
        "live peers report: pdf=%s saved=%s\n%s",
        pdf_path.name,
        output_path,
        _peers_report(peers),
    )
    _assert_peers_compare_the_parsed_protocol(peers, upload.title)


def _peers_report(peers: StepData) -> str:
    """The PEERS step as a plain-text table, for reading test output."""
    [dimensions] = peers.tables
    rows = [
        [str(row[column]) for column in REPORT_COLUMNS]
        for row in dimensions.rows
    ]
    widths = [
        max(len(column), *(len(row[index]) for row in rows))
        for index, column in enumerate(REPORT_COLUMNS)
    ]
    lines = [
        "  ".join(
            column.ljust(width)
            for column, width in zip(REPORT_COLUMNS, widths, strict=True)
        )
    ]
    lines.extend(
        "  ".join(
            cell.ljust(width) for cell, width in zip(row, widths, strict=True)
        )
        for row in rows
    )
    lines.append("")
    lines.append("Draft evidence (where each draft value was read):")
    for decision in peers.decisions:
        for evidence in decision.evidence:
            if evidence.evidence_id.endswith("-draft"):
                lines.append(
                    f"  {decision.title}: page {evidence.page} "
                    f"[{evidence.source}] "
                    f'"{evidence.quote[:QUOTE_PREVIEW_CHARS]}"'
                )
    lines.append("")
    lines.append(f"Summary: {peers.summary}")
    lines.append(f"Status: {peers.status}")
    lines.extend(
        f"Warning {warning.code}: {warning.message}"
        for warning in peers.warnings
    )
    return "\n".join(lines)


def _assert_peers_compare_the_parsed_protocol(
    peers: StepData, protocol_title: str
) -> None:
    """The PEERS step's draft values come from the uploaded PDF."""
    [dimensions] = peers.tables
    warning_codes = {warning.code for warning in peers.warnings}
    assert peers.id == "peers"
    assert not warning_codes & UNREAD_DRAFT_LAB_WARNINGS
    assert any(row["draft_value"] is not None for row in dimensions.rows)
    draft_evidence = [
        evidence
        for decision in peers.decisions
        for evidence in decision.evidence
        if evidence.evidence_id.endswith("-draft")
    ]
    assert draft_evidence
    for evidence in draft_evidence:
        assert evidence.source == "protocol"
        assert evidence.document == protocol_title
