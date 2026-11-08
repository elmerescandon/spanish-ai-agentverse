"""Tests for comparing a draft against peers on one dimension.

Values are hand-picked; see profiles.py for the shared peer sets.
"""

from datetime import date

from backend.agents.protocol_comparison.comparison import (
    DimensionComparison,
    GroupSummary,
    PeerGroup,
    PercentileRange,
    RangePosition,
    Verdict,
    compare_draft,
)
from backend.agents.protocol_comparison.dimensions import (
    DimensionId,
    DimensionValue,
)
from backend.agents.protocol_comparison.rules import DrugClass
from tests.backend.agents.protocol_comparison.profiles import (
    MAXIMUM_AGE,
    PROTOCOL_DATE,
    compare,
    draft,
    profile,
    recent_peers,
    same_class_peers,
    spread_peers,
)


def group(result: DimensionComparison, peer_group: PeerGroup) -> GroupSummary:
    return next(
        summary for summary in result.groups if summary.group == peer_group
    )


# All peers: the 10th-90th percentile range


def test_range_is_10th_to_90th_percentile_of_all_peers() -> None:
    result = compare(draft(50), spread_peers())

    assert result.percentile_range == PercentileRange(low=10.0, high=90.0)


def test_draft_inside_range_is_not_flagged() -> None:
    result = compare(draft(50), spread_peers())

    assert result.range_position == RangePosition.INSIDE
    assert result.verdict == Verdict.NO_FLAG


def test_draft_exactly_on_range_edge_counts_as_inside() -> None:
    result = compare(draft(90), spread_peers())

    assert result.range_position == RangePosition.INSIDE
    assert result.verdict == Verdict.NO_FLAG


def test_draft_above_range_is_stricter_when_higher_is_stricter() -> None:
    result = compare(draft(91), spread_peers())

    assert result.range_position == RangePosition.STRICTER
    assert result.verdict == Verdict.FLAG


def test_draft_below_range_is_looser_and_still_flagged() -> None:
    result = compare(draft(9), spread_peers())

    assert result.range_position == RangePosition.LOOSER
    assert result.verdict == Verdict.FLAG


def test_draft_below_range_is_stricter_when_lower_is_stricter() -> None:
    result = compare(
        draft(9, MAXIMUM_AGE), spread_peers(MAXIMUM_AGE), MAXIMUM_AGE
    )

    assert result.range_position == RangePosition.STRICTER
    assert result.verdict == Verdict.FLAG


# Minimum number of peers


def test_fewer_than_ten_peers_never_flags() -> None:
    peers = spread_peers()[:9]

    result = compare(draft(1000), peers)

    assert result.verdict == Verdict.INSUFFICIENT_PEERS
    assert result.percentile_range is None


def test_peers_not_stating_a_value_do_not_count_towards_ten() -> None:
    peers = spread_peers()[:9] + [profile("NCT-SILENT", None)]

    result = compare(draft(1000), peers)

    assert result.verdict == Verdict.INSUFFICIENT_PEERS
    summary = group(result, PeerGroup.ALL)
    assert (summary.peer_count, summary.stating_count) == (10, 9)


def test_draft_without_a_value_cannot_be_compared() -> None:
    result = compare(draft(None), spread_peers())

    assert result.verdict == Verdict.NO_DRAFT_VALUE


# Recent peers


def test_draft_stricter_than_every_recent_peer_is_flagged() -> None:
    # 70 sits inside the all-peer range, so only the recent group flags.
    peers = spread_peers() + recent_peers(20, 30, 40)

    result = compare(draft(70), peers)

    assert result.range_position == RangePosition.INSIDE
    assert result.verdict == Verdict.FLAG
    assert result.flagging_groups == frozenset({PeerGroup.RECENT})


def test_recent_group_of_two_peers_is_too_small_to_flag() -> None:
    peers = spread_peers() + recent_peers(20, 30)

    result = compare(draft(70), peers)

    assert result.verdict == Verdict.NO_FLAG
    assert not group(result, PeerGroup.RECENT).is_large_enough


def test_draft_equal_to_strictest_recent_peer_is_not_flagged() -> None:
    peers = spread_peers() + recent_peers(20, 30, 70)

    result = compare(draft(70), peers)

    assert result.verdict == Verdict.NO_FLAG


def test_recent_window_includes_exactly_three_years_before() -> None:
    on_edge = profile("NCT-EDGE", 10, start_date=date(2013, 12, 19))
    just_outside = profile("NCT-OLD", 10, start_date=date(2013, 12, 18))
    undated = profile("NCT-UNDATED", 10, start_date=None)

    result = compare(draft(50), [on_edge, just_outside, undated])

    groups_by_trial = {
        evidence.trial_id: evidence.groups for evidence in result.evidence
    }
    assert PeerGroup.RECENT in groups_by_trial["NCT-EDGE"]
    assert PeerGroup.RECENT not in groups_by_trial["NCT-OLD"]
    assert PeerGroup.RECENT not in groups_by_trial["NCT-UNDATED"]


# Same-class peers


def test_draft_stricter_than_every_same_class_peer_is_flagged() -> None:
    peers = spread_peers() + same_class_peers(20, 30, 40)

    result = compare(draft(70), peers)

    assert result.verdict == Verdict.FLAG
    assert result.flagging_groups == frozenset({PeerGroup.SAME_CLASS})


def test_peer_of_another_class_is_not_same_class() -> None:
    other_class = profile(
        "NCT-DPP4", 10, drug_classes=frozenset({DrugClass.DPP4_INHIBITOR})
    )

    result = compare(draft(50), [other_class])

    assert result.evidence[0].groups == frozenset({PeerGroup.ALL})


# Evidence and the whole draft


def test_evidence_lists_every_peer_with_its_value_and_source() -> None:
    peers = [profile("NCT-A", 12), profile("NCT-SILENT", None)]

    result = compare(draft(50), peers)

    assert [
        (evidence.trial_id, evidence.value) for evidence in result.evidence
    ] == [
        ("NCT-A", DimensionValue(value=12, source="test value 12")),
        ("NCT-SILENT", None),
    ]


def test_compare_draft_returns_one_result_per_dimension() -> None:
    results = compare_draft(draft(50), PROTOCOL_DATE, spread_peers())

    assert [result.dimension.dimension_id for result in results] == [
        DimensionId.MINIMUM_AGE,
        DimensionId.MAXIMUM_AGE,
        DimensionId.ENROLLMENT,
    ]
    assert [result.verdict for result in results] == [
        Verdict.NO_FLAG,
        Verdict.NO_DRAFT_VALUE,
        Verdict.NO_DRAFT_VALUE,
    ]
