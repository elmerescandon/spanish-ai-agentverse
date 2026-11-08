"""Compare a draft against its peers, dimension by dimension. No I/O.

Each dimension is checked against three peer groups (all, recent,
same-class) following FlagRules. Results stay structured, with every
peer's value and source as evidence; turning them into words for a
reviewer is left to whoever displays them.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from backend.agents.protocol_comparison.dimensions import (
    REGISTRY_DIMENSIONS,
    Dimension,
    DimensionValue,
    StricterWhen,
    TrialProfile,
)
from backend.agents.protocol_comparison.rules import (
    DEFAULT_FLAG_RULES,
    FlagRules,
)

PERCENTILE_CUT_COUNT = 100  # statistics.quantiles cuts into percentiles


class PeerGroup(StrEnum):
    """A subset of peers the draft is compared against."""

    ALL = "ALL"
    RECENT = "RECENT"
    SAME_CLASS = "SAME_CLASS"


class RangePosition(StrEnum):
    """Where the draft sits relative to the all-peer percentile range."""

    STRICTER = "STRICTER"
    INSIDE = "INSIDE"
    LOOSER = "LOOSER"


class Verdict(StrEnum):
    """Outcome of comparing one dimension."""

    FLAG = "FLAG"
    NO_FLAG = "NO_FLAG"
    INSUFFICIENT_PEERS = "INSUFFICIENT_PEERS"
    NO_DRAFT_VALUE = "NO_DRAFT_VALUE"


@dataclass(frozen=True)
class PercentileRange:
    """The all-peer range a draft value is expected to fall in."""

    low: float
    high: float


@dataclass(frozen=True)
class PeerEvidence:
    """One peer's value for the dimension and the groups it belongs to."""

    trial_id: str
    value: DimensionValue | None
    groups: frozenset[PeerGroup]


@dataclass(frozen=True)
class GroupSummary:
    """How the draft compares with one peer group.

    is_large_enough says whether enough peers state a value for the
    group to support a flag.
    """

    group: PeerGroup
    peer_count: int
    stating_count: int
    is_large_enough: bool
    is_draft_stricter_than_every_peer: bool


@dataclass(frozen=True)
class DimensionComparison:
    """The draft against its peers on one dimension, with the evidence."""

    dimension: Dimension
    draft_value: DimensionValue | None
    verdict: Verdict
    percentile_range: PercentileRange | None
    range_position: RangePosition | None
    # Recent or same-class groups that raised a flag on their own.
    flagging_groups: frozenset[PeerGroup]
    groups: tuple[GroupSummary, ...]
    evidence: tuple[PeerEvidence, ...]


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February in a year that has none
        return day.replace(year=day.year - years, day=28)


def assign_peer_groups(
    peer: TrialProfile,
    draft: TrialProfile,
    protocol_date: date,
    rules: FlagRules,
) -> frozenset[PeerGroup]:
    """Return every group a peer belongs to; all peers are in ALL.

    A peer is recent if it started in the window before the protocol
    date; one with no start date is never recent.
    """
    groups = {PeerGroup.ALL}
    window_start = _years_before(protocol_date, rules.recent_window_years)
    if (
        peer.start_date is not None
        and window_start <= peer.start_date < protocol_date
    ):
        groups.add(PeerGroup.RECENT)
    if peer.drug_classes & draft.drug_classes:
        groups.add(PeerGroup.SAME_CLASS)
    return frozenset(groups)


def _is_stricter(
    value: float, other_value: float, dimension: Dimension
) -> bool:
    if dimension.stricter_when == StricterWhen.HIGHER:
        return value > other_value
    return value < other_value


def _summarise_group(
    peer_group: PeerGroup,
    evidence: Sequence[PeerEvidence],
    draft_value: DimensionValue | None,
    dimension: Dimension,
    rules: FlagRules,
) -> GroupSummary:
    members = [peer for peer in evidence if peer_group in peer.groups]
    values = [peer.value.value for peer in members if peer.value is not None]
    minimum_size = (
        rules.min_peers
        if peer_group == PeerGroup.ALL
        else rules.min_group_peers
    )
    is_stricter_than_every_peer = (
        draft_value is not None
        and len(values) > 0
        and all(
            _is_stricter(draft_value.value, value, dimension)
            for value in values
        )
    )
    return GroupSummary(
        group=peer_group,
        peer_count=len(members),
        stating_count=len(values),
        is_large_enough=len(values) >= minimum_size,
        is_draft_stricter_than_every_peer=is_stricter_than_every_peer,
    )


def percentile_range(
    values: Sequence[float], rules: FlagRules
) -> PercentileRange:
    """Linear-interpolated percentiles, as numpy's default computes."""
    cuts = statistics.quantiles(
        values, n=PERCENTILE_CUT_COUNT, method="inclusive"
    )
    return PercentileRange(
        low=cuts[rules.low_percentile - 1],
        high=cuts[rules.high_percentile - 1],
    )


def _range_position(
    value: float, peer_range: PercentileRange, dimension: Dimension
) -> RangePosition:
    if peer_range.low <= value <= peer_range.high:
        return RangePosition.INSIDE
    is_above = value > peer_range.high
    is_higher_stricter = dimension.stricter_when == StricterWhen.HIGHER
    if is_above == is_higher_stricter:
        return RangePosition.STRICTER
    return RangePosition.LOOSER


def compare_dimension(
    dimension: Dimension,
    draft: TrialProfile,
    protocol_date: date,
    peers: Sequence[TrialProfile],
    rules: FlagRules = DEFAULT_FLAG_RULES,
) -> DimensionComparison:
    """Compare the draft's value on one dimension against its peers.

    Flags when the value is outside the all-peer percentile range, or
    stricter than every peer of a large-enough recent or same-class
    group. Never flags from fewer than rules.min_peers stating peers.
    """
    draft_value = draft.values.get(dimension.dimension_id)
    evidence = tuple(
        PeerEvidence(
            trial_id=peer.trial_id,
            value=peer.values.get(dimension.dimension_id),
            groups=assign_peer_groups(peer, draft, protocol_date, rules),
        )
        for peer in peers
    )
    groups = tuple(
        _summarise_group(peer_group, evidence, draft_value, dimension, rules)
        for peer_group in PeerGroup
    )
    all_values = [peer.value.value for peer in evidence if peer.value]
    if draft_value is None or len(all_values) < rules.min_peers:
        return DimensionComparison(
            dimension=dimension,
            draft_value=draft_value,
            verdict=(
                Verdict.NO_DRAFT_VALUE
                if draft_value is None
                else Verdict.INSUFFICIENT_PEERS
            ),
            percentile_range=None,
            range_position=None,
            flagging_groups=frozenset(),
            groups=groups,
            evidence=evidence,
        )
    peer_range = percentile_range(all_values, rules)
    position = _range_position(draft_value.value, peer_range, dimension)
    flagging_groups = frozenset(
        summary.group
        for summary in groups
        if summary.group != PeerGroup.ALL
        and summary.is_large_enough
        and summary.is_draft_stricter_than_every_peer
    )
    is_flagged = position != RangePosition.INSIDE or bool(flagging_groups)
    return DimensionComparison(
        dimension=dimension,
        draft_value=draft_value,
        verdict=Verdict.FLAG if is_flagged else Verdict.NO_FLAG,
        percentile_range=peer_range,
        range_position=position,
        flagging_groups=flagging_groups,
        groups=groups,
        evidence=evidence,
    )


def compare_draft(
    draft: TrialProfile,
    protocol_date: date,
    peers: Sequence[TrialProfile],
    dimensions: Sequence[Dimension] = REGISTRY_DIMENSIONS,
    rules: FlagRules = DEFAULT_FLAG_RULES,
) -> tuple[DimensionComparison, ...]:
    """Compare the draft on every dimension, in the order given."""
    return tuple(
        compare_dimension(dimension, draft, protocol_date, peers, rules)
        for dimension in dimensions
    )
