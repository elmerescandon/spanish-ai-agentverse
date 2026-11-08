"""Tests for the values suggested to bring a flagged draft back in line."""

from backend.agents.protocol_comparison.comparison import (
    Category,
    DimensionComparison,
    FlagRule,
)
from backend.agents.protocol_comparison.suggestions import (
    Suggestion,
    suggest_values,
)
from tests.backend.agents.protocol_comparison.profiles import (
    MAXIMUM_AGE,
    compare,
    draft,
    recent_peers,
    spread_peers,
)

ALL_SPREAD_IDS = tuple(f"NCT-SPREAD-{index}" for index in range(11))


def suggestion_for(
    result: DimensionComparison, category: Category
) -> Suggestion:
    return next(
        suggestion
        for suggestion in suggest_values(result)
        if suggestion.category == category
    )


def test_unflagged_dimension_gets_no_suggestion() -> None:
    result = compare(draft(50), spread_peers())

    assert suggest_values(result) == ()


def test_each_flagging_category_gets_its_own_suggestion() -> None:
    result = compare(draft(95), spread_peers())

    assert suggest_values(result) == (
        Suggestion(
            category=Category.WEIGHTED,
            rule=FlagRule.PERCENTILE_RANGE,
            suggested_value=90.0,
            peer_ids=ALL_SPREAD_IDS,
        ),
        Suggestion(
            category=Category.ALL,
            rule=FlagRule.PERCENTILE_RANGE,
            suggested_value=90.0,
            peer_ids=ALL_SPREAD_IDS,
        ),
    )


def test_looser_value_below_range_is_brought_up_to_the_range_edge() -> None:
    result = compare(draft(5), spread_peers())

    assert suggestion_for(result, Category.WEIGHTED).suggested_value == 10.0


def test_lower_is_stricter_dimension_below_range_goes_to_low_edge() -> None:
    result = compare(
        draft(5, MAXIMUM_AGE), spread_peers(MAXIMUM_AGE), MAXIMUM_AGE
    )

    assert suggestion_for(result, Category.WEIGHTED).suggested_value == 10.0


def test_beyond_every_peer_is_brought_to_the_nearest_peer_value() -> None:
    result = compare(draft(61), spread_peers()[:7])  # peers 0..60

    suggestion = suggestion_for(result, Category.WEIGHTED)

    assert suggestion.rule == FlagRule.BEYOND_EVERY_PEER
    assert suggestion.suggested_value == 60.0


def test_recent_flag_suggests_the_nearest_recent_value() -> None:
    result = compare(
        draft(70), spread_peers() + recent_peers(20, 60, 40, 30, 50)
    )

    suggestion = suggestion_for(result, Category.RECENT)

    assert suggestion.suggested_value == 60.0
    assert suggestion.peer_ids == tuple(f"NCT-RECENT-{i}" for i in range(5))


def test_nearest_peer_is_the_lowest_when_draft_is_below_every_peer() -> None:
    peers = spread_peers(MAXIMUM_AGE) + recent_peers(
        80, 60, 70, 90, 100, dimension=MAXIMUM_AGE
    )

    result = compare(draft(50, MAXIMUM_AGE), peers, MAXIMUM_AGE)

    assert suggestion_for(result, Category.RECENT).suggested_value == 60.0
