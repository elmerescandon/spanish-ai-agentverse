"""Tests for finding an uploaded protocol's peers from its parsed values.

The registry search follows the protocol's phase and ages; peers come
from memory, then the committed snapshot, then a live search.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from backend.agents.protocol_comparison.agent import (
    SessionLabReadingCache,
    compare_with_registry_peers,
)
from backend.agents.protocol_comparison.logic import (
    PEER_CONDITION,
    peer_query_for,
)
from backend.agents.protocol_comparison.peer_store import (
    PeerSource,
    PeerStore,
)
from backend.clients.clinicaltrials_gov import (
    ClinicalTrialsGovError,
    PeerSearchQuery,
    Phase,
    Population,
    StudyRecord,
)
from backend.shared.messages import ProtocolDocument, TrialPhase
from tests.backend.agents.protocol_comparison.builders import make_study
from tests.backend.agents.protocol_comparison.protocols import (
    DRAFT_NCT_ID,
    REVIEW_DATE,
    cited,
    parsed_protocol,
)

REVIEW_DATE_TIME = datetime(2026, 11, 8, tzinfo=UTC)


class RecordingSearch:
    """Registry search double: records each query, returns fixed studies."""

    def __init__(
        self, studies: list[StudyRecord], error: Exception | None = None
    ) -> None:
        self.queries: list[PeerSearchQuery] = []
        self._studies = studies
        self._error = error

    async def __call__(self, query: PeerSearchQuery) -> list[StudyRecord]:
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return self._studies


def with_design(
    phase: TrialPhase | None = TrialPhase.PHASE3,
    min_age: float | None = 10.0,
    max_age: float | None = 17.0,
    is_max_age_inclusive: bool | None = None,
) -> ProtocolDocument:
    document = parsed_protocol()
    assert document.design is not None
    document.design.phase = None if phase is None else cited(phase, "", 1)
    document.design.min_age_years = (
        None if min_age is None else cited(min_age, "", 1)
    )
    document.design.max_age_years = (
        None if max_age is None else cited(max_age, "", 1)
    )
    document.design.is_max_age_inclusive = is_max_age_inclusive
    return document


def test_search_uses_the_protocols_phase_population_and_own_id() -> None:
    query = peer_query_for(parsed_protocol(), REVIEW_DATE)

    assert query.condition == PEER_CONDITION
    assert query.phases == (Phase.PHASE3,)
    assert query.population == Population.PEDIATRIC
    assert query.exclude_nct_ids == frozenset({DRAFT_NCT_ID})


def test_search_window_starts_on_1_january_ten_years_back() -> None:
    query = peer_query_for(parsed_protocol(), date(2026, 11, 8))

    assert query.started_on_or_after == date(2016, 1, 1)
    assert query.started_before is None


def test_same_year_reviews_share_one_search() -> None:
    january = peer_query_for(parsed_protocol(), date(2026, 1, 2))
    december = peer_query_for(parsed_protocol(), date(2026, 12, 30))

    assert january == december


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        (TrialPhase.PHASE2_PHASE3, (Phase.PHASE2, Phase.PHASE3)),
        (TrialPhase.PHASE4, (Phase.PHASE4,)),
        (TrialPhase.UNKNOWN, (Phase.PHASE2, Phase.PHASE3)),
        (None, (Phase.PHASE2, Phase.PHASE3)),
    ],
)
def test_search_phases_follow_the_parsed_phase(
    phase: TrialPhase | None, expected: tuple[Phase, ...]
) -> None:
    query = peer_query_for(with_design(phase=phase), REVIEW_DATE)

    assert query.phases == expected


@pytest.mark.parametrize(
    ("min_age", "max_age", "expected"),
    [
        (10.0, 17.0, Population.PEDIATRIC),
        # "≥10 to <18": the parser stores 18 with an exclusive bound.
        (10.0, 18.0, Population.PEDIATRIC),
        (18.0, 75.0, Population.ADULT),
        (12.0, 75.0, Population.ADULT),
        (None, None, Population.ADULT),
        (10.0, None, Population.ADULT),
    ],
)
def test_search_population_follows_the_parsed_ages(
    min_age: float | None, max_age: float | None, expected: Population
) -> None:
    document = with_design(min_age=min_age, max_age=max_age)

    assert peer_query_for(document, REVIEW_DATE).population == expected


def test_protocol_without_an_nct_id_excludes_nothing() -> None:
    document = parsed_protocol()
    assert document.design is not None
    document.design.nct_id = None

    assert peer_query_for(document, REVIEW_DATE).exclude_nct_ids == (
        frozenset()
    )


async def test_new_search_runs_live_once_then_comes_from_memory(
    tmp_path: Path,
) -> None:
    search = RecordingSearch([make_study(nct_id="NCT00000001")])
    source = PeerSource(PeerStore(tmp_path), search=search)
    query = peer_query_for(parsed_protocol(), REVIEW_DATE)

    first = await source.studies_for(query)
    second = await source.studies_for(query)

    assert [study.nct_id for study in second] == ["NCT00000001"]
    assert first == second
    assert search.queries == [query]
    assert list(tmp_path.iterdir()) == []


async def test_committed_snapshot_is_used_without_searching(
    tmp_path: Path,
) -> None:
    query = peer_query_for(parsed_protocol(), REVIEW_DATE)
    store = PeerStore(tmp_path)
    store.save(query, [make_study(nct_id="NCT00000002")], REVIEW_DATE_TIME)
    search = RecordingSearch([])

    studies = await PeerSource(store, search=search).studies_for(query)

    assert [study.nct_id for study in studies] == ["NCT00000002"]
    assert search.queries == []


async def test_failed_search_raises_and_is_retried_next_time(
    tmp_path: Path,
) -> None:
    query = peer_query_for(parsed_protocol(), REVIEW_DATE)
    failing = RecordingSearch([], error=ClinicalTrialsGovError("down"))
    source = PeerSource(PeerStore(tmp_path), search=failing)

    with pytest.raises(ClinicalTrialsGovError):
        await source.studies_for(query)
    with pytest.raises(ClinicalTrialsGovError):
        await source.studies_for(query)

    assert len(failing.queries) == 2


async def test_comparison_searches_with_the_protocols_values(
    tmp_path: Path,
) -> None:
    peer = make_study(nct_id="NCT00000001", minimum_age="10 Years")
    search = RecordingSearch([peer])
    store = PeerStore(tmp_path)

    comparison = await compare_with_registry_peers(
        parsed_protocol(),
        REVIEW_DATE,
        PeerSource(store, search=search),
        SessionLabReadingCache(store),
        lab_llm=None,
    )

    [query] = search.queries
    assert query.population == Population.PEDIATRIC
    assert comparison.peer_search == query
    assert comparison.review_date == REVIEW_DATE
    peer_ids = {
        evidence.trial_id for evidence in comparison.results[0].evidence
    }
    assert peer_ids == {"NCT00000001"}
