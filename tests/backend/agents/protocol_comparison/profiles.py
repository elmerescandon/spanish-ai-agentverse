"""Trial profiles with hand-picked values for comparison tests.

spread_peers() gives 11 peers valued 0, 10, ..., 100 that all started on
the same day and share nothing with the draft, so they are equal-weight
T3 peers: n_eff is exactly 11 and the 10th-90th percentile range is
exactly 10 to 90, weighted or not.
"""

from datetime import date

from backend.agents.protocol_comparison.comparison import (
    Category,
    CategoryResult,
    DimensionComparison,
    compare_dimension,
)
from backend.agents.protocol_comparison.dimensions import (
    REGISTRY_DIMENSIONS,
    Dimension,
    DimensionId,
    DimensionValue,
    TrialProfile,
)
from backend.agents.protocol_comparison.rules import DrugClass

PROTOCOL_DATE = date(2016, 12, 19)
OLD_START = date(2005, 1, 1)
RECENT_START = date(2015, 1, 1)
DRAFT_DRUGS = frozenset({"canagliflozin"})
DRAFT_CLASSES = frozenset({DrugClass.SGLT2_INHIBITOR})
SPREAD_VALUES = tuple(float(value) for value in range(0, 101, 10))

MINIMUM_AGE = next(
    dimension
    for dimension in REGISTRY_DIMENSIONS
    if dimension.dimension_id == DimensionId.MINIMUM_AGE
)
MAXIMUM_AGE = next(
    dimension
    for dimension in REGISTRY_DIMENSIONS
    if dimension.dimension_id == DimensionId.MAXIMUM_AGE
)


def profile(
    trial_id: str,
    value: float | None,
    dimension: Dimension = MINIMUM_AGE,
    start_date: date | None = OLD_START,
    drug_classes: frozenset[DrugClass] = frozenset(),
    drugs: frozenset[str] = frozenset(),
    is_ongoing: bool = False,
) -> TrialProfile:
    values = {}
    if value is not None:
        values[dimension.dimension_id] = DimensionValue(
            value=value, source=f"test value {value}"
        )
    return TrialProfile(
        trial_id=trial_id,
        start_date=start_date,
        drugs=drugs,
        drug_classes=drug_classes,
        is_ongoing=is_ongoing,
        values=values,
    )


def spread_peers(dimension: Dimension = MINIMUM_AGE) -> list[TrialProfile]:
    return [
        profile(f"NCT-SPREAD-{index}", value, dimension)
        for index, value in enumerate(SPREAD_VALUES)
    ]


def draft(
    value: float | None, dimension: Dimension = MINIMUM_AGE
) -> TrialProfile:
    return profile(
        "DRAFT",
        value,
        dimension,
        start_date=None,
        drug_classes=DRAFT_CLASSES,
        drugs=DRAFT_DRUGS,
    )


def compare(
    draft_profile: TrialProfile,
    peers: list[TrialProfile],
    dimension: Dimension = MINIMUM_AGE,
) -> DimensionComparison:
    return compare_dimension(dimension, draft_profile, PROTOCOL_DATE, peers)


def category(result: DimensionComparison, wanted: Category) -> CategoryResult:
    return next(
        summary for summary in result.categories if summary.category == wanted
    )


def recent_peers(
    *values: float, dimension: Dimension = MINIMUM_AGE
) -> list[TrialProfile]:
    return [
        profile(
            f"NCT-RECENT-{index}", value, dimension, start_date=RECENT_START
        )
        for index, value in enumerate(values)
    ]


def same_drug_peers(
    *values: float, dimension: Dimension = MINIMUM_AGE
) -> list[TrialProfile]:
    return [
        profile(
            f"NCT-DRUG-{index}",
            value,
            dimension,
            drug_classes=DRAFT_CLASSES,
            drugs=DRAFT_DRUGS,
        )
        for index, value in enumerate(values)
    ]
