"""Suggest values that bring a flagged dimension back in line. No I/O.

Suggested values always come from the peers' own values, never from the
LLM, so any number a protocol might be changed to traces back to trials.
"""

from dataclasses import dataclass

from backend.agents.protocol_comparison.comparison import (
    Category,
    CategoryResult,
    DimensionComparison,
    FlagRule,
    PeerEvidence,
)


@dataclass(frozen=True)
class Suggestion:
    """A value for the draft, the category it fits, and its peers."""

    category: Category
    rule: FlagRule
    suggested_value: float
    peer_ids: tuple[str, ...]


def _members(
    evidence: tuple[PeerEvidence, ...], category: Category
) -> list[tuple[str, float]]:
    return [
        (peer.trial_id, peer.value.value)
        for peer in evidence
        if peer.value is not None
        and (category == Category.WEIGHTED or category in peer.categories)
    ]


def _suggest(
    flagged: CategoryResult,
    draft_value: float,
    members: list[tuple[str, float]],
) -> float:
    if flagged.rule == FlagRule.PERCENTILE_RANGE:
        assert flagged.percentile_range is not None
        peer_range = flagged.percentile_range
        if draft_value > peer_range.high:
            return peer_range.high
        return peer_range.low
    values = [value for _, value in members]
    return max(values) if draft_value > max(values) else min(values)


def suggest_values(result: DimensionComparison) -> tuple[Suggestion, ...]:
    """Suggest one value per flagging category, official result first.

    Under the percentile rule the value is the nearest edge of the range;
    when only "beyond every peer" applies, it is the nearest peer value.
    """
    if result.draft_value is None:
        return ()
    suggestions: list[Suggestion] = []
    for flagged in result.flagged_categories:
        assert flagged.rule is not None
        members = _members(result.evidence, flagged.category)
        suggestions.append(
            Suggestion(
                category=flagged.category,
                rule=flagged.rule,
                suggested_value=_suggest(
                    flagged, result.draft_value.value, members
                ),
                peer_ids=tuple(trial_id for trial_id, _ in members),
            )
        )
    return tuple(suggestions)
