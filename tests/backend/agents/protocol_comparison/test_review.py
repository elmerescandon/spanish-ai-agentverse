"""Tests for turning flagged dimensions into reviewed suggestion cards."""

from backend.agents.protocol_comparison.agent import review_flags
from backend.agents.protocol_comparison.review import (
    FlagReasoning,
    Leaning,
    ReasoningStatus,
    build_reasoning_prompt,
)
from backend.agents.protocol_comparison.suggestions import suggest_values
from backend.clients.gemini import LlmCallFailedError
from tests.backend.agents.protocol_comparison.profiles import (
    compare,
    draft,
    spread_peers,
)
from tests.conftest import FakeJsonGenerator

FLAGGED = compare(draft(95), spread_peers())
IN_LINE = compare(draft(50), spread_peers())


def reasoning(*cited_trial_ids: str) -> FlagReasoning:
    return FlagReasoning(
        summary="Minimum age is higher than in most peers.",
        why_it_matters="Fewer eligible children.",
        risk_of_changing="None obvious.",
        leaning=Leaning.BRING_IN_LINE,
        cited_trial_ids=list(cited_trial_ids),
    )


async def test_review_writes_reasoning_only_for_flagged_dimensions() -> None:
    reply = reasoning("NCT-SPREAD-9")
    llm = FakeJsonGenerator([reply])

    cards = await review_flags([FLAGGED, IN_LINE], llm)

    assert len(cards) == 1
    assert cards[0].comparison is FLAGGED
    assert cards[0].reasoning == reply
    assert cards[0].reasoning_status == ReasoningStatus.WRITTEN
    assert len(llm.prompts) == 1


async def test_review_without_llm_keeps_suggestions_and_skips_reasoning() -> (
    None
):
    [card] = await review_flags([FLAGGED], llm=None)

    assert card.reasoning is None
    assert card.reasoning_status == ReasoningStatus.SKIPPED
    assert [suggestion.suggested_value for suggestion in card.suggestions] == [
        90.0
    ]


async def test_review_marks_reasoning_failed_when_llm_call_fails() -> None:
    llm = FakeJsonGenerator([LlmCallFailedError("retries exhausted")])

    [card] = await review_flags([FLAGGED], llm)

    assert card.reasoning is None
    assert card.reasoning_status == ReasoningStatus.FAILED
    assert len(card.suggestions) == 1


async def test_review_reports_cited_trials_missing_from_evidence() -> None:
    llm = FakeJsonGenerator([reasoning("NCT-SPREAD-1", "NCT99999999")])

    [card] = await review_flags([FLAGGED], llm)

    assert card.unknown_cited_trial_ids == ("NCT99999999",)


async def test_review_with_no_flags_makes_no_llm_call() -> None:
    llm = FakeJsonGenerator([])

    assert await review_flags([IN_LINE], llm) == ()


def test_prompt_shows_every_peer_value_with_its_source() -> None:
    prompt = build_reasoning_prompt(FLAGGED, suggest_values(FLAGGED))

    for index, value in enumerate(range(0, 101, 10)):
        assert f"NCT-SPREAD-{index}" in prompt
        assert f"test value {float(value)}" in prompt


def test_prompt_shows_the_draft_value_and_suggested_value() -> None:
    prompt = build_reasoning_prompt(FLAGGED, suggest_values(FLAGGED))

    assert "test value 95" in prompt
    assert "90" in prompt


def test_prompt_names_every_leaning_the_reply_may_use() -> None:
    prompt = build_reasoning_prompt(FLAGGED, suggest_values(FLAGGED))

    for leaning in Leaning:
        assert f'"{leaning.value}"' in prompt
