"""End-to-end /demo flow: upload, the three steps, then the review."""

import asyncio
from pathlib import Path

import httpx
import pytest

from backend.agents.protocol_comparison.comparison import Category
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.api import agent_runners
from backend.api.protocol_fields import comparison_field
from backend.api.routes import reset_mock_state
from backend.main import app
from tests.conftest import (
    OFFERED_HBA1C_VALUES,
    flagged_demo_comparison,
    make_pdf,
)

READABLE_PAGE = (
    "This clinical trial protocol evaluates glycemic control in adults "
    "with type 2 diabetes mellitus across multiple investigative sites."
)
STEP_ROUTES = [
    "/api/checklist-recommendation",
    "/api/protocol-recommendation",
    "/api/cohort-recommendation",
]


async def test_demo_path_upload_then_parallel_steps_fill_all_four_sections(
    tmp_path: Path,
) -> None:
    reset_mock_state()
    pdf_path = make_pdf(tmp_path, [READABLE_PAGE])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        upload = await client.post(
            "/api/upload-file",
            files={
                "file": (
                    "trial.pdf",
                    pdf_path.read_bytes(),
                    "application/pdf",
                )
            },
        )
        assert upload.status_code == 200
        protocol_id = upload.json()["protocol_id"]
        responses = await asyncio.gather(
            *(
                client.post(route, json={"protocol_id": protocol_id})
                for route in STEP_ROUTES
            )
        )
    step_ids = [upload.json()["step"]["id"]] + [
        response.json()["id"] for response in responses
    ]
    assert all(response.status_code == 200 for response in responses)
    assert step_ids == ["ingest", "check", "peers", "cohort"]
    reset_mock_state()


async def test_demo_review_accepts_an_offered_value_and_pulls_the_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent_runners, "compare_with_registry_peers", flagged_demo_comparison
    )
    reset_mock_state()
    hba1c_field = comparison_field(DimensionId.HBA1C_UPPER_BOUND)
    accepted_value = OFFERED_HBA1C_VALUES[Category.ALL]
    pdf_path = make_pdf(tmp_path, [READABLE_PAGE])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        upload = await client.post(
            "/api/upload-file",
            files={
                "file": (
                    "trial.pdf",
                    pdf_path.read_bytes(),
                    "application/pdf",
                )
            },
        )
        protocol_id = upload.json()["protocol_id"]
        steps = await asyncio.gather(
            *(
                client.post(route, json={"protocol_id": protocol_id})
                for route in STEP_ROUTES
            )
        )
        accepted = await client.post(
            f"/api/protocols/{protocol_id}/changes",
            json={"field": hba1c_field, "value": accepted_value},
        )
        pulled = await client.get(f"/api/protocols/{protocol_id}/fields")
    assert all(step.status_code == 200 for step in steps)
    assert accepted.status_code == 200, accepted.text
    fields = {item["field"]: item for item in pulled.json()["fields"]}
    assert fields[hba1c_field]["value"] == "10.5"
    assert fields[hba1c_field]["unit"] == "%"
    [change] = pulled.json()["changes"]
    assert (change["old_value"], change["new_value"]) == ("11", "10.5")
    reset_mock_state()
