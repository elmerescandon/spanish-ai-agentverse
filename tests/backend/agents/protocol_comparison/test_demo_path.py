"""End to end on the committed demo data: cached peers, cached lab
readings, comparison, recommendations. No network and no LLM."""

from backend.agents.protocol_comparison.demo import demo_recommendations
from backend.api.schemas import PipelineStep, Severity

PROTOCOL_ID = "proto-demo"


async def test_demo_returns_one_comparison_record_per_dimension() -> None:
    recommendations = await demo_recommendations(PROTOCOL_ID)

    assert [r.details["dimension_id"] for r in recommendations] == [
        "MINIMUM_AGE",
        "MAXIMUM_AGE",
        "ENROLLMENT",
        "HBA1C_LOWER_BOUND",
        "HBA1C_UPPER_BOUND",
        "ALT_AST_LIMIT",
        "EGFR_CUTOFF",
    ]
    assert {r.source_step for r in recommendations} == {
        PipelineStep.COMPARISON
    }
    assert {r.protocol_id for r in recommendations} == {PROTOCOL_ID}


async def test_demo_reads_the_drafts_lab_limits_from_the_cache() -> None:
    recommendations = await demo_recommendations(PROTOCOL_ID)

    by_dimension = {r.details["dimension_id"]: r for r in recommendations}
    hba1c = by_dimension["HBA1C_UPPER_BOUND"].details["draft_value"]
    assert isinstance(hba1c, dict)
    assert hba1c["value"] == 11.0
    assert by_dimension["EGFR_CUTOFF"].details["finding"] == "NOT_STATED"


async def test_demo_registry_draft_has_no_flags_today() -> None:
    # The registry shows the protocol after Amendment 4 loosened its
    # limits; under Stefan's weighted rules nothing is out of line.
    recommendations = await demo_recommendations(PROTOCOL_ID)

    assert {r.severity for r in recommendations} == {Severity.INFO}
