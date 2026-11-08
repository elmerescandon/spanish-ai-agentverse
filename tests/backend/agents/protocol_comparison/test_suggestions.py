"""Tests for the values suggested to bring a flagged draft back in line."""

from backend.agents.protocol_comparison.suggestions import (
    Suggestion,
    SuggestionBasis,
    suggest_values,
)
from tests.backend.agents.protocol_comparison.profiles import (
    MAXIMUM_AGE,
    compare,
    draft,
    recent_peers,
    same_class_peers,
    spread_peers,
)

ALL_SPREAD_IDS = tuple(f"NCT-SPREAD-{index}" for index in range(11))


def test_unflagged_dimension_gets_no_suggestion() -> None:
    result = compare(draft(50), spread_peers())

    assert suggest_values(result) == ()


def test_value_above_range_is_brought_down_to_the_range_edge() -> None:
    result = compare(draft(95), spread_peers())

    assert suggest_values(result) == (
        Suggestion(
            basis=SuggestionBasis.PEER_RANGE,
            suggested_value=90.0,
            peer_ids=ALL_SPREAD_IDS,
        ),
    )


def test_looser_value_below_range_is_brought_up_to_the_range_edge() -> None:
    result = compare(draft(5), spread_peers())

    [suggestion] = suggest_values(result)

    assert suggestion.suggested_value == 10.0


def test_lower_is_stricter_dimension_below_range_goes_to_low_edge() -> None:
    result = compare(
        draft(5, MAXIMUM_AGE), spread_peers(MAXIMUM_AGE), MAXIMUM_AGE
    )

    [suggestion] = suggest_values(result)

    assert suggestion.suggested_value == 10.0


def test_stricter_than_recent_peers_matches_strictest_recent_peer() -> None:
    result = compare(draft(70), spread_peers() + recent_peers(20, 40, 30))

    assert suggest_values(result) == (
        Suggestion(
            basis=SuggestionBasis.RECENT_PEERS,
            suggested_value=40.0,
            peer_ids=("NCT-RECENT-0", "NCT-RECENT-1", "NCT-RECENT-2"),
        ),
    )


def test_strictest_peer_is_the_lowest_when_lower_is_stricter() -> None:
    peers = spread_peers(MAXIMUM_AGE) + recent_peers(
        80, 60, 70, dimension=MAXIMUM_AGE
    )

    result = compare(draft(50, MAXIMUM_AGE), peers, MAXIMUM_AGE)

    [suggestion] = suggest_values(result)
    assert suggestion.suggested_value == 60.0


def test_same_class_flag_suggests_strictest_same_class_peer() -> None:
    result = compare(draft(70), spread_peers() + same_class_peers(25, 35, 45))

    [suggestion] = suggest_values(result)

    assert suggestion.basis == SuggestionBasis.SAME_CLASS_PEERS
    assert suggestion.suggested_value == 45.0


def test_range_and_recent_flags_give_one_suggestion_each() -> None:
    # 14 values now: the 90th percentile is 80 + 0.7 * (90 - 80) = 87.
    result = compare(draft(95), spread_peers() + recent_peers(20, 30, 40))

    assert [
        (suggestion.basis, suggestion.suggested_value)
        for suggestion in suggest_values(result)
    ] == [
        (SuggestionBasis.PEER_RANGE, 87.0),
        (SuggestionBasis.RECENT_PEERS, 40.0),
    ]
