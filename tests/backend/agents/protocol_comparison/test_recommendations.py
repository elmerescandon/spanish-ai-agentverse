"""Tests for turning comparison results into API recommendations.

Every compared dimension becomes one recommendation: flags keep their
severity, everything else is info, so a reviewer sees what was checked.
"""

import json

from backend.agents.protocol_comparison.agent import review_flags
from backend.agents.protocol_comparison.comparison import DimensionComparison
from backend.agents.protocol_comparison.recommendations import (
    to_recommendations,
)
from backend.agents.protocol_comparison.review import (
    FlagReasoning,
    Leaning,
    SuggestionCard,
)
from backend.api.schemas import (
    PipelineStep,
    Recommendation,
    RecommendationStatus,
    Severity,
)
from backend.clients.gemini import JsonGenerator
from tests.backend.agents.protocol_comparison.profiles import (
    MAXIMUM_AGE,
    compare,
    draft,
    recent_peers,
    spread_peers,
)
from tests.conftest import FakeJsonGenerator

PROTOCOL_ID = "proto-test"
OFFICIAL_S2 = compare(draft(95), spread_peers())
OFFICIAL_S3 = compare(draft(61), spread_peers()[:7])
RECENT_ONLY = compare(
    draft(70), spread_peers() + recent_peers(20, 30, 40, 50, 60)
)
REASONING = FlagReasoning(
    summary="Minimum age 95 is stricter than every comparable trial.",
    why_it_matters="Fewer eligible participants.",
    risk_of_changing="None obvious.",
    leaning=Leaning.BRING_IN_LINE,
    cited_trial_ids=["NCT-SPREAD-9"],
)


LOOSER_MAX_AGE = compare(
    draft(95, MAXIMUM_AGE), spread_peers(MAXIMUM_AGE), MAXIMUM_AGE
)


async def recommend(
    *results: DimensionComparison, llm: JsonGenerator | None = None
) -> list[Recommendation]:
    cards: tuple[SuggestionCard, ...] = await review_flags(list(results), llm)
    return to_recommendations(PROTOCOL_ID, results, cards)


async def test_official_flag_becomes_a_pending_comparison_recommendation() -> (
    None
):
    [recommendation] = await recommend(OFFICIAL_S2)

    assert recommendation.protocol_id == PROTOCOL_ID
    assert recommendation.source_step == PipelineStep.COMPARISON
    assert recommendation.status == RecommendationStatus.PENDING
    assert recommendation.severity == Severity.WARNING


async def test_stefans_s3_advisory_flag_maps_to_info() -> None:
    [recommendation] = await recommend(OFFICIAL_S3)

    assert recommendation.severity == Severity.INFO


async def test_category_only_flag_is_info_and_marked_unofficial() -> None:
    [recommendation] = await recommend(RECENT_ONLY)

    assert recommendation.severity == Severity.INFO
    assert recommendation.details["is_official_flag"] is False


async def test_title_names_the_dimension_value_and_direction() -> None:
    [recommendation] = await recommend(OFFICIAL_S2)

    assert recommendation.title == (
        "Minimum age: 95 years is stricter than comparable trials"
    )


async def test_title_says_looser_for_a_looser_value() -> None:
    [recommendation] = await recommend(LOOSER_MAX_AGE)

    assert "is looser than comparable trials" in recommendation.title


async def test_description_is_the_llm_summary_when_written() -> None:
    llm = FakeJsonGenerator([REASONING])

    [recommendation] = await recommend(OFFICIAL_S2, llm=llm)

    assert recommendation.description == REASONING.summary
    assert recommendation.details["reasoning"] == REASONING.model_dump(
        mode="json"
    )


async def test_description_falls_back_to_the_facts_without_an_llm() -> None:
    [recommendation] = await recommend(OFFICIAL_S2)

    assert "95" in recommendation.description
    assert "90" in recommendation.description  # the suggested value
    assert recommendation.details["reasoning"] is None


async def test_recommendation_ids_are_stable_and_unique_per_dimension() -> (
    None
):
    first = await recommend(OFFICIAL_S2)
    again = await recommend(OFFICIAL_S2)
    max_age = await recommend(LOOSER_MAX_AGE)

    assert first[0].recommendation_id == again[0].recommendation_id
    assert first[0].recommendation_id != max_age[0].recommendation_id


async def test_details_carry_suggestions_and_evidence_as_plain_json() -> None:
    [recommendation] = await recommend(OFFICIAL_S2)

    details = json.loads(json.dumps(recommendation.details))
    assert details["suggested_values"][0]["suggested_value"] == 90.0
    assert {peer["trial_id"] for peer in details["peers"]} == {
        f"NCT-SPREAD-{index}" for index in range(11)
    }


IN_LINE = compare(draft(50), spread_peers())


async def test_in_line_dimension_is_an_info_record_without_suggestions() -> (
    None
):
    [recommendation] = await recommend(IN_LINE)

    assert recommendation.severity == Severity.INFO
    assert recommendation.title == (
        "Minimum age: 50 years is in line with comparable trials"
    )
    assert recommendation.details["finding"] == "IN_LINE"
    assert recommendation.details["suggested_values"] == []


async def test_dimension_the_draft_does_not_state_says_so() -> None:
    [recommendation] = await recommend(compare(draft(None), spread_peers()))

    assert recommendation.title == "Minimum age: not stated in the draft"
    assert recommendation.details["finding"] == "NOT_STATED"


async def test_too_few_peers_says_so_instead_of_in_line() -> None:
    [recommendation] = await recommend(compare(draft(50), spread_peers()[:3]))

    assert recommendation.title == (
        "Minimum age: too few comparable trials to judge 50 years"
    )
    assert recommendation.details["finding"] == "INSUFFICIENT_PEERS"


async def test_flag_is_marked_as_a_flag_in_details() -> None:
    [recommendation] = await recommend(OFFICIAL_S2)

    assert recommendation.details["finding"] == "FLAGGED"


async def test_one_recommendation_per_dimension_in_the_given_order() -> None:
    recommendations = await recommend(IN_LINE, LOOSER_MAX_AGE)

    assert [r.details["dimension_id"] for r in recommendations] == [
        "MINIMUM_AGE",
        "MAXIMUM_AGE",
    ]
