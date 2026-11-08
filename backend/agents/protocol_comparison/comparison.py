"""Compare a draft against its peers, dimension by dimension. No I/O.

Follows Stefan's comparison thresholds: every peer gets a tier (same
drug, same class, same disease) and a weight, and the official verdict
uses all peers weighted, with Kish's effective sample size (n_eff)
deciding how strong a flag can be. The same rule also runs, unweighted,
on three categories of peers (all, recent, same drug) so a reviewer can
see where the draft differs. The same-drug note is our addition, not
one of Stefan's flags.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import accumulate

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

DAYS_PER_YEAR = 365.25
PERCENT = 100
# n_eff and percentiles are compared against thresholds and draft values;
# rounding stops float noise in weighted sums (e.g. 9.9999999 or
# 10.000000000000002) from flipping a comparison at its edge.
FLOAT_DECIMALS = 9


class Tier(StrEnum):
    """How closely a peer matches the draft (Stefan's T1, T2, T3)."""

    SAME_DRUG = "SAME_DRUG"
    SAME_CLASS = "SAME_CLASS"
    SAME_DISEASE = "SAME_DISEASE"


class Category(StrEnum):
    """A view of the peers; WEIGHTED gives the official verdict."""

    WEIGHTED = "WEIGHTED"
    ALL = "ALL"
    RECENT = "RECENT"
    SAME_DRUG = "SAME_DRUG"


class RangePosition(StrEnum):
    """Where the draft sits against a category's peers."""

    STRICTER = "STRICTER"
    INSIDE = "INSIDE"
    LOOSER = "LOOSER"


class Verdict(StrEnum):
    """Outcome of comparing one dimension, or one category of it."""

    FLAG = "FLAG"
    NO_FLAG = "NO_FLAG"
    INSUFFICIENT_PEERS = "INSUFFICIENT_PEERS"
    NO_DRAFT_VALUE = "NO_DRAFT_VALUE"


class Severity(StrEnum):
    """Stefan's severity tiers: S1 blocker, S2 major, S3 minor."""

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"


class FlagRule(StrEnum):
    """Which of Stefan's rules applies, given the evidence available."""

    PERCENTILE_RANGE = "PERCENTILE_RANGE"  # n_eff >= full_n_eff
    BEYOND_EVERY_PEER = "BEYOND_EVERY_PEER"  # min_n_eff <= n_eff < full


@dataclass(frozen=True)
class PercentileRange:
    """The range a draft value is expected to fall in."""

    low: float
    high: float


@dataclass(frozen=True)
class PeerEvidence:
    """One peer's value, tier, weight and the categories it is in."""

    trial_id: str
    value: DimensionValue | None
    tier: Tier
    weight: float
    categories: frozenset[Category]


@dataclass(frozen=True)
class CategoryResult:
    """How the draft compares with one category of peers.

    rule is the rule the evidence allows (None when there is too little);
    percentile_range is set only when the percentile rule applies.
    """

    category: Category
    peer_count: int
    stating_count: int
    n_eff: float
    verdict: Verdict
    severity: Severity | None
    rule: FlagRule | None
    percentile_range: PercentileRange | None
    range_position: RangePosition | None


@dataclass(frozen=True)
class SameDrugNote:
    """The draft is beyond every same-drug peer (our addition, no flag)."""

    position: RangePosition
    peer_ids: tuple[str, ...]


@dataclass(frozen=True)
class DimensionComparison:
    """The draft against its peers on one dimension, with the evidence.

    verdict and severity are the official (weighted) result; categories
    holds the weighted result first, then the per-category breakdown.
    """

    dimension: Dimension
    draft_value: DimensionValue | None
    verdict: Verdict
    severity: Severity | None
    categories: tuple[CategoryResult, ...]
    same_drug_note: SameDrugNote | None
    evidence: tuple[PeerEvidence, ...]

    @property
    def flagged_categories(self) -> tuple[CategoryResult, ...]:
        return tuple(
            result
            for result in self.categories
            if result.verdict == Verdict.FLAG
        )


def weighted_percentile(
    values: Sequence[float], weights: Sequence[float], percentile: float
) -> float:
    """Weighted linear-interpolated percentile.

    With equal weights it equals numpy's default (linear) percentile.
    Each sorted value sits at (cumulative weight - own weight) /
    (total weight - last weight), so heavier values take up more room.
    """
    if not values or len(values) != len(weights):
        raise ValueError(
            "expected equally long, non-empty values and weights, got "
            f"{len(values)} values and {len(weights)} weights"
        )
    pairs = sorted(zip(values, weights, strict=True))
    if len(pairs) == 1:
        return float(pairs[0][0])
    sorted_values = [value for value, _ in pairs]
    sorted_weights = [weight for _, weight in pairs]
    cumulative = list(accumulate(sorted_weights))
    span = cumulative[-1] - sorted_weights[-1]
    positions = [
        (total - weight) / span
        for total, weight in zip(cumulative, sorted_weights, strict=True)
    ]
    target = percentile / PERCENT
    upper = bisect_right(positions, target)
    if upper >= len(positions):
        return float(sorted_values[-1])
    lower = upper - 1
    fraction = (target - positions[lower]) / (
        positions[upper] - positions[lower]
    )
    interpolated = sorted_values[lower] + fraction * (
        sorted_values[upper] - sorted_values[lower]
    )
    return round(float(interpolated), FLOAT_DECIMALS)


def effective_sample_size(weights: Sequence[float]) -> float:
    """Kish's effective sample size: (sum of w)^2 / sum of w^2."""
    squared_total = sum(weight * weight for weight in weights)
    if squared_total == 0:
        return 0.0
    return round(sum(weights) ** 2 / squared_total, FLOAT_DECIMALS)


def assign_tier(peer: TrialProfile, draft: TrialProfile) -> Tier:
    """Same drug beats same class; anything else is same disease."""
    if peer.drugs & draft.drugs:
        return Tier.SAME_DRUG
    if peer.drug_classes & draft.drug_classes:
        return Tier.SAME_CLASS
    return Tier.SAME_DISEASE


def peer_weight(
    peer: TrialProfile, tier: Tier, protocol_date: date, rules: FlagRules
) -> float:
    """Tier weight, halved per half-life of age, reduced if ongoing.

    A peer with no start date is not discounted for age.
    """
    base_weight = {
        Tier.SAME_DRUG: rules.same_drug_weight,
        Tier.SAME_CLASS: rules.same_class_weight,
        Tier.SAME_DISEASE: rules.same_disease_weight,
    }[tier]
    recency = 1.0
    if peer.start_date is not None:
        years_before = max(
            0.0, (protocol_date - peer.start_date).days / DAYS_PER_YEAR
        )
        recency = 0.5 ** (years_before / rules.recency_half_life_years)
    status = rules.ongoing_weight if peer.is_ongoing else 1.0
    return base_weight * recency * status


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February in a year that has none
        return day.replace(year=day.year - years, day=28)


def _is_recent(
    peer: TrialProfile, protocol_date: date, rules: FlagRules
) -> bool:
    window_start = _years_before(protocol_date, rules.recent_window_years)
    return (
        peer.start_date is not None
        and window_start <= peer.start_date < protocol_date
    )


def _position_beyond_every(
    value: float, peer_values: Sequence[float], dimension: Dimension
) -> RangePosition:
    is_above_all = all(value > peer_value for peer_value in peer_values)
    is_below_all = all(value < peer_value for peer_value in peer_values)
    if not (is_above_all or is_below_all):
        return RangePosition.INSIDE
    return _direction(is_above_all, dimension)


def _position_in_range(
    value: float, peer_range: PercentileRange, dimension: Dimension
) -> RangePosition:
    if peer_range.low <= value <= peer_range.high:
        return RangePosition.INSIDE
    return _direction(value > peer_range.high, dimension)


def _direction(is_above: bool, dimension: Dimension) -> RangePosition:
    is_higher_stricter = dimension.stricter_when == StricterWhen.HIGHER
    if is_above == is_higher_stricter:
        return RangePosition.STRICTER
    return RangePosition.LOOSER


def _evaluate_category(
    category: Category,
    members: Sequence[PeerEvidence],
    draft_value: float,
    dimension: Dimension,
    rules: FlagRules,
) -> CategoryResult:
    stating = [peer for peer in members if peer.value is not None]
    values = [peer.value.value for peer in stating if peer.value is not None]
    weights = (
        [peer.weight for peer in stating]
        if category == Category.WEIGHTED
        else [1.0] * len(stating)
    )
    n_eff = effective_sample_size(weights)
    rule: FlagRule | None = None
    peer_range: PercentileRange | None = None
    position: RangePosition | None = None
    severity: Severity | None = None
    if n_eff < rules.min_n_eff:
        verdict = Verdict.INSUFFICIENT_PEERS
    elif n_eff < rules.full_n_eff:
        rule = FlagRule.BEYOND_EVERY_PEER
        position = _position_beyond_every(draft_value, values, dimension)
        severity = Severity.S3
    else:
        rule = FlagRule.PERCENTILE_RANGE
        peer_range = PercentileRange(
            low=weighted_percentile(values, weights, rules.low_percentile),
            high=weighted_percentile(values, weights, rules.high_percentile),
        )
        position = _position_in_range(draft_value, peer_range, dimension)
        severity = Severity.S2
    if position is not None:
        is_flagged = position != RangePosition.INSIDE
        verdict = Verdict.FLAG if is_flagged else Verdict.NO_FLAG
        severity = severity if is_flagged else None
    return CategoryResult(
        category=category,
        peer_count=len(members),
        stating_count=len(stating),
        n_eff=n_eff,
        verdict=verdict,
        severity=severity,
        rule=rule,
        percentile_range=peer_range,
        range_position=position,
    )


def _same_drug_note(
    evidence: Sequence[PeerEvidence],
    draft_value: float,
    dimension: Dimension,
) -> SameDrugNote | None:
    same_drug = [
        peer
        for peer in evidence
        if peer.tier == Tier.SAME_DRUG and peer.value is not None
    ]
    values = [peer.value.value for peer in same_drug if peer.value]
    if not values:
        return None
    position = _position_beyond_every(draft_value, values, dimension)
    if position == RangePosition.INSIDE:
        return None
    return SameDrugNote(
        position=position,
        peer_ids=tuple(peer.trial_id for peer in same_drug),
    )


def _peer_evidence(
    peer: TrialProfile,
    dimension: Dimension,
    draft: TrialProfile,
    protocol_date: date,
    rules: FlagRules,
) -> PeerEvidence:
    tier = assign_tier(peer, draft)
    categories = {Category.ALL}
    if _is_recent(peer, protocol_date, rules):
        categories.add(Category.RECENT)
    if tier == Tier.SAME_DRUG:
        categories.add(Category.SAME_DRUG)
    return PeerEvidence(
        trial_id=peer.trial_id,
        value=peer.values.get(dimension.dimension_id),
        tier=tier,
        weight=peer_weight(peer, tier, protocol_date, rules),
        categories=frozenset(categories),
    )


def compare_dimension(
    dimension: Dimension,
    draft: TrialProfile,
    protocol_date: date,
    peers: Sequence[TrialProfile],
    rules: FlagRules = DEFAULT_FLAG_RULES,
) -> DimensionComparison:
    """Compare the draft's value on one dimension against its peers.

    The official verdict is the weighted one. Each category is judged by
    the same rule on its own peers, unweighted, as a breakdown.
    """
    evidence = tuple(
        _peer_evidence(peer, dimension, draft, protocol_date, rules)
        for peer in peers
    )
    draft_value = draft.values.get(dimension.dimension_id)
    if draft_value is None:
        return DimensionComparison(
            dimension=dimension,
            draft_value=None,
            verdict=Verdict.NO_DRAFT_VALUE,
            severity=None,
            categories=(),
            same_drug_note=None,
            evidence=evidence,
        )
    categories = tuple(
        _evaluate_category(
            category,
            [
                peer
                for peer in evidence
                if category == Category.WEIGHTED or category in peer.categories
            ],
            draft_value.value,
            dimension,
            rules,
        )
        for category in Category
    )
    official = categories[0]
    assert official.category == Category.WEIGHTED
    return DimensionComparison(
        dimension=dimension,
        draft_value=draft_value,
        verdict=official.verdict,
        severity=official.severity,
        categories=categories,
        same_drug_note=_same_drug_note(evidence, draft_value.value, dimension),
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
