"""Suggestion cards for flagged dimensions, and the LLM's part in them.

Pure: builds the reasoning prompt from the comparison's facts and checks
the LLM's reply against them. The LLM call itself lives in agent.py.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.agents.protocol_comparison.comparison import (
    DimensionComparison,
    Verdict,
)
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
    """One dimension worth a doctor's look, ready for their decision.

    Made for any flag (official or category) or a same-drug note.
    """

    comparison: DimensionComparison
    suggestions: tuple[Suggestion, ...]
    reasoning: FlagReasoning | None
    reasoning_status: ReasoningStatus
    # Trials the LLM cited that are not in the evidence: shown as a
    # warning on the card, since they may be invented.
    unknown_cited_trial_ids: tuple[str, ...] = ()

    @property
    def is_official_flag(self) -> bool:
        """True when Stefan's weighted rule flags it, not just a view."""
        return self.comparison.verdict == Verdict.FLAG


def needs_review(result: DimensionComparison) -> bool:
    """A dimension gets a card if anything flags or a note applies."""
    return bool(result.flagged_categories) or (
        result.same_drug_note is not None
    )


def _comparison_facts(
    result: DimensionComparison, suggestions: Sequence[Suggestion]
) -> dict[str, object]:
    dimension = result.dimension
    draft_value = result.draft_value
    note = result.same_drug_note
    return {
        "dimension": dimension.label,
        "unit": dimension.unit,
        "stricter_when": f"{dimension.stricter_when.value.lower()} values",
        "draft_value": (
            None
            if draft_value is None
            else {"value": draft_value.value, "source": draft_value.source}
        ),
        "official_verdict": {
            "verdict": result.verdict.value,
            "severity": None if result.severity is None else result.severity,
            "explanation": (
                "From all peers weighted by tier (same drug 1.0, same "
                "class 0.6, same disease 0.3), recency and status. Below "
                "5 effective peers nothing flags; with 5 to 9 only a "
                "value beyond every peer flags (S3, advisory); from 10, "
                "a value outside the 10th-90th percentile flags (S2)."
            ),
        },
        "categories": [
            {
                "category": summary.category.value,
                "is_official": summary is result.categories[0],
                "peers": summary.peer_count,
                "peers_stating_a_value": summary.stating_count,
                "effective_peers": round(summary.n_eff, 2),
                "verdict": summary.verdict.value,
                "severity": summary.severity,
                "rule": summary.rule,
                "percentile_range_10_to_90": (
                    None
                    if summary.percentile_range is None
                    else [
                        summary.percentile_range.low,
                        summary.percentile_range.high,
                    ]
                ),
                "draft_position": summary.range_position,
            }
            for summary in result.categories
        ],
        "same_drug_note": (
            None
            if note is None
            else {
                "meaning": (
                    "The draft is beyond every earlier trial of the same "
                    "drug. An extra note, not an official flag."
                ),
                "draft_position": note.position.value,
                "same_drug_trials": list(note.peer_ids),
            }
        ),
        "suggested_values": [
            {
                "brings_in_line_with": suggestion.category.value,
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
                "tier": peer.tier.value,
                "weight": round(peer.weight, 3),
                "categories": sorted(peer.categories),
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
