"""Suggestion cards for flagged dimensions, and the LLM's part in them.

Pure: builds the reasoning prompt from the comparison's facts and checks
the LLM's reply against them. The LLM call itself lives in agent.py.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.agents.protocol_comparison.comparison import DimensionComparison
from backend.agents.protocol_comparison.prompts import REASONING_INSTRUCTIONS
from backend.agents.protocol_comparison.suggestions import Suggestion

PROMPT_SECTION_SEPARATOR = "\n---\nFacts (JSON):\n"
JSON_INDENT = 2


class Leaning(StrEnum):
    """The LLM's lean on a flag; the doctor makes the decision."""

    BRING_IN_LINE = "BRING_IN_LINE"
    KEEP_AS_IS = "KEEP_AS_IS"
    NEEDS_CLINICAL_JUDGEMENT = "NEEDS_CLINICAL_JUDGEMENT"


class ReasoningStatus(StrEnum):
    """Whether a card's written reasoning is there, and why not."""

    WRITTEN = "WRITTEN"
    SKIPPED = "SKIPPED"  # no LLM configured
    FAILED = "FAILED"  # the LLM call failed after its retries


class FlagReasoning(BaseModel):
    """The LLM's explanation of one flag, validated at the boundary."""

    summary: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    risk_of_changing: str = Field(min_length=1)
    leaning: Leaning
    cited_trial_ids: list[str]


@dataclass(frozen=True)
class SuggestionCard:
    """One flagged dimension, ready for a doctor's decision."""

    comparison: DimensionComparison
    suggestions: tuple[Suggestion, ...]
    reasoning: FlagReasoning | None
    reasoning_status: ReasoningStatus
    # Trials the LLM cited that are not in the evidence: shown as a
    # warning on the card, since they may be invented.
    unknown_cited_trial_ids: tuple[str, ...] = ()


def _comparison_facts(
    result: DimensionComparison, suggestions: Sequence[Suggestion]
) -> dict[str, object]:
    dimension = result.dimension
    draft_value = result.draft_value
    peer_range = result.percentile_range
    return {
        "dimension": dimension.label,
        "unit": dimension.unit,
        "stricter_when": f"{dimension.stricter_when.value.lower()} values",
        "draft_value": (
            None
            if draft_value is None
            else {"value": draft_value.value, "source": draft_value.source}
        ),
        "usual_range_of_all_peers": (
            None
            if peer_range is None
            else {
                "description": "10th to 90th percentile of all peers",
                "low": peer_range.low,
                "high": peer_range.high,
            }
        ),
        "draft_position_against_usual_range": (
            None
            if result.range_position is None
            else result.range_position.value
        ),
        "groups_where_draft_is_stricter_than_every_peer": sorted(
            result.flagging_groups
        ),
        "peer_groups": [
            {
                "group": summary.group.value,
                "peers": summary.peer_count,
                "peers_stating_a_value": summary.stating_count,
                "large_enough_to_flag": summary.is_large_enough,
                "draft_stricter_than_every_peer": (
                    summary.is_draft_stricter_than_every_peer
                ),
            }
            for summary in result.groups
        ],
        "suggested_values": [
            {
                "brings_in_line_with": suggestion.basis.value,
                "suggested_value": suggestion.suggested_value,
                "based_on_trials": list(suggestion.peer_ids),
            }
            for suggestion in suggestions
        ],
        "peers": [
            {
                "trial_id": peer.trial_id,
                "value": None if peer.value is None else peer.value.value,
                "source": None if peer.value is None else peer.value.source,
                "groups": sorted(peer.groups),
            }
            for peer in result.evidence
        ],
    }


def build_reasoning_prompt(
    result: DimensionComparison, suggestions: Sequence[Suggestion]
) -> str:
    """Instructions plus every fact the LLM may use, as JSON."""
    facts = _comparison_facts(result, suggestions)
    return (
        REASONING_INSTRUCTIONS
        + PROMPT_SECTION_SEPARATOR
        + json.dumps(facts, indent=JSON_INDENT)
    )


def unknown_cited_trials(
    reasoning: FlagReasoning, result: DimensionComparison
) -> tuple[str, ...]:
    """Trial IDs the LLM cited that are not among the peers compared."""
    known_trial_ids = {peer.trial_id for peer in result.evidence}
    return tuple(
        trial_id
        for trial_id in reasoning.cited_trial_ids
        if trial_id not in known_trial_ids
    )
