"""Tests for the on-disk peer cache, including the committed demo snapshot."""

import asyncio
import dataclasses
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from backend.agents.protocol_comparison.demo import (
    DEMO_DRAFT_NCT_ID,
    DEMO_PEER_QUERY,
)
from backend.agents.protocol_comparison.logic import (
    classify_drug_classes,
    screen_peers,
)
from backend.agents.protocol_comparison.peer_store import (
    PeerStore,
    PeerStoreError,
    load_or_fetch_peers,
    query_id_for,
)
from backend.agents.protocol_comparison.rules import (
    TYPE_2_DIABETES_PEER_CRITERIA,
    DrugClass,
)
from backend.clients.clinicaltrials_gov import (
    PeerSearchQuery,
    Phase,
    Population,
    StudyRecord,
)
from tests.backend.agents.protocol_comparison.builders import make_study

FETCHED_AT = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
COMMITTED_STORE = PeerStore(Path("data/peers"))

QUERY = PeerSearchQuery(
    condition="Diabetes Mellitus, Type 2",
    phases=(Phase.PHASE3,),
    population=Population.PEDIATRIC,
    started_on_or_after=date(2006, 12, 19),
    started_before=date(2016, 12, 19),
)


class FakeSearcher:
    """Registry stand-in that counts searches and returns fixed studies."""

    def __init__(self, studies: list[StudyRecord]) -> None:
        self.studies = studies
        self.search_count = 0

    async def search_studies(
        self, query: PeerSearchQuery
    ) -> list[StudyRecord]:
        self.search_count += 1
        return self.studies


def test_saved_search_loads_back_identically_in_order(tmp_path: Path) -> None:
    store = PeerStore(tmp_path)
    studies = [make_study("NCT00000002"), make_study("NCT00000001")]

    store.save(QUERY, studies, fetched_at=FETCHED_AT)

    assert store.load_studies(QUERY) == studies
    stored = store.load_query(QUERY)
    assert stored is not None
    assert stored.fetched_at == FETCHED_AT
    assert stored.nct_ids == ["NCT00000002", "NCT00000001"]


def test_unseen_query_is_a_cache_miss(tmp_path: Path) -> None:
    assert PeerStore(tmp_path).load_studies(QUERY) is None


def test_query_id_is_stable_and_changes_with_any_filter() -> None:
    later_cutoff = dataclasses.replace(QUERY, started_before=date(2017, 1, 1))
    reordered_phases = dataclasses.replace(
        QUERY, phases=(Phase.PHASE3, Phase.PHASE2)
    )
    same_phases_other_order = dataclasses.replace(
        QUERY, phases=(Phase.PHASE2, Phase.PHASE3)
    )

    assert query_id_for(QUERY) == query_id_for(dataclasses.replace(QUERY))
    assert query_id_for(later_cutoff) != query_id_for(QUERY)
    assert query_id_for(reordered_phases) == query_id_for(
        same_phases_other_order
    )


def test_cached_search_does_not_call_registry(tmp_path: Path) -> None:
    store = PeerStore(tmp_path)
    store.save(QUERY, [make_study()], fetched_at=FETCHED_AT)
    searcher = FakeSearcher([])

    studies = asyncio.run(load_or_fetch_peers(QUERY, searcher, store))

    assert [study.nct_id for study in studies] == ["NCT00000001"]
    assert searcher.search_count == 0


def test_cache_miss_fetches_and_saves(tmp_path: Path) -> None:
    store = PeerStore(tmp_path)
    searcher = FakeSearcher([make_study("NCT00000007")])

    asyncio.run(load_or_fetch_peers(QUERY, searcher, store))
    asyncio.run(load_or_fetch_peers(QUERY, searcher, store))

    assert searcher.search_count == 1
    cached = store.load_studies(QUERY)
    assert cached is not None
    assert [study.nct_id for study in cached] == ["NCT00000007"]


def test_refresh_searches_again_and_overwrites_cache(tmp_path: Path) -> None:
    store = PeerStore(tmp_path)
    store.save(QUERY, [make_study("NCT00000001")], fetched_at=FETCHED_AT)
    searcher = FakeSearcher([make_study("NCT00000009")])

    studies = asyncio.run(
        load_or_fetch_peers(QUERY, searcher, store, refresh=True)
    )

    assert searcher.search_count == 1
    assert [study.nct_id for study in studies] == ["NCT00000009"]
    assert store.load_studies(QUERY) == studies


def test_query_pointing_at_missing_study_file_fails_loudly(
    tmp_path: Path,
) -> None:
    store = PeerStore(tmp_path)
    store.save(QUERY, [make_study("NCT00000001")], fetched_at=FETCHED_AT)
    (tmp_path / "studies" / "NCT00000001.json").unlink()

    with pytest.raises(PeerStoreError, match="NCT00000001"):
        store.load_studies(QUERY)


def test_corrupt_study_file_fails_loudly(tmp_path: Path) -> None:
    store = PeerStore(tmp_path)
    store.save(QUERY, [make_study("NCT00000001")], fetched_at=FETCHED_AT)
    (tmp_path / "studies" / "NCT00000001.json").write_text("{}")

    with pytest.raises(PeerStoreError, match="validation error"):
        store.load_studies(QUERY)


def test_committed_demo_snapshot_screens_to_expected_peers() -> None:
    studies = COMMITTED_STORE.load_studies(DEMO_PEER_QUERY)
    assert studies is not None

    screening = screen_peers(studies, TYPE_2_DIABETES_PEER_CRITERIA)

    assert DEMO_DRAFT_NCT_ID not in {study.nct_id for study in studies}
    assert {study.nct_id for study in screening.peers} == {
        "NCT01554618",
        "NCT02131272",
        "NCT00658021",
        "NCT01779375",
        "NCT01541215",
        "NCT01434186",
        "NCT01485614",
        "NCT02856113",
        "NCT01204775",
        "NCT02725593",
        "NCT01760447",
    }
    assert {excluded.nct_id for excluded in screening.excluded} == {
        "NCT01560676",
        "NCT00949221",
        "NCT02216552",
        "NCT02735044",
        "NCT01334125",
        "NCT02132442",
    }


def test_committed_demo_draft_and_same_class_peer_are_sglt2() -> None:
    draft = COMMITTED_STORE.load_study(DEMO_DRAFT_NCT_ID)
    dapagliflozin_peer = COMMITTED_STORE.load_study("NCT02725593")

    assert classify_drug_classes(draft) == {DrugClass.SGLT2_INHIBITOR}
    assert classify_drug_classes(dapagliflozin_peer) == {
        DrugClass.SGLT2_INHIBITOR
    }
