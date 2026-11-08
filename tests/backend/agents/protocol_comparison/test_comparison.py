"""Tests for comparing a draft against weighted peers on one dimension.

Expected values are worked out by hand; see profiles.py for the shared
peer sets. Stefan's rule: n_eff < 5 never flags, 5-9 flags only beyond
every peer (S3), >= 10 flags outside the 10th-90th percentile (S2).
"""

from datetime import date

import pytest

from backend.agents.protocol_comparison.comparison import (
    Category,
    FlagRule,
    PercentileRange,
    RangePosition,
    Severity,
    Tier,
    Verdict,
    compare_draft,
    effective_sample_size,
    peer_weight,
    weighted_percentile,
)
from backend.agents.protocol_comparison.dimensions import (
    DimensionId,
    DimensionValue,
)
from backend.agents.protocol_comparison.rules import (
    DEFAULT_FLAG_RULES,
    DrugClass,
)
from tests.backend.agents.protocol_comparison.profiles import (
    DRAFT_CLASSES,
    MAXIMUM_AGE,
    PROTOCOL_DATE,
    SPREAD_VALUES,
    category,
    compare,
    draft,
    profile,
    recent_peers,
    same_drug_peers,
    spread_peers,
)

# Weights and statistics


def test_weighted_percentile_with_equal_weights_matches_linear() -> None:
    weights = [1.0] * len(SPREAD_VALUES)

    assert weighted_percentile(SPREAD_VALUES, weights, 10) == 10.0
    assert weighted_percentile(SPREAD_VALUES, weights, 90) == 90.0


def test_weighted_percentile_leans_towards_heavier_values() -> None:
    # Cumulative positions 0, 2/3, 1: the median sits 0.75 of the way
    # from 0 to 50, not at 50 as it would with equal weights.
    assert weighted_percentile([100, 0, 50], [1, 2, 1], 50) == 37.5


def test_effective_sample_size_counts_unequal_weights_as_fewer() -> None:
    # (1 + 0.5)^2 / (1^2 + 0.5^2) = 2.25 / 1.25
    assert effective_sample_size([1.0, 0.5]) == pytest.approx(1.8)
    assert effective_sample_size([0.3] * 7) == pytest.approx(7.0)


@pytest.mark.parametrize(
    ("tier", "start_date", "is_ongoing", "expected_weight"),
    [
        (Tier.SAME_DRUG, PROTOCOL_DATE, False, 1.0),
        (Tier.SAME_CLASS, PROTOCOL_DATE, False, 0.6),
        (Tier.SAME_DISEASE, PROTOCOL_DATE, False, 0.3),
        (Tier.SAME_DRUG, date(2011, 12, 19), False, 0.5),
        (Tier.SAME_DRUG, date(2006, 12, 19), False, 0.25),
        (Tier.SAME_CLASS, date(2011, 12, 19), True, 0.6 * 0.5 * 0.8),
        (Tier.SAME_DRUG, None, False, 1.0),
    ],
)
def test_peer_weight_follows_tier_recency_and_status(
    tier: Tier,
    start_date: date | None,
    is_ongoing: bool,
    expected_weight: float,
) -> None:
    peer = profile("NCT-P", 1, start_date=start_date, is_ongoing=is_ongoing)

    weight = peer_weight(peer, tier, PROTOCOL_DATE, DEFAULT_FLAG_RULES)

    assert weight == pytest.approx(expected_weight, rel=0.01)


# Tiers


def test_peer_sharing_a_drug_is_same_drug_tier() -> None:
    result = compare(draft(50), same_drug_peers(10))

    assert result.evidence[0].tier == Tier.SAME_DRUG
    assert Category.SAME_DRUG in result.evidence[0].categories


def test_peer_sharing_only_a_class_is_same_class_tier() -> None:
    peer = profile(
        "NCT-CLASS",
        10,
        drug_classes=DRAFT_CLASSES,
        drugs=frozenset({"dapagliflozin"}),
    )

    result = compare(draft(50), [peer])

    assert result.evidence[0].tier == Tier.SAME_CLASS
    assert Category.SAME_DRUG not in result.evidence[0].categories


def test_peer_sharing_nothing_is_same_disease_tier() -> None:
    peer = profile(
        "NCT-DPP4",
        10,
        drug_classes=frozenset({DrugClass.DPP4_INHIBITOR}),
        drugs=frozenset({"sitagliptin"}),
    )

    result = compare(draft(50), [peer])

    assert result.evidence[0].tier == Tier.SAME_DISEASE


# The official (weighted) verdict


def test_ten_or_more_effective_peers_flag_beyond_90th_percentile() -> None:
    result = compare(draft(95), spread_peers())

    weighted = category(result, Category.WEIGHTED)
    assert weighted.n_eff == pytest.approx(11.0)
    assert weighted.percentile_range == PercentileRange(low=10.0, high=90.0)
    assert weighted.range_position == RangePosition.STRICTER
    assert weighted.rule == FlagRule.PERCENTILE_RANGE
    assert (result.verdict, result.severity) == (Verdict.FLAG, Severity.S2)


def test_value_on_the_90th_percentile_is_not_flagged() -> None:
    result = compare(draft(90), spread_peers())

    assert result.verdict == Verdict.NO_FLAG
    assert result.severity is None


def test_value_on_the_10th_percentile_with_light_weights_is_inside() -> None:
    # Spread peers weigh about 0.057 each; float noise in the weighted
    # sums must not push the 10th percentile above 10.
    result = compare(draft(10), spread_peers())

    assert result.verdict == Verdict.NO_FLAG


def test_looser_than_10th_percentile_is_flagged() -> None:
    result = compare(draft(5), spread_peers())

    assert category(result, Category.WEIGHTED).range_position == (
        RangePosition.LOOSER
    )
    assert result.verdict == Verdict.FLAG


def test_lower_is_stricter_dimension_flags_below_range_as_stricter() -> None:
    result = compare(
        draft(5, MAXIMUM_AGE), spread_peers(MAXIMUM_AGE), MAXIMUM_AGE
    )

    assert category(result, Category.WEIGHTED).range_position == (
        RangePosition.STRICTER
    )


def test_five_to_nine_effective_peers_flag_only_beyond_every_peer() -> None:
    peers = spread_peers()[:7]  # 0..60

    beyond = compare(draft(61), peers)
    inside = compare(draft(55), peers)

    weighted = category(beyond, Category.WEIGHTED)
    assert weighted.rule == FlagRule.BEYOND_EVERY_PEER
    assert (beyond.verdict, beyond.severity) == (Verdict.FLAG, Severity.S3)
    assert inside.verdict == Verdict.NO_FLAG


def test_matching_the_strictest_peer_is_not_beyond_every_peer() -> None:
    result = compare(draft(60), spread_peers()[:7])

    assert result.verdict == Verdict.NO_FLAG


def test_fewer_than_five_effective_peers_never_flag() -> None:
    result = compare(draft(1000), spread_peers()[:4])

    assert result.verdict == Verdict.INSUFFICIENT_PEERS
    assert category(result, Category.WEIGHTED).percentile_range is None


def test_effective_peers_not_peer_count_decide_the_minimum() -> None:
    # One heavy same-drug peer and five light old peers: 6 peers, but
    # n_eff = (1 + 5 * 0.075)^2 / (1 + 5 * 0.075^2) = 1.84.
    heavy = profile(
        "NCT-HEAVY",
        10,
        start_date=PROTOCOL_DATE,
        drug_classes=DRAFT_CLASSES,
        drugs=frozenset({"canagliflozin"}),
    )
    light = [
        profile(f"NCT-LIGHT-{index}", 10, start_date=date(2006, 12, 19))
        for index in range(5)
    ]

    result = compare(draft(1000), [heavy, *light])

    weighted = category(result, Category.WEIGHTED)
    assert weighted.n_eff == pytest.approx(1.84, abs=0.01)
    assert result.verdict == Verdict.INSUFFICIENT_PEERS
    # Unweighted, the same six peers are enough for an advisory flag.
    assert category(result, Category.ALL).verdict == Verdict.FLAG


def test_draft_without_a_value_cannot_be_compared() -> None:
    result = compare(draft(None), spread_peers())

    assert result.verdict == Verdict.NO_DRAFT_VALUE
    assert result.categories == ()


# Category breakdown


def test_every_category_is_reported_in_order() -> None:
    result = compare(draft(50), spread_peers())

    assert [summary.category for summary in result.categories] == [
        Category.WEIGHTED,
        Category.ALL,
        Category.RECENT,
        Category.SAME_DRUG,
    ]


def test_recent_category_can_flag_on_its_own() -> None:
    peers = spread_peers() + recent_peers(20, 30, 40, 50, 60)

    result = compare(draft(70), peers)

    recent = category(result, Category.RECENT)
    assert (recent.stating_count, recent.n_eff) == (5, 5.0)
    assert (recent.verdict, recent.severity) == (Verdict.FLAG, Severity.S3)
    assert category(result, Category.ALL).verdict == Verdict.NO_FLAG


def test_small_category_reports_insufficient_peers() -> None:
    result = compare(draft(50), spread_peers() + recent_peers(20, 30))

    assert category(result, Category.RECENT).verdict == (
        Verdict.INSUFFICIENT_PEERS
    )


def test_recent_window_includes_exactly_three_years_before() -> None:
    on_edge = profile("NCT-EDGE", 10, start_date=date(2013, 12, 19))
    just_outside = profile("NCT-OLD", 10, start_date=date(2013, 12, 18))
    undated = profile("NCT-UNDATED", 10, start_date=None)

    result = compare(draft(50), [on_edge, just_outside, undated])

    categories_by_trial = {
        evidence.trial_id: evidence.categories for evidence in result.evidence
    }
    assert Category.RECENT in categories_by_trial["NCT-EDGE"]
    assert Category.RECENT not in categories_by_trial["NCT-OLD"]
    assert Category.RECENT not in categories_by_trial["NCT-UNDATED"]


# Same-drug note (our addition, not one of Stefan's flags)


def test_note_when_draft_is_stricter_than_every_same_drug_peer() -> None:
    result = compare(draft(50), spread_peers() + same_drug_peers(20, 30))

    assert result.verdict == Verdict.NO_FLAG
    assert result.same_drug_note is not None
    assert result.same_drug_note.position == RangePosition.STRICTER
    assert result.same_drug_note.peer_ids == ("NCT-DRUG-0", "NCT-DRUG-1")


def test_note_when_draft_is_looser_than_every_same_drug_peer() -> None:
    result = compare(draft(10), spread_peers() + same_drug_peers(20, 30))

    assert result.same_drug_note is not None
    assert result.same_drug_note.position == RangePosition.LOOSER


def test_no_note_when_draft_matches_a_same_drug_peer() -> None:
    result = compare(draft(30), spread_peers() + same_drug_peers(20, 30))

    assert result.same_drug_note is None


def test_no_note_without_same_drug_peers() -> None:
    assert compare(draft(50), spread_peers()).same_drug_note is None


# Evidence and the whole draft


def test_evidence_lists_every_peer_with_value_tier_and_weight() -> None:
    peers = [profile("NCT-A", 12), profile("NCT-SILENT", None)]

    result = compare(draft(50), peers)

    first, second = result.evidence
    assert (first.trial_id, first.value) == (
        "NCT-A",
        DimensionValue(value=12, source="test value 12"),
    )
    assert first.tier == Tier.SAME_DISEASE
    assert first.weight > 0
    assert (second.trial_id, second.value) == ("NCT-SILENT", None)


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
