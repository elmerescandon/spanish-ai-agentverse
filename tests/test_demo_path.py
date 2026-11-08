"""End-to-end /demo flow: upload, then the three steps in parallel."""

import asyncio
from pathlib import Path

import httpx

from backend.api.routes import reset_mock_state
from backend.main import app
from tests.conftest import make_pdf

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
