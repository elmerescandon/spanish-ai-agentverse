"""Scripted parser facet answers and synthetic PDF helper for tests."""

from pathlib import Path

from pydantic import BaseModel

from backend.agents.parser.facets import FACETS
from backend.shared.messages import (
    AnalysisPlanExtraction,
    Citation,
    CitedValue,
    CriterionKind,
    EligibilityCriterion,
    EligibilityExtraction,
    Endpoint,
    EndpointKind,
    EndpointList,
    EstimandExtraction,
    FacetName,
    InterventionArm,
    InterventionExtraction,
    InterventionType,
    M11Heading,
    ProtocolSection,
    SafetyMonitoringExtraction,
    ScheduledVisit,
    ScheduleOfActivities,
    SectionMap,
    StatisticalAssumptions,
    SynopsisConsistencyExtraction,
    TrialDesignFacts,
)
from tests.conftest import make_pdf

PDF_PAGE_ONE = (
    "1 PROTOCOL SUMMARY\n"
    "Official Title: Food As Medicine for Diabetes Study Protocol.\n"
    "National Clinical Trial Identified Number: NCT 04828785.\n"
    "We will enroll N=200 participants into 2 arms in this clinical trial."
)
PDF_PAGE_TWO = (
    "5 TARGET POPULATION AND STUDY SAMPLE\n"
    "Inclusion Criteria: Participants must have HbA1c >= 8.0% at screening.\n"
    "Primary Outcome: Change in Hemoglobin A1c at 6 months after baseline."
)
PDF_TITLE_QUOTE = "Official Title: Food As Medicine for Diabetes"
PDF_NCT_QUOTE = "National Clinical Trial Identified Number: NCT 04828785"
PDF_SAMPLE_SIZE_QUOTE = (
    "We will enroll N=200 participants into 2 arms in this clinical trial"
)
PDF_CRITERION_QUOTE = "Participants must have HbA1c >= 8.0% at screening"
PDF_SECTION_QUOTE = "1 PROTOCOL SUMMARY Official Title: Food As Medicine"
PDF_ENDPOINT_QUOTE = "Primary Outcome: Change in Hemoglobin A1c at 6 months"


def scripted_facet_responses() -> list[BaseModel | Exception]:
    """Return one valid scripted response per parser facet, in FACETS order."""
    by_facet: dict[FacetName, BaseModel] = {
        FacetName.ELIGIBILITY: EligibilityExtraction(
            criteria=[
                EligibilityCriterion(
                    criterion_id="raw-1",
                    kind=CriterionKind.INCLUSION,
                    text="HbA1c >= 8.0% at screening",
                    citation=Citation(
                        page_number=2, quote=PDF_CRITERION_QUOTE
                    ),
                )
            ]
        ),
        FacetName.DESIGN: TrialDesignFacts(
            official_title=CitedValue[str](
                value="Food As Medicine for Diabetes Study Protocol",
                citation=Citation(page_number=1, quote=PDF_TITLE_QUOTE),
            ),
            nct_id=CitedValue[str](
                value="NCT 04828785",
                citation=Citation(page_number=1, quote=PDF_NCT_QUOTE),
            ),
        ),
        FacetName.SECTIONS: SectionMap(
            sections=[
                ProtocolSection(
                    heading=M11Heading.PROTOCOL_SUMMARY,
                    title="1 PROTOCOL SUMMARY",
                    start_page=1,
                    end_page=1,
                    summary="Summarizes the FAME-D trial.",
                    citation=Citation(page_number=1, quote=PDF_SECTION_QUOTE),
                )
            ]
        ),
        FacetName.ENDPOINTS: EndpointList(
            endpoints=[
                Endpoint(
                    kind=EndpointKind.PRIMARY,
                    description="Change in Hemoglobin A1c",
                    time_frame="6 months",
                    citation=Citation(page_number=2, quote=PDF_ENDPOINT_QUOTE),
                )
            ]
        ),
        FacetName.SCHEDULE: ScheduleOfActivities(
            visits=[
                ScheduledVisit(
                    visit_name="6-month assessment",
                    study_day=180,
                    procedures=["Hemoglobin A1c blood draw"],
                    citation=Citation(page_number=2, quote=PDF_ENDPOINT_QUOTE),
                )
            ]
        ),
        FacetName.STATISTICS: StatisticalAssumptions(
            sample_size=CitedValue[int](
                value=200,
                citation=Citation(page_number=1, quote=PDF_SAMPLE_SIZE_QUOTE),
            )
        ),
        FacetName.ESTIMANDS: EstimandExtraction(),
        FacetName.INTERVENTIONS: InterventionExtraction(
            arms=[
                InterventionArm(
                    name="Food As Medicine",
                    intervention_type=InterventionType.BEHAVIORAL,
                    citation=Citation(page_number=1, quote=PDF_TITLE_QUOTE),
                )
            ]
        ),
        FacetName.ANALYSIS: AnalysisPlanExtraction(),
        FacetName.SYNOPSIS_CHECK: SynopsisConsistencyExtraction(),
        FacetName.SAFETY_MONITORING: SafetyMonitoringExtraction(),
    }
    return [by_facet[facet.name] for facet in FACETS]


def demo_pdf(tmp_path: Path, name: str = "protocol.pdf") -> Path:
    """Write the two-page synthetic FAME-D PDF into tmp_path / name."""
    pdf_path = make_pdf(tmp_path, [PDF_PAGE_ONE, PDF_PAGE_TWO])
    return pdf_path.rename(tmp_path / name)
