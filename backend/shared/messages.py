"""Shared contract: the typed models every part of the backend exchanges."""

from enum import StrEnum

from pydantic import BaseModel, Field


class FacetName(StrEnum):
    """Protocol extraction facets."""

    DESIGN = "DESIGN"
    ELIGIBILITY = "ELIGIBILITY"
    SECTIONS = "SECTIONS"
    ENDPOINTS = "ENDPOINTS"
    SCHEDULE = "SCHEDULE"
    STATISTICS = "STATISTICS"


class CriterionKind(StrEnum):
    """Whether an eligibility criterion includes or excludes participants."""

    INCLUSION = "INCLUSION"
    EXCLUSION = "EXCLUSION"


class EndpointKind(StrEnum):
    """Clinical trial endpoint hierarchy level."""

    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    EXPLORATORY = "EXPLORATORY"


class M11Heading(StrEnum):
    """Standardized ICH M11 protocol section headings."""

    PROTOCOL_SUMMARY = "PROTOCOL_SUMMARY"
    INTRODUCTION = "INTRODUCTION"
    OBJECTIVES_AND_ESTIMANDS = "OBJECTIVES_AND_ESTIMANDS"
    TRIAL_DESIGN = "TRIAL_DESIGN"
    TRIAL_POPULATION = "TRIAL_POPULATION"
    TRIAL_INTERVENTION = "TRIAL_INTERVENTION"
    DISCONTINUATION = "DISCONTINUATION"
    ASSESSMENTS_AND_PROCEDURES = "ASSESSMENTS_AND_PROCEDURES"
    STATISTICAL_CONSIDERATIONS = "STATISTICAL_CONSIDERATIONS"
    REGULATORY_AND_ETHICAL = "REGULATORY_AND_ETHICAL"
    OTHER = "OTHER"


class TrialPhase(StrEnum):
    """Standardized trial phases."""

    EARLY_PHASE1 = "EARLY_PHASE1"
    PHASE1 = "PHASE1"
    PHASE1_PHASE2 = "PHASE1/PHASE2"
    PHASE2 = "PHASE2"
    PHASE2_PHASE3 = "PHASE2/PHASE3"
    PHASE3 = "PHASE3"
    PHASE4 = "PHASE4"
    NOT_APPLICABLE = "NA"
    UNKNOWN = "UNKNOWN"


class AllocationType(StrEnum):
    """Trial allocation methods."""

    RANDOMIZED = "RANDOMIZED"
    NON_RANDOMIZED = "NON_RANDOMIZED"
    NA = "NA"


class InterventionModelType(StrEnum):
    """Design intervention models."""

    PARALLEL = "PARALLEL"
    CROSSOVER = "CROSSOVER"
    FACTORIAL = "FACTORIAL"
    SINGLE_GROUP = "SINGLE_GROUP"
    SEQUENTIAL = "SEQUENTIAL"
    OTHER = "OTHER"


class MaskingType(StrEnum):
    """Masking / blinding levels."""

    NONE = "NONE"
    SINGLE = "SINGLE"
    DOUBLE = "DOUBLE"
    TRIPLE = "TRIPLE"
    QUADRUPLE = "QUADRUPLE"


class PageText(BaseModel):
    """Extracted text content for a single 1-based PDF page."""

    page_number: int
    text: str


class Citation(BaseModel):
    """Verbatim quote and 1-based page number grounding an extracted fact."""

    page_number: int
    quote: str
    is_verified: bool = False


class CitedValue[ValueT](BaseModel):
    """Typed value paired with its supporting PDF citation."""

    value: ValueT
    citation: Citation


class ExtractionWarning(BaseModel):
    """Non-fatal extraction or verification issue attached to a facet."""

    facet: FacetName
    message: str


class EligibilityCriterion(BaseModel):
    """One inclusion or exclusion criterion from a protocol or peer trial."""

    criterion_id: str
    kind: CriterionKind
    text: str
    citation: Citation | None = None


class EligibilityExtraction(BaseModel):
    """Result schema for the ELIGIBILITY facet."""

    criteria: list[EligibilityCriterion]


class TrialDesignFacts(BaseModel):
    """Result schema for the DESIGN facet."""

    official_title: CitedValue[str] | None = None
    phase: CitedValue[TrialPhase] | None = None
    allocation: CitedValue[AllocationType] | None = None
    intervention_model: CitedValue[InterventionModelType] | None = None
    masking: CitedValue[MaskingType] | None = None
    target_enrollment: CitedValue[int] | None = None
    arm_count: CitedValue[int] | None = None
    min_age_years: CitedValue[float] | None = None
    max_age_years: CitedValue[float] | None = None
    # Whether each age limit includes its endpoint: True for ">=18" or
    # "18 and older", False for "<18" or "under 18". None when the
    # limit or its wording is absent; consumers must not assume either.
    is_min_age_inclusive: bool | None = None
    is_max_age_inclusive: bool | None = None
    accepts_healthy_volunteers: CitedValue[bool] | None = None
    site_count: CitedValue[int] | None = None
    country_count: CitedValue[int] | None = None
    has_data_monitoring_committee: CitedValue[bool] | None = None
    nct_id: CitedValue[str] | None = None


class ProtocolSection(BaseModel):
    """Mapped protocol section classified under an ICH M11 heading."""

    heading: M11Heading
    title: str
    start_page: int
    end_page: int
    summary: str
    citation: Citation


class SectionMap(BaseModel):
    """Result schema for the SECTIONS facet."""

    sections: list[ProtocolSection]


class Endpoint(BaseModel):
    """Clinical trial endpoint with optional assessment time frame."""

    kind: EndpointKind
    description: str
    time_frame: str | None = None
    citation: Citation


class EndpointList(BaseModel):
    """Result schema for the ENDPOINTS facet."""

    endpoints: list[Endpoint]


class ScheduledVisit(BaseModel):
    """Visit in the schedule of activities."""

    visit_name: str
    study_day: int | None = None
    procedures: list[str]
    citation: Citation | None = None


class ScheduleOfActivities(BaseModel):
    """Result schema for the SCHEDULE facet."""

    visits: list[ScheduledVisit]


class StatisticalAssumptions(BaseModel):
    """Result schema for the STATISTICS facet."""

    sample_size: CitedValue[int] | None = None
    power: CitedValue[float] | None = None
    alpha: CitedValue[float] | None = None
    dropout_rate: CitedValue[float] | None = None
    effect_size: CitedValue[str] | None = None


class ProtocolDocument(BaseModel):
    """Assembled structured representation of a clinical trial protocol PDF."""

    protocol_id: str
    title: str
    page_count: int
    pages: list[PageText]
    design: TrialDesignFacts | None = None
    eligibility_criteria: list[EligibilityCriterion] | None = None
    sections: list[ProtocolSection] | None = None
    endpoints: list[Endpoint] | None = None
    schedule: list[ScheduledVisit] | None = None
    statistics: StatisticalAssumptions | None = None
    extraction_warnings: list[ExtractionWarning] = Field(default_factory=list)
