"""Tests for turning CohortComparisonReport into the /demo COHORT StepData."""

from pathlib import Path

from backend.agents.cohort.agent import (
    AGENT_NAME,
    analyze_protocol_document_cohort,
    extract_criteria_from_pages,
)
from backend.agents.cohort.models import (
    CohortComparisonReport,
    CriterionType,
    ProtocolCriterionInput,
)
from backend.agents.cohort.step_data import (
    find_quote_page,
    to_step_data,
)
from backend.api.schemas import (
    ChartKind,
    EvidenceSource,
    Severity,
    StepId,
    StepStatus,
    TraceKind,
)
from backend.clients.pdf_reader import read_pdf_pages
from backend.shared.messages import (
    Citation,
    CriterionKind,
    EligibilityCriterion,
    M11Heading,
    PageText,
    ProtocolDocument,
)

SAMPLE_PDF_PATH = Path("data/protocols/sample/SYN-T2D-301_protocol.pdf")
BMI_CRITERION_QUOTE = "Body Mass Index (BMI) <= 30.0 kg/m2 at baseline visit"
EGFR_CRITERION_QUOTE = (
    "Impaired renal function defined as eGFR < 75 mL/min/1.73m2"
)


def _make_document(
    *page_texts: str,
    criteria: list[EligibilityCriterion] | None = None,
) -> ProtocolDocument:
    pages = [
        PageText(page_number=idx, text=text)
        for idx, text in enumerate(page_texts, start=1)
    ]
    return ProtocolDocument(
        protocol_id="proto-cohort-test",
        title="SYN-T2D-301",
        page_count=len(pages),
        pages=pages,
        eligibility_criteria=criteria or [],
    )


async def test_every_decision_belongs_to_the_cohort_step() -> None:
    doc = _make_document(
        "Title page.",
        f"5.1 Inclusion Criteria\n1. {BMI_CRITERION_QUOTE}.\n"
        f"5.2 Exclusion Criteria\n1. {EGFR_CRITERION_QUOTE}.",
    )
    report = await analyze_protocol_document_cohort(doc)
    step = to_step_data(report, doc)

    assert step.id == StepId.COHORT
    assert step.agent == AGENT_NAME
    assert len(step.decisions) >= 2
    assert {d.step_id for d in step.decisions} == {StepId.COHORT}
    assert len(step.metrics) <= 4


async def test_decision_has_protocol_and_nhanes_evidence_and_valid_trace() -> (
    None
):
    doc = _make_document(
        "Title page.",
        f"5.1 Inclusion Criteria\n1. {BMI_CRITERION_QUOTE}.",
    )
    report = await analyze_protocol_document_cohort(doc)
    step = to_step_data(report, doc)

    decision = step.decisions[0]
    sources = [ev.source for ev in decision.evidence]
    assert EvidenceSource.PROTOCOL in sources
    assert EvidenceSource.NHANES in sources

    protocol_ev = next(
        ev for ev in decision.evidence if ev.source == EvidenceSource.PROTOCOL
    )
    assert protocol_ev.is_verified is True
    assert protocol_ev.page == 2
    assert BMI_CRITERION_QUOTE in protocol_ev.quote

    assert decision.location is not None
    assert decision.location.section_heading == M11Heading.TRIAL_POPULATION
    assert decision.location.start_page == 2
    assert decision.location.criterion_id == "IN-01"

    evidence_ids = {ev.evidence_id for ev in decision.evidence}
    cited_ids = {
        ev_id for entry in decision.trace for ev_id in entry.evidence_ids
    }
    assert cited_ids <= evidence_ids
    trace_kinds = [entry.kind for entry in decision.trace]
    assert trace_kinds == [
        TraceKind.RULE,
        TraceKind.COMPARE,
        TraceKind.CONCLUDE,
    ]


async def test_decision_proposed_change_and_recommended_option() -> None:
    doc = _make_document(
        f"5.2 Exclusion Criteria\n1. {EGFR_CRITERION_QUOTE}.",
    )
    report = await analyze_protocol_document_cohort(doc)
    step = to_step_data(report, doc)

    decision = step.decisions[0]
    assert decision.severity in {Severity.WARNING, Severity.CRITICAL}
    assert decision.proposed_change is not None
    assert EGFR_CRITERION_QUOTE in decision.proposed_change.before
    assert "eGFR" in decision.proposed_change.after
    assert decision.confidence is not None
    assert decision.references
    assert decision.impact

    assert len(decision.options) == 2
    recommended = [opt for opt in decision.options if opt.is_recommended]
    assert len(recommended) == 1
    assert recommended[0].impact


async def test_step_includes_data_sources_tables_and_charts() -> None:
    doc = _make_document(
        f"5.1 Inclusion Criteria\n1. {BMI_CRITERION_QUOTE}.",
    )
    report = await analyze_protocol_document_cohort(doc)
    step = to_step_data(report, doc)

    assert [ds.source for ds in step.data_sources] == [
        EvidenceSource.NHANES,
        EvidenceSource.AACT,
    ]
    assert step.data_sources[0].record_count == report.base_population_count

    table_ids = {t.table_id for t in step.tables}
    assert {
        "cohort-attrition-funnel",
        "cohort-peer-benchmarks",
        "cohort-subgroups",
    } <= table_ids

    chart_kinds = {c.kind for c in step.charts}
    assert {ChartKind.WATERFALL, ChartKind.COMPARISON} <= chart_kinds


async def test_unsimulatable_criterion_marks_step_partial_with_warning() -> (
    None
):
    criteria = [
        EligibilityCriterion(
            criterion_id="EX-99",
            kind=CriterionKind.EXCLUSION,
            text="Left ventricular ejection fraction < 35% by cardiac MRI",
            citation=Citation(
                page_number=1,
                quote=(
                    "Left ventricular ejection fraction < 35% by cardiac MRI"
                ),
                is_verified=True,
            ),
        ),
        EligibilityCriterion(
            criterion_id="EX-01",
            kind=CriterionKind.EXCLUSION,
            text=EGFR_CRITERION_QUOTE,
            citation=Citation(
                page_number=1,
                quote=EGFR_CRITERION_QUOTE,
                is_verified=True,
            ),
        ),
    ]
    doc = _make_document(
        f"Left ventricular ejection fraction < 35% by cardiac MRI. "
        f"{EGFR_CRITERION_QUOTE}.",
        criteria=criteria,
    )
    report: CohortComparisonReport = await analyze_protocol_document_cohort(
        doc
    )
    step = to_step_data(report, doc)

    assert step.status == StepStatus.PARTIAL
    warning_codes = {w.code for w in step.warnings}
    assert "CRITERIA_NOT_SIMULABLE" in warning_codes


def test_extract_criteria_from_sample_protocol_pdf() -> None:
    pages = read_pdf_pages(SAMPLE_PDF_PATH)
    doc = ProtocolDocument(
        protocol_id="proto-sample",
        title="SYN-T2D-301",
        page_count=len(pages),
        pages=pages,
    )
    criteria: list[ProtocolCriterionInput] = extract_criteria_from_pages(doc)
    assert len(criteria) == 25
    inclusions = [c for c in criteria if c.kind == CriterionType.INCLUSION]
    exclusions = [c for c in criteria if c.kind == CriterionType.EXCLUSION]
    assert len(inclusions) == 10
    assert len(exclusions) == 15
    for item in criteria:
        assert item.quote is not None
        assert find_quote_page(doc, item.quote) == item.page_number
