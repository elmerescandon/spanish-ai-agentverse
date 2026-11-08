"""Tests for comparing a parsed protocol (the draft) with registry peers.

The draft's values come from the ProtocolDocument the parser built;
peers keep their ClinicalTrials.gov values.
"""

from pathlib import Path

from backend.agents.protocol_comparison.agent import (
    SessionLabReadingCache,
    compare_protocol_draft,
)
from backend.agents.protocol_comparison.comparison import DimensionComparison
from backend.agents.protocol_comparison.dimensions import (
    DimensionId,
    profile_protocol_document,
)
from backend.agents.protocol_comparison.eligibility import (
    ReadingStatus,
    protocol_eligibility_text,
)
from backend.agents.protocol_comparison.peer_store import PeerStore
from backend.agents.protocol_comparison.rules import DrugClass
from backend.clients.gemini import LlmCallFailedError
from backend.shared.messages import (
    CriterionKind,
    ProtocolDocument,
    StatisticalAssumptions,
)
from tests.backend.agents.protocol_comparison.builders import make_study
from tests.backend.agents.protocol_comparison.protocols import (
    ALT_CRITERION,
    DRAFT_NCT_ID,
    HBA1C_CRITERION,
    HBA1C_REPLY,
    PEER_SEARCH,
    PROTOCOL_ID,
    REVIEW_DATE,
    cited,
    criterion,
    parsed_protocol,
)
from tests.conftest import FakeJsonGenerator


def by_dimension(
    results: tuple[DimensionComparison, ...],
) -> dict[DimensionId, DimensionComparison]:
    return {result.dimension.dimension_id: result for result in results}


def test_profile_reads_ages_and_enrollment_with_their_pages() -> None:
    values = profile_protocol_document(parsed_protocol()).values

    assert values[DimensionId.MINIMUM_AGE].value == 10.0
    assert values[DimensionId.MAXIMUM_AGE].value == 17.0
    assert values[DimensionId.MINIMUM_AGE].page_number == 11
    assert values[DimensionId.ENROLLMENT].value == 150.0
    assert '"approximately 150 participants"' in (
        values[DimensionId.ENROLLMENT].source
    )


def test_profile_takes_drugs_from_arms_ignoring_placebo() -> None:
    profile = profile_protocol_document(parsed_protocol())

    assert profile.trial_id == PROTOCOL_ID
    assert profile.drugs == frozenset({"canagliflozin"})
    assert profile.drug_classes == frozenset({DrugClass.SGLT2_INHIBITOR})


def test_profile_falls_back_to_sample_size_for_enrollment() -> None:
    document = parsed_protocol()
    assert document.design is not None
    document.design.target_enrollment = None
    document.statistics = StatisticalAssumptions(
        sample_size=cited(132, "132 participants are needed", 40)
    )

    enrollment = profile_protocol_document(document).values[
        DimensionId.ENROLLMENT
    ]

    assert enrollment.value == 132.0
    assert enrollment.page_number == 40


def test_unparsed_protocol_states_no_values() -> None:
    document = ProtocolDocument(
        protocol_id=PROTOCOL_ID, title="empty", page_count=0, pages=[]
    )

    profile = profile_protocol_document(document)

    assert profile.values == {}
    assert profile.drugs == frozenset()


def test_eligibility_text_lists_inclusion_before_exclusion() -> None:
    text = protocol_eligibility_text(
        [
            criterion("EX-01", CriterionKind.EXCLUSION, ALT_CRITERION),
            criterion("IN-01", CriterionKind.INCLUSION, HBA1C_CRITERION),
        ]
    )

    assert text == (
        f"Inclusion Criteria:\n- {HBA1C_CRITERION}\n\n"
        f"Exclusion Criteria:\n- {ALT_CRITERION}"
    )


def test_eligibility_text_is_none_without_criteria() -> None:
    assert protocol_eligibility_text([]) is None


async def test_draft_values_come_from_the_parsed_protocol(
    tmp_path: Path,
) -> None:
    # The registry record says 12 to 25; the parsed protocol must win.
    registry_draft = make_study(
        nct_id=DRAFT_NCT_ID, minimum_age="12 Years", maximum_age="25 Years"
    )
    peer = make_study(nct_id="NCT00000001", minimum_age="18 Years")
    document = parsed_protocol(
        [criterion("IN-01", CriterionKind.INCLUSION, HBA1C_CRITERION)]
    )
    llm = FakeJsonGenerator([HBA1C_REPLY])

    comparison = await compare_protocol_draft(
        document,
        REVIEW_DATE,
        PEER_SEARCH,
        [registry_draft, peer],
        SessionLabReadingCache(PeerStore(tmp_path)),
        llm,
    )

    results = by_dimension(comparison.results)
    minimum_age = results[DimensionId.MINIMUM_AGE].draft_value
    hba1c = results[DimensionId.HBA1C_UPPER_BOUND].draft_value
    assert minimum_age is not None and minimum_age.value == 10.0
    assert hba1c is not None and hba1c.value == 10.5
    assert HBA1C_CRITERION in llm.prompts[0]
    assert comparison.draft_lab_reading.status == ReadingStatus.READ


async def test_protocols_own_registry_record_is_not_its_own_peer(
    tmp_path: Path,
) -> None:
    peers = [make_study(nct_id=DRAFT_NCT_ID), make_study(nct_id="NCT00000001")]

    comparison = await compare_protocol_draft(
        parsed_protocol(),
        REVIEW_DATE,
        PEER_SEARCH,
        peers,
        PeerStore(tmp_path),
        lab_llm=None,
    )

    peer_ids = {
        evidence.trial_id for evidence in comparison.results[0].evidence
    }
    assert peer_ids == {"NCT00000001"}


async def test_draft_reading_is_reused_without_touching_disk(
    tmp_path: Path,
) -> None:
    cache = SessionLabReadingCache(PeerStore(tmp_path))
    document = parsed_protocol(
        [criterion("IN-01", CriterionKind.INCLUSION, HBA1C_CRITERION)]
    )
    first_llm = FakeJsonGenerator([HBA1C_REPLY])

    await compare_protocol_draft(
        document, REVIEW_DATE, PEER_SEARCH, [], cache, first_llm
    )
    second = await compare_protocol_draft(
        document, REVIEW_DATE, PEER_SEARCH, [], cache, FakeJsonGenerator([])
    )

    assert len(first_llm.prompts) == 1
    assert second.draft_lab_reading.status == ReadingStatus.READ
    assert list(tmp_path.iterdir()) == []


async def test_failed_draft_reading_leaves_lab_limits_out(
    tmp_path: Path,
) -> None:
    document = parsed_protocol(
        [criterion("IN-01", CriterionKind.INCLUSION, HBA1C_CRITERION)]
    )
    llm = FakeJsonGenerator([LlmCallFailedError("timed out")])

    comparison = await compare_protocol_draft(
        document, REVIEW_DATE, PEER_SEARCH, [], PeerStore(tmp_path), llm
    )

    results = by_dimension(comparison.results)
    assert comparison.draft_lab_reading.status == ReadingStatus.FAILED
    assert results[DimensionId.HBA1C_UPPER_BOUND].draft_value is None
    assert results[DimensionId.MINIMUM_AGE].draft_value is not None


async def test_protocol_without_criteria_makes_no_llm_call(
    tmp_path: Path,
) -> None:
    llm = FakeJsonGenerator([])

    comparison = await compare_protocol_draft(
        parsed_protocol(),
        REVIEW_DATE,
        PEER_SEARCH,
        [],
        PeerStore(tmp_path),
        llm,
    )

    assert llm.prompts == []
    assert comparison.draft_lab_reading.status == ReadingStatus.NO_TEXT
