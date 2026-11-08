"""Suggest values that bring a flagged dimension back in line. No I/O.

Suggested values always come from the peers' own values, never from the
LLM, so any number a protocol might be changed to traces back to trials.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from backend.agents.protocol_comparison.comparison import (
    DimensionComparison,
    PeerEvidence,
    PeerGroup,
    RangePosition,
    Verdict,
)
from backend.agents.protocol_comparison.dimensions import StricterWhen


class SuggestionBasis(StrEnum):
    """What a suggested value would bring the draft in line with."""

    PEER_RANGE = "PEER_RANGE"
    RECENT_PEERS = "RECENT_PEERS"
    SAME_CLASS_PEERS = "SAME_CLASS_PEERS"


GROUP_BASIS = {
    PeerGroup.RECENT: SuggestionBasis.RECENT_PEERS,
    PeerGroup.SAME_CLASS: SuggestionBasis.SAME_CLASS_PEERS,
}


@dataclass(frozen=True)
class Suggestion:
    """A value for the draft, and the peers it is derived from."""

    basis: SuggestionBasis
    suggested_value: float
    peer_ids: tuple[str, ...]


def _stating(
    evidence: Sequence[PeerEvidence], peer_group: PeerGroup
) -> list[tuple[str, float]]:
    return [
        (peer.trial_id, peer.value.value)
        for peer in evidence
        if peer_group in peer.groups and peer.value is not None
    ]


def suggest_values(result: DimensionComparison) -> tuple[Suggestion, ...]:
    """Suggest one value per reason the dimension was flagged.

    Outside the all-peer range: the nearest edge of the range. Stricter
    than every peer of a recent or same-class group: that group's
    strictest value. Unflagged dimensions get no suggestion.
    """
    if result.verdict != Verdict.FLAG:
        return ()
    suggestions: list[Suggestion] = []
    if result.range_position != RangePosition.INSIDE:
        assert result.percentile_range is not None
        assert result.draft_value is not None
        is_above = result.draft_value.value > result.percentile_range.high
        all_peers = _stating(result.evidence, PeerGroup.ALL)
        suggestions.append(
            Suggestion(
                basis=SuggestionBasis.PEER_RANGE,
                suggested_value=(
                    result.percentile_range.high
                    if is_above
                    else result.percentile_range.low
                ),
                peer_ids=tuple(trial_id for trial_id, _ in all_peers),
            )
        )
    pick_strictest = (
        max if result.dimension.stricter_when == StricterWhen.HIGHER else min
    )
    for peer_group in (PeerGroup.RECENT, PeerGroup.SAME_CLASS):
        if peer_group not in result.flagging_groups:
            continue
        members = _stating(result.evidence, peer_group)
        suggestions.append(
            Suggestion(
                basis=GROUP_BASIS[peer_group],
                suggested_value=pick_strictest(value for _, value in members),
                peer_ids=tuple(trial_id for trial_id, _ in members),
            )
        )
    return tuple(suggestions)
