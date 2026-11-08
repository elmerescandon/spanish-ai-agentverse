"""Tests for the ClinicalTrials.gov API v2 client."""

import asyncio
import json
from collections.abc import Callable, Coroutine
from datetime import date
from pathlib import Path

import httpx
import pytest

from backend.clients.clinicaltrials_gov import (
    MAX_RETRIES,
    MIN_SECONDS_BETWEEN_REQUESTS,
    REQUESTED_SECTIONS,
    RETRY_BASE_DELAY_SECONDS,
    AgeGroup,
    ClinicalTrialsGovClient,
    ClinicalTrialsGovError,
    Masking,
    OverallStatus,
    PeerSearchQuery,
    Phase,
    Population,
    StudyNotFoundError,
    build_search_params,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "clinicaltrials_gov"
DEMO_NCT_ID = "NCT03170518"

type Handler = Callable[[httpx.Request], httpx.Response]


def load_fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def minimal_study(nct_id: str) -> dict[str, object]:
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": nct_id,
                "briefTitle": f"Study {nct_id}",
            },
            "statusModule": {"overallStatus": "COMPLETED"},
        }
    }


class FakeTime:
    """Fake clock and sleep, so tests never wait and can inspect delays."""

    def __init__(self, seconds_per_tick: float) -> None:
        self.now = 0.0
        self.seconds_per_tick = seconds_per_tick
        self.sleeps: list[float] = []

    def clock(self) -> float:
        self.now += self.seconds_per_tick
        return self.now

    async def sleep(self, delay_seconds: float) -> None:
        self.sleeps.append(delay_seconds)


def run[ResultT](
    handler: Handler,
    action: Callable[
        [ClinicalTrialsGovClient], Coroutine[object, object, ResultT]
    ],
    fake_time: FakeTime | None = None,
) -> ResultT:
    """Run action against a client whose HTTP calls go to handler."""
    # A clock that jumps 10s per call keeps throttling out of the way.
    time_source = fake_time or FakeTime(seconds_per_tick=10.0)

    async def run_with_client() -> ResultT:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with ClinicalTrialsGovClient(
            http_client=http_client,
            sleep=time_source.sleep,
            clock=time_source.clock,
        ) as client:
            return await action(client)

    return asyncio.run(run_with_client())


def pediatric_query(**overrides: object) -> PeerSearchQuery:
    fields: dict[str, object] = {
        "condition": "Diabetes Mellitus, Type 2",
        "phases": (Phase.PHASE3,),
        "population": Population.PEDIATRIC,
        "started_on_or_after": date(2010, 1, 1),
        "started_before": date(2017, 7, 21),
    }
    fields.update(overrides)
    return PeerSearchQuery(**fields)  # type: ignore[arg-type]


def test_fetch_study_parses_real_registry_record() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=load_fixture("NCT03170518.json"))

    study = run(handler, lambda client: client.fetch_study(DEMO_NCT_ID))

    protocol = study.protocol_section
    assert study.nct_id == DEMO_NCT_ID
    assert study.url == "https://clinicaltrials.gov/study/NCT03170518"
    assert protocol.status_module.overall_status is OverallStatus.COMPLETED
    assert protocol.status_module.start_date_struct is not None
    assert protocol.status_module.start_date_struct.date == "2017-07-21"
    assert study.last_updated == "2025-04-25"
    assert protocol.design_module is not None
    assert protocol.design_module.phases == [Phase.PHASE3]
    assert protocol.design_module.design_info is not None
    masking_info = protocol.design_module.design_info.masking_info
    assert masking_info is not None
    assert masking_info.masking is Masking.DOUBLE
    eligibility = protocol.eligibility_module
    assert eligibility is not None
    assert eligibility.std_ages == [AgeGroup.CHILD]
    assert eligibility.minimum_age == "10 Years"
    assert eligibility.eligibility_criteria is not None
    assert "HbA1c" in eligibility.eligibility_criteria
    assert protocol.oversight_module is not None
    assert protocol.oversight_module.oversight_has_dmc is True
    assert protocol.contacts_locations_module is not None
    assert len(protocol.contacts_locations_module.locations) == 106
    assert study.document_section is not None
    filenames = [
        document.filename
        for document in study.document_section.large_document_module.large_docs
    ]
    assert "Prot_002.pdf" in filenames


def test_fetch_study_requests_only_the_sections_we_use() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=minimal_study(DEMO_NCT_ID))

    run(handler, lambda client: client.fetch_study(DEMO_NCT_ID))

    assert len(seen) == 1
    assert seen[0].url.path == f"/api/v2/studies/{DEMO_NCT_ID}"
    assert seen[0].url.params["fields"] == REQUESTED_SECTIONS


def test_fetch_study_rejects_malformed_nct_id_without_calling_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected for a malformed NCT ID")

    with pytest.raises(ValueError, match="expected an NCT ID"):
        run(handler, lambda client: client.fetch_study("NCT123"))


def test_fetch_study_raises_not_found_without_retrying() -> None:
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(404, text="not found")

    with pytest.raises(StudyNotFoundError, match="NCT00000000"):
        run(handler, lambda client: client.fetch_study("NCT00000000"))
    assert len(attempts) == 1


def test_fetch_study_retries_rate_limit_and_server_error_then_succeeds() -> (
    None
):
    responses = iter(
        [
            httpx.Response(429, text="slow down"),
            httpx.Response(503, text="unavailable"),
            httpx.Response(200, json=minimal_study(DEMO_NCT_ID)),
        ]
    )
    fake_time = FakeTime(seconds_per_tick=10.0)

    study = run(
        lambda request: next(responses),
        lambda client: client.fetch_study(DEMO_NCT_ID),
        fake_time,
    )

    assert study.nct_id == DEMO_NCT_ID
    assert fake_time.sleeps == [
        RETRY_BASE_DELAY_SECONDS,
        RETRY_BASE_DELAY_SECONDS * 2,
    ]


def test_fetch_study_retries_after_timeout() -> None:
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json=minimal_study(DEMO_NCT_ID))

    study = run(handler, lambda client: client.fetch_study(DEMO_NCT_ID))

    assert study.nct_id == DEMO_NCT_ID
    assert len(attempts) == 2


def test_fetch_study_gives_up_after_max_retries() -> None:
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(500, text="boom")

    with pytest.raises(ClinicalTrialsGovError, match="after 3 attempts"):
        run(handler, lambda client: client.fetch_study(DEMO_NCT_ID))
    assert len(attempts) == MAX_RETRIES


def test_fetch_study_fails_fast_on_client_error() -> None:
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(400, text="bad fields")

    with pytest.raises(ClinicalTrialsGovError, match="status 400"):
        run(handler, lambda client: client.fetch_study(DEMO_NCT_ID))
    assert len(attempts) == 1


def test_fetch_study_rejects_payload_missing_required_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"protocolSection": {}})

    with pytest.raises(ClinicalTrialsGovError, match="unexpected payload"):
        run(handler, lambda client: client.fetch_study(DEMO_NCT_ID))


def test_fetch_study_rejects_non_json_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with pytest.raises(ClinicalTrialsGovError, match="unexpected payload"):
        run(handler, lambda client: client.fetch_study(DEMO_NCT_ID))


def test_consecutive_requests_are_spaced_by_the_rate_limit() -> None:
    # A frozen clock means no time passes between the two requests.
    fake_time = FakeTime(seconds_per_tick=0.0)

    async def fetch_twice(client: ClinicalTrialsGovClient) -> None:
        await client.fetch_study(DEMO_NCT_ID)
        await client.fetch_study(DEMO_NCT_ID)

    run(
        lambda request: httpx.Response(200, json=minimal_study(DEMO_NCT_ID)),
        fetch_twice,
        fake_time,
    )

    assert fake_time.sleeps == [MIN_SECONDS_BETWEEN_REQUESTS]


def test_search_params_for_pediatric_phase3_trials_before_draft_start() -> (
    None
):
    params = build_search_params(pediatric_query(), page_token=None)

    assert params == {
        "query.cond": "Diabetes Mellitus, Type 2",
        "filter.advanced": (
            "AREA[StudyType]INTERVENTIONAL"
            " AND (AREA[Phase]PHASE3)"
            " AND AREA[StdAge]CHILD AND NOT AREA[StdAge]OLDER_ADULT"
            " AND AREA[StartDate]RANGE[2010-01-01,2017-07-20]"
        ),
        "fields": REQUESTED_SECTIONS,
        "pageSize": "100",
        "countTotal": "true",
    }


def test_search_params_for_adults_with_intervention_and_open_end_date() -> (
    None
):
    query = pediatric_query(
        phases=(Phase.PHASE2, Phase.PHASE3),
        population=Population.ADULT,
        started_before=None,
        intervention="SGLT2 inhibitor",
    )

    params = build_search_params(query, page_token="next-page")

    assert params["query.intr"] == "SGLT2 inhibitor"
    assert params["pageToken"] == "next-page"
    assert params["filter.advanced"] == (
        "AREA[StudyType]INTERVENTIONAL"
        " AND (AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)"
        " AND AREA[StdAge]ADULT AND NOT AREA[StdAge]CHILD"
        " AND AREA[StartDate]RANGE[2010-01-01,MAX]"
    )


def test_peer_search_query_requires_at_least_one_phase() -> None:
    with pytest.raises(ValueError, match="at least one phase"):
        pediatric_query(phases=())


def test_peer_search_query_rejects_empty_date_window() -> None:
    with pytest.raises(ValueError, match="started_before"):
        pediatric_query(
            started_on_or_after=date(2017, 7, 21),
            started_before=date(2017, 7, 21),
        )


def test_search_studies_follows_pages_and_excludes_the_draft() -> None:
    seen: list[httpx.Request] = []
    pages = {
        None: {
            "totalCount": 3,
            "studies": [
                minimal_study("NCT00000001"),
                minimal_study(DEMO_NCT_ID),
            ],
            "nextPageToken": "page-2",
        },
        "page-2": {"totalCount": 3, "studies": [minimal_study("NCT00000002")]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, content=json.dumps(pages[request.url.params.get("pageToken")])
        )

    studies = run(
        handler,
        lambda client: client.search_studies(
            pediatric_query(exclude_nct_ids=frozenset({DEMO_NCT_ID}))
        ),
    )

    assert [study.nct_id for study in studies] == [
        "NCT00000001",
        "NCT00000002",
    ]
    assert len(seen) == 2


def test_search_studies_stops_once_max_studies_reached() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "studies": [
                    minimal_study("NCT00000001"),
                    minimal_study("NCT00000002"),
                ],
                "nextPageToken": "more",
            },
        )

    studies = run(
        handler,
        lambda client: client.search_studies(pediatric_query(), max_studies=1),
    )

    assert [study.nct_id for study in studies] == ["NCT00000001"]
    assert len(seen) == 1


def test_search_studies_returns_empty_list_when_nothing_matches() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"totalCount": 0, "studies": []})

    studies = run(
        handler, lambda client: client.search_studies(pediatric_query())
    )

    assert studies == []


@pytest.mark.live
def test_live_pediatric_t2dm_search_finds_enough_peers() -> None:
    async def search() -> list[str]:
        async with ClinicalTrialsGovClient() as client:
            studies = await client.search_studies(
                pediatric_query(exclude_nct_ids=frozenset({DEMO_NCT_ID}))
            )
        return [study.nct_id for study in studies]

    nct_ids = asyncio.run(search())

    assert len(nct_ids) >= 10
    assert DEMO_NCT_ID not in nct_ids
