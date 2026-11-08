"""Tests for turning comparison results into the /demo PEERS step.

Each compared dimension with any evidence becomes one Decision in the
PEERS step; the draft is always cited from the uploaded protocol.
"""

import dataclasses
from datetime import date

from backend.agents.protocol_comparison.agent import (
    ProtocolComparison,
    review_flags,
)
from backend.agents.protocol_comparison.comparison import DimensionComparison
from backend.agents.protocol_comparison.dimensions import (
    DimensionValue,
    TrialProfile,
)
from backend.agents.protocol_comparison.eligibility import (
    LabReading,
    ReadingStatus,
)
from backend.agents.protocol_comparison.review import (
    FlagReasoning,
    Leaning,
    SuggestionCard,
)
from backend.agents.protocol_comparison.step_data import (
    MIN_PDF_QUOTE_LENGTH,
    quoted_text,
    to_step_data,
)
from backend.api.schemas import (
    EvidenceSource,
    Severity,
    StepData,
    StepId,
    StepStatus,
    TraceKind,
)
from backend.clients.gemini import JsonGenerator, LlmCallFailedError
from backend.shared.messages import (
    Citation,
    CriterionKind,
    EligibilityCriterion,
    PageText,
    ProtocolDocument,
)
from tests.backend.agents.protocol_comparison.profiles import (
    MAXIMUM_AGE,
    MINIMUM_AGE,
    compare,
    draft,
    profile,
    spread_peers,
)
from tests.backend.agents.protocol_comparison.protocols import PEER_SEARCH
from tests.conftest import FakeJsonGenerator

PROTOCOL_ID = "proto-test"
PROTOCOL_DATE = date(2016, 12, 19)
DRAFT_QUOTE = "Participants aged at least 95 years at the screening visit"
REASONING = FlagReasoning(
    summary="Minimum age 95 is stricter than every comparable trial.",
    why_it_matters="Fewer eligible participants.",
    risk_of_changing="None obvious.",
    leaning=Leaning.BRING_IN_LINE,
    cited_trial_ids=["NCT-SPREAD-9"],
)


def document(*page_texts: str) -> ProtocolDocument:
    pages = [
        PageText(page_number=number, text=text)
        for number, text in enumerate(page_texts, start=1)
    ]
    return ProtocolDocument(
        protocol_id=PROTOCOL_ID,
        title="my_trial",
        page_count=len(pages),
        pages=pages,
    )


def lab_reading(status: ReadingStatus) -> LabReading:
    return LabReading(
        trial_id=PROTOCOL_ID, values={}, rejected=(), status=status
    )


def quoted_draft(
    value: float, quote: str, page_number: int | None = None
) -> TrialProfile:
    """A draft whose value's source quotes the eligibility text."""
    base = draft(value)
    return dataclasses.replace(
        base,
        values={
            MINIMUM_AGE.dimension_id: DimensionValue(
                value=value,
                source=f'eligibility text "{quote}"',
                page_number=page_number,
            )
        },
    )


async def step_for(
    *results: DimensionComparison,
    pdf: ProtocolDocument | None = None,
    llm: JsonGenerator | None = None,
    draft_labs: ReadingStatus = ReadingStatus.READ,
) -> StepData:
    cards: tuple[SuggestionCard, ...] = await review_flags(list(results), llm)
    return to_step_data(
        pdf or document("No eligibility text here."),
        ProtocolComparison(
            review_date=PROTOCOL_DATE,
            peer_search=PEER_SEARCH,
            results=results,
            cards=cards,
            draft_lab_reading=lab_reading(draft_labs),
        ),
    )


async def test_every_decision_belongs_to_the_peers_step() -> None:
    step = await step_for(
        compare(draft(95), spread_peers()),
        compare(
            draft(50, MAXIMUM_AGE), spread_peers(MAXIMUM_AGE), MAXIMUM_AGE
        ),
    )

    assert step.id == StepId.PEERS
    assert len(step.decisions) == 2
    assert {decision.step_id for decision in step.decisions} == {StepId.PEERS}


async def test_official_flag_counts_as_outlier_with_a_proposed_change() -> (
    None
):
    step = await step_for(compare(draft(95), spread_peers()))

    decision = step.decisions[0]
    assert decision.severity == Severity.WARNING
    metrics = {metric.label: metric.value for metric in step.metrics}
    assert metrics["Outliers"] == "1"
    assert metrics["Peer trials"] == "11"
    assert decision.proposed_change is not None
    assert decision.proposed_change.before == "95 years"
    assert decision.proposed_change.after == "90 years"
    assert decision.options[-1].title == "Keep the current value"


async def test_in_line_value_is_info_with_no_options() -> None:
    step = await step_for(compare(draft(50), spread_peers()))

    decision = step.decisions[0]
    assert decision.severity == Severity.INFO
    assert decision.options == []
    assert decision.proposed_change is None
    assert step.metrics[2].value == "0"


async def test_draft_quote_in_pdf_is_cited_from_protocol_with_its_page() -> (
    None
):
    pdf = document("Title page.", f"5.1 Inclusion\n{DRAFT_QUOTE}.")
    step = await step_for(
        compare(quoted_draft(95, DRAFT_QUOTE), spread_peers()), pdf=pdf
    )

    draft_evidence = step.decisions[0].evidence[0]
    assert draft_evidence.source == EvidenceSource.PROTOCOL
    assert draft_evidence.page == 2
    assert draft_evidence.quote == DRAFT_QUOTE
    assert draft_evidence.quote in pdf.pages[1].text
    assert step.decisions[0].location is not None
    assert step.decisions[0].location.start_page == 2
    assert step.warnings == []


async def test_draft_value_with_a_parser_citation_uses_its_page() -> None:
    step = await step_for(
        compare(quoted_draft(95, "aged 95", page_number=7), spread_peers())
    )

    draft_evidence = step.decisions[0].evidence[0]
    assert draft_evidence.source == EvidenceSource.PROTOCOL
    assert draft_evidence.page == 7
    assert draft_evidence.is_verified
    assert step.warnings == []


async def test_draft_quote_only_in_a_parsed_criterion_takes_its_page() -> None:
    # PDF text can split a criterion over lines the parser joined.
    pdf = document("Title page.", "Criteria are listed on page 3.")
    pdf.eligibility_criteria = [
        EligibilityCriterion(
            criterion_id="IN-01",
            kind=CriterionKind.INCLUSION,
            text=f"{DRAFT_QUOTE}.",
            citation=Citation(page_number=3, quote=DRAFT_QUOTE),
        )
    ]
    step = await step_for(
        compare(quoted_draft(95, DRAFT_QUOTE), spread_peers()), pdf=pdf
    )

    assert step.decisions[0].evidence[0].page == 3


async def test_short_lab_quote_takes_its_criterions_page() -> None:
    # Found live: "HbA1c of ≥6.5% to ≤11.0%" is under the PDF-search
    # minimum but was read from a parsed criterion, so it has a page.
    short_quote = "HbA1c of ≥6.5% to ≤11.0%"
    assert len(short_quote) < MIN_PDF_QUOTE_LENGTH
    pdf = document("Title page.")
    pdf.eligibility_criteria = [
        EligibilityCriterion(
            criterion_id="IN-02",
            kind=CriterionKind.INCLUSION,
            text=f"{short_quote} at screening",
            citation=Citation(page_number=47, quote=short_quote),
        )
    ]
    step = await step_for(
        compare(quoted_draft(11, short_quote), spread_peers()), pdf=pdf
    )

    assert step.decisions[0].evidence[0].page == 47
    assert step.warnings == []


async def test_unplaced_draft_quote_is_still_cited_from_the_protocol() -> None:
    step = await step_for(
        compare(quoted_draft(95, DRAFT_QUOTE), spread_peers())
    )

    draft_evidence = step.decisions[0].evidence[0]
    assert draft_evidence.source == EvidenceSource.PROTOCOL
    assert draft_evidence.document == "my_trial"
    assert draft_evidence.page is None
    assert not draft_evidence.is_verified
    assert step.decisions[0].location is None
    assert [warning.code for warning in step.warnings] == [
        "DRAFT_VALUE_WITHOUT_PAGE"
    ]


async def test_short_draft_quote_is_not_matched_in_the_pdf() -> None:
    short_quote = "10 Years"
    assert len(short_quote) < MIN_PDF_QUOTE_LENGTH
    pdf = document("Follow-up lasts 10 years after randomisation.")
    step = await step_for(
        compare(quoted_draft(10, short_quote), spread_peers()), pdf=pdf
    )

    assert step.decisions[0].evidence[0].page is None


async def test_unread_draft_labs_make_the_step_partial_with_a_warning() -> (
    None
):
    step = await step_for(
        compare(draft(50), spread_peers()), draft_labs=ReadingStatus.FAILED
    )

    assert step.status == StepStatus.PARTIAL
    assert "DRAFT_LABS_FAILED" in {warning.code for warning in step.warnings}


async def test_protocol_without_criteria_warns_but_stays_complete() -> None:
    step = await step_for(
        compare(draft(50), spread_peers()), draft_labs=ReadingStatus.NO_TEXT
    )

    assert step.status == StepStatus.COMPLETED
    assert "DRAFT_LABS_NO_TEXT" in {warning.code for warning in step.warnings}


async def test_peer_evidence_cites_each_stating_peer_from_aact() -> None:
    step = await step_for(compare(draft(95), spread_peers()))

    peer_evidence = step.decisions[0].evidence[1:]
    assert len(peer_evidence) == 11
    assert {evidence.source for evidence in peer_evidence} == {
        EvidenceSource.AACT
    }
    assert peer_evidence[0].document == "NCT-SPREAD-0"


async def test_trace_cites_only_evidence_on_the_decision() -> None:
    step = await step_for(compare(draft(95), spread_peers()))

    decision = step.decisions[0]
    evidence_ids = {evidence.evidence_id for evidence in decision.evidence}
    cited = {
        evidence_id
        for entry in decision.trace
        for evidence_id in entry.evidence_ids
    }
    assert cited <= evidence_ids
    kinds = [entry.kind for entry in decision.trace]
    assert TraceKind.COMPARE in kinds
    assert kinds[-1] == TraceKind.CONCLUDE


async def test_dimension_nobody_states_has_no_decision_but_is_tabled() -> None:
    nobody = [profile(f"NCT-EMPTY-{index}", None) for index in range(3)]
    step = await step_for(compare(draft(None), nobody))

    assert step.decisions == []
    assert step.tables[0].rows[0]["finding"] == "NOT_STATED"


async def test_reasoning_leaning_marks_the_recommended_option() -> None:
    step = await step_for(
        compare(draft(95), spread_peers()),
        llm=FakeJsonGenerator([REASONING]),
    )

    decision = step.decisions[0]
    assert decision.claim == REASONING.summary
    assert decision.options[0].is_recommended
    assert not decision.options[-1].is_recommended
    assert step.status == StepStatus.COMPLETED


async def test_failed_reasoning_makes_the_step_partial_with_a_warning() -> (
    None
):
    step = await step_for(
        compare(draft(95), spread_peers()),
        llm=FakeJsonGenerator([LlmCallFailedError("timed out")]),
    )

    assert step.status == StepStatus.PARTIAL
    assert "REASONING_FAILED" in {warning.code for warning in step.warnings}


async def test_step_shows_at_most_four_metrics() -> None:
    # The /demo page keeps a step's overview to four figures.
    step = await step_for(compare(draft(95), spread_peers()))

    assert len(step.metrics) <= 4


def test_quoted_text_takes_the_quote_or_the_whole_source() -> None:
    assert quoted_text('registry minimumAge "10 Years"') == "10 Years"
    assert quoted_text("test value 95") == "test value 95"


async def test_step_names_the_search_built_from_the_protocol() -> None:
    step = await step_for(compare(draft(50), spread_peers()))

    [source] = step.data_sources
    assert source.description is not None
    assert "phase 3, pediatric trials started since 2016-01-01" in (
        source.description
    )
    peer_search = step.details["peer_search"]
    assert isinstance(peer_search, dict)
    assert peer_search["excluded_nct_ids"] == ["NCT03170518"]


async def test_dimension_table_rounds_peer_percentiles() -> None:
    # Peers at 0, 1/3, ..., 10/3: the 10th percentile is 1/3.
    peers = [profile(f"NCT-THIRD-{index}", index / 3) for index in range(11)]
    step = await step_for(compare(draft(1), peers))

    row = step.tables[0].rows[0]
    assert row["peer_p10"] == 0.33
    assert row["peer_p90"] == 3.0
