"""Shared contract: the typed models every part of the backend exchanges."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class FacetName(StrEnum):
    """Protocol extraction facets."""

    DESIGN = "DESIGN"
    ELIGIBILITY = "ELIGIBILITY"
    SECTIONS = "SECTIONS"
    ENDPOINTS = "ENDPOINTS"
    SCHEDULE = "SCHEDULE"
    STATISTICS = "STATISTICS"
    ESTIMANDS = "ESTIMANDS"
    INTERVENTIONS = "INTERVENTIONS"
    ANALYSIS = "ANALYSIS"
    SYNOPSIS_CHECK = "SYNOPSIS_CHECK"
    SAFETY_MONITORING = "SAFETY_MONITORING"


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


class InterventionType(StrEnum):
    """High-level category of the trial's primary intervention."""

    DRUG = "DRUG"
    BIOLOGIC = "BIOLOGIC"
    DEVICE = "DEVICE"
    BEHAVIORAL = "BEHAVIORAL"
    OTHER = "OTHER"


class DiabetesType(StrEnum):
    """Target diabetes population type."""

    T1D = "T1D"
    T2D = "T2D"
    OTHER = "OTHER"


class DrugClass(StrEnum):
    """Pharmacological class of the investigational diabetes therapy."""

    METFORMIN = "METFORMIN"
    SULFONYLUREA = "SULFONYLUREA"
    DPP4_INHIBITOR = "DPP4_INHIBITOR"
    SGLT2_INHIBITOR = "SGLT2_INHIBITOR"
    GLP1_RECEPTOR_AGONIST = "GLP1_RECEPTOR_AGONIST"
    TZD = "TZD"
    INSULIN = "INSULIN"
    OTHER = "OTHER"


class ControlType(StrEnum):
    """Comparator arm control type."""

    PLACEBO = "PLACEBO"
    ACTIVE = "ACTIVE"
    USUAL_CARE = "USUAL_CARE"
    NONE = "NONE"
    OTHER = "OTHER"


class EstimandStrategy(StrEnum):
    """ICH E9(R1) intercurrent event handling strategies."""

    TREATMENT_POLICY = "TREATMENT_POLICY"
    HYPOTHETICAL = "HYPOTHETICAL"
    COMPOSITE = "COMPOSITE"
    WHILE_ON_TREATMENT = "WHILE_ON_TREATMENT"
    PRINCIPAL_STRATUM = "PRINCIPAL_STRATUM"
    OTHER = "OTHER"


class IntercurrentEventType(StrEnum):
    """Canonical intercurrent event categories for ICH E9(R1) estimands."""

    RESCUE_MEDICATION = "RESCUE_MEDICATION"
    TREATMENT_DISCONTINUATION = "TREATMENT_DISCONTINUATION"
    BACKGROUND_THERAPY_CHANGE = "BACKGROUND_THERAPY_CHANGE"
    DEATH = "DEATH"
    OTHER = "OTHER"


class AnalysisSetType(StrEnum):
    """Canonical statistical analysis population categories."""

    RANDOMIZED = "RANDOMIZED"
    FULL_ANALYSIS = "FULL_ANALYSIS"
    PER_PROTOCOL = "PER_PROTOCOL"
    SAFETY = "SAFETY"
    OTHER = "OTHER"


class SubgroupDimension(StrEnum):
    """Canonical prespecified subgroup analysis dimensions."""

    SEX = "SEX"
    AGE = "AGE"
    RACE = "RACE"
    ETHNICITY = "ETHNICITY"
    BASELINE_HBA1C = "BASELINE_HBA1C"
    DIABETES_DURATION = "DIABETES_DURATION"
    OTHER = "OTHER"


class StratificationFactorType(StrEnum):
    """Canonical randomization stratification and model covariate factors."""

    BASELINE_HBA1C = "BASELINE_HBA1C"
    PRIOR_THERAPY = "PRIOR_THERAPY"
    REGION = "REGION"
    BMI = "BMI"
    AGE = "AGE"
    SEX = "SEX"
    OTHER = "OTHER"


class CommitteeType(StrEnum):
    """Canonical trial oversight and governance committee categories."""

    DATA_MONITORING = "DATA_MONITORING"
    ADJUDICATION = "ADJUDICATION"
    STEERING = "STEERING"
    OTHER = "OTHER"


class EpochType(StrEnum):
    """Canonical trial schema epoch and scheduled visit phases."""

    SCREENING = "SCREENING"
    RUN_IN = "RUN_IN"
    TREATMENT = "TREATMENT"
    FOLLOW_UP = "FOLLOW_UP"
    EXTENSION = "EXTENSION"
    OTHER = "OTHER"


class ScaleDirection(StrEnum):
    """Whether a higher or lower score on an endpoint scale is better."""

    HIGHER = "HIGHER"
    LOWER = "LOWER"


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


class ProtocolSubsection(BaseModel):
    """Numbered subsection heading extracted from the protocol body."""

    number: str
    title: str
    page_number: int
    citation: Citation


class SectionMap(BaseModel):
    """Result schema for the SECTIONS facet."""

    sections: list[ProtocolSection]
    subsections: list[ProtocolSubsection] = Field(default_factory=list)


class Endpoint(BaseModel):
    """Clinical trial endpoint with optional assessment time frame."""

    kind: EndpointKind
    description: str
    time_frame: str | None = None
    scale_name: CitedValue[str] | None = None
    scale_min: CitedValue[float] | None = None
    scale_max: CitedValue[float] | None = None
    scale_better_direction: CitedValue[ScaleDirection] | None = None
    citation: Citation


class EndpointList(BaseModel):
    """Result schema for the ENDPOINTS facet."""

    endpoints: list[Endpoint]


class ScheduledVisit(BaseModel):
    """Visit in the schedule of activities."""

    visit_name: str
    study_day: int | None = None
    epoch: EpochType | None = None
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
    effect_size_value: CitedValue[float] | None = None
    standard_deviation: CitedValue[float] | None = None
    allocation_ratio: CitedValue[float] | None = None
    is_two_sided: CitedValue[bool] | None = None
    has_sample_size_calculation: CitedValue[bool] | None = None
    assumptions_source_citation: CitedValue[str] | None = None
    non_inferiority_margin: CitedValue[float] | None = None


class AnalysisSetItem(BaseModel):
    """Canonical analysis set paired with its display label and citation."""

    category: AnalysisSetType
    label: str
    citation: Citation


class SubgroupItem(BaseModel):
    """Canonical subgroup dimension paired with its label and citation."""

    category: SubgroupDimension
    label: str
    citation: Citation


class StratificationFactorItem(BaseModel):
    """Canonical stratification or covariate factor with label and citation."""

    category: StratificationFactorType
    label: str
    citation: Citation


class CommitteeItem(BaseModel):
    """Canonical oversight committee paired with its label and citation."""

    category: CommitteeType
    label: str
    citation: Citation


class IntercurrentEvent(BaseModel):
    """Intercurrent event and its handling strategy inside an estimand."""

    event_type: IntercurrentEventType
    event: str
    strategy: EstimandStrategy | None = None
    citation: Citation


class Estimand(BaseModel):
    """Structured ICH E9(R1) estimand for one protocol endpoint."""

    endpoint_kind: EndpointKind
    endpoint_description: str
    population: CitedValue[str] | None = None
    variable: CitedValue[str] | None = None
    intercurrent_events: list[IntercurrentEvent] = Field(default_factory=list)
    population_level_summary: CitedValue[str] | None = None
    treatment_condition: CitedValue[str] | None = None


class EstimandExtraction(BaseModel):
    """Result schema for the ESTIMANDS facet."""

    estimands: list[Estimand] = Field(default_factory=list)
    lists_all_five_attributes: CitedValue[bool] | None = None


class InterventionArm(BaseModel):
    """One study intervention or control arm extracted from the protocol."""

    name: str
    intervention_type: InterventionType
    drug_class: DrugClass | None = None
    dose_and_regimen: str | None = None
    is_control: bool = False
    control_type: ControlType | None = None
    citation: Citation


class InterventionExtraction(BaseModel):
    """Result schema for the INTERVENTIONS facet."""

    arms: list[InterventionArm] = Field(default_factory=list)
    background_therapy: CitedValue[str] | None = None
    background_therapy_stable_weeks: CitedValue[float] | None = None
    rescue_therapy_criteria: CitedValue[str] | None = None
    rescue_medication_regimen: CitedValue[str] | None = None
    prohibited_medications: list[CitedValue[str]] = Field(default_factory=list)
    prior_washout_weeks: CitedValue[float] | None = None
    stratification_factors: list[StratificationFactorItem] = Field(
        default_factory=list
    )
    continues_follow_up_after_discontinuation: CitedValue[bool] | None = None
    collects_hba1c_after_discontinuation: CitedValue[bool] | None = None


class AnalysisPlanExtraction(BaseModel):
    """Result schema for the ANALYSIS facet."""

    analysis_sets: list[AnalysisSetItem] = Field(default_factory=list)
    primary_analysis_set: AnalysisSetItem | None = None
    primary_analysis_method: CitedValue[str] | None = None
    primary_analysis_covariates: list[StratificationFactorItem] = Field(
        default_factory=list
    )
    adjusts_for_baseline: CitedValue[bool] | None = None
    missing_data_method: CitedValue[str] | None = None
    sensitivity_analyses: list[CitedValue[str]] = Field(default_factory=list)
    confirmatory_hierarchy: CitedValue[str] | None = None
    controls_type_i_error: CitedValue[bool] | None = None
    prespecified_subgroups: list[SubgroupItem] = Field(default_factory=list)
    has_interim_analysis: CitedValue[bool] | None = None
    stopping_boundaries: CitedValue[str] | None = None
    alpha_spending_function: CitedValue[str] | None = None


class TrialEpoch(BaseModel):
    """One study phase or epoch in the trial schema."""

    epoch_type: EpochType
    name: str
    duration_weeks: float | None = None
    citation: Citation


class SynopsisConsistencyExtraction(BaseModel):
    """Result schema for the SYNOPSIS_CHECK facet."""

    synopsis_enrollment: CitedValue[int] | None = None
    synopsis_arm_count: CitedValue[int] | None = None
    synopsis_treatment_duration_weeks: CitedValue[float] | None = None
    synopsis_primary_timepoint_weeks: CitedValue[float] | None = None
    body_treatment_duration_weeks: CitedValue[float] | None = None
    body_primary_timepoint_weeks: CitedValue[float] | None = None
    synopsis_stratification_factors: list[StratificationFactorItem] = Field(
        default_factory=list
    )
    synopsis_committees: list[CommitteeItem] = Field(default_factory=list)
    governance_committees: list[CommitteeItem] = Field(default_factory=list)
    schema_epochs: list[TrialEpoch] = Field(default_factory=list)
    synopsis_ice_strategies: list[IntercurrentEvent] = Field(
        default_factory=list
    )
    assessments_retention_years: CitedValue[float] | None = None
    icf_retention_years: CitedValue[float] | None = None
    has_lay_summary: CitedValue[bool] | None = None
    states_no_amendments: CitedValue[bool] | None = None
    amendment_numbers: list[CitedValue[int]] = Field(default_factory=list)


class SafetyMonitoringExtraction(BaseModel):
    """Result schema for the SAFETY_MONITORING facet."""

    defines_hypoglycemia_levels: CitedValue[bool] | None = None
    level_1_glucose_mg_dl: CitedValue[float] | None = None
    level_2_glucose_mg_dl: CitedValue[float] | None = None
    level_3_requires_assistance: CitedValue[bool] | None = None
    captures_hypoglycemia_diary: CitedValue[bool] | None = None
    defines_dka_criteria: CitedValue[bool] | None = None
    defines_sae_escalation: CitedValue[bool] | None = None
    monitors_renal_function: CitedValue[bool] | None = None
    has_cv_adjudication: CitedValue[bool] | None = None


class ProtocolDocument(BaseModel):
    """Assembled structured representation of a clinical trial protocol PDF."""

    protocol_id: str
    title: str
    page_count: int
    pages: list[PageText]
    design: TrialDesignFacts | None = None
    eligibility_criteria: list[EligibilityCriterion] | None = None
    sections: list[ProtocolSection] | None = None
    subsections: list[ProtocolSubsection] | None = None
    endpoints: list[Endpoint] | None = None
    schedule: list[ScheduledVisit] | None = None
    statistics: StatisticalAssumptions | None = None
    estimands: EstimandExtraction | None = None
    interventions: InterventionExtraction | None = None
    analysis: AnalysisPlanExtraction | None = None
    synopsis_check: SynopsisConsistencyExtraction | None = None
    safety_monitoring: SafetyMonitoringExtraction | None = None
    extraction_warnings: list[ExtractionWarning] = Field(default_factory=list)


class RuleStatus(StrEnum):
    """Evaluation status of a completeness or consistency rule."""

    FIRED = "fired"
    PASSED = "passed"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_COMPARATORS = "insufficient_comparators"
    CANNOT_ASSESS = "cannot_assess"


NON_SCORED_RULE_STATUSES: frozenset[RuleStatus] = frozenset(
    {
        RuleStatus.NOT_APPLICABLE,
        RuleStatus.INSUFFICIENT_COMPARATORS,
        RuleStatus.CANNOT_ASSESS,
    }
)


class RuleSeverity(StrEnum):
    """Rule severity tier (S1 blocker, S2 major, S3 minor)."""

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"


class GateStatus(StrEnum):
    """Pass/fail status of a registration or review gate."""

    PASS = "pass"
    FAIL = "fail"


class RuleFamily(StrEnum):
    """Catalogue family grouping related protocol exclusion rules."""

    REG = "REG"
    M11 = "M11"
    EST = "EST"
    XS = "XS"
    DM = "DM"
    ELQ = "ELQ"
    EX = "EX"
    AMD = "AMD"


class CheckMethod(StrEnum):
    """Whether a rule was evaluated deterministically in code or by LLM."""

    DETERMINISTIC = "deterministic"
    JUDGEMENT = "judgement"


class SourceTier(StrEnum):
    """Binding force or provenance tier of the rule's regulatory source."""

    LAW = "law"
    ICH = "ich"
    FINAL_GUIDANCE = "final_guidance"
    PRODUCT_EVIDENCE = "product_evidence"
    DRAFT_GUIDANCE = "draft_guidance"
    REGISTRY_QC = "registry_qc"
    REPORTING_GUIDELINE = "reporting_guideline"
    COMPARATOR_NORM = "comparator_norm"
    HEURISTIC = "heuristic"


class SearchedLocation(BaseModel):
    """Protocol section and page range inspected when checking for content."""

    heading: M11Heading
    section_title: str | None = None
    start_page: int
    end_page: int


class FindingLocation(BaseModel):
    """Protocol section numbering, M11 heading and page of a finding."""

    section: str | None = None
    heading: M11Heading | None = None
    page: int | None = None


class RuleFinding(BaseModel):
    """Single rule evaluation produced by the completeness checker."""

    rule_id: str
    family: RuleFamily
    severity: RuleSeverity
    status: RuleStatus
    status_reason: str | None = None
    title: str
    finding: str
    # Why the second Gemini opinion agreed with a flag; None if not reviewed.
    second_opinion_reason: str | None = None
    location: FindingLocation = Field(default_factory=FindingLocation)
    evidence: list[Citation] = Field(default_factory=list)
    searched_locations: list[SearchedLocation] = Field(default_factory=list)
    proposed_fix: str | None = None
    requires_medical_review: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    source_tier: SourceTier
    check_method: CheckMethod

    @model_validator(mode="after")
    def _validate_status_invariants(self) -> Self:
        if (
            self.status == RuleStatus.FIRED
            and not self.evidence
            and not self.searched_locations
        ):
            raise ValueError(
                f"fired finding '{self.rule_id}' must have non-empty "
                "evidence or searched_locations, got evidence=[] and "
                "searched_locations=[]"
            )
        if self.status in NON_SCORED_RULE_STATUSES and (
            self.status_reason is None or not self.status_reason.strip()
        ):
            raise ValueError(
                f"finding '{self.rule_id}' with status '{self.status}' "
                "must have a non-blank status_reason, "
                f"got {self.status_reason!r}"
            )
        return self


class GateResult(BaseModel):
    """Pass/fail outcome of a registration or review readiness gate."""

    status: GateStatus
    is_partial: bool
    failing_rule_ids: list[str] = Field(default_factory=list)


class RunResult(BaseModel):
    """Completeness score and gate outcomes for one evaluation pass."""

    score: float = Field(ge=0.0, le=100.0)
    registration_gate: GateResult
    review_gate: GateResult


class ProposedFix(BaseModel):
    """Suggested replacement text for a fired rule under a protocol section."""

    rule_id: str
    section: str
    replacement_text: str
    requires_medical_review: bool = False


class SponsorInput(BaseModel):
    """Fact placeholder that only the trial sponsor can supply."""

    section: str
    placeholder: str


class TrialProfile(BaseModel):
    """Cited trial characteristics that govern rule applicability."""

    intervention_type: CitedValue[InterventionType] | None = None
    diabetes_type: CitedValue[DiabetesType] | None = None
    drug_class: CitedValue[DrugClass] | None = None
    phase: CitedValue[TrialPhase] | None = None
    control_type: CitedValue[ControlType] | None = None
    is_non_inferiority: CitedValue[bool] | None = None
    is_add_on: CitedValue[bool] | None = None
    is_amended: CitedValue[bool] | None = None


class ComplianceReport(BaseModel):
    """Internal completeness and consistency report for a protocol."""

    protocol_id: str
    protocol_title: str
    protocol_version: str | None = None
    trial_profile: TrialProfile
    rules_evaluated: int
    comparators_used: int = 0
    before: RunResult
    after: RunResult | None = None
    findings: list[RuleFinding]
    fixes: list[ProposedFix] = Field(default_factory=list)
    new_findings_after_fixes: list[RuleFinding] = Field(default_factory=list)
    sponsor_inputs_needed: list[SponsorInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_findings_consistency(self) -> Self:
        if self.rules_evaluated != len(self.findings):
            raise ValueError(
                "rules_evaluated must equal len(findings): "
                f"expected {self.rules_evaluated}, got {len(self.findings)}"
            )
        seen_rule_ids: set[str] = set()
        duplicate_rule_ids: list[str] = []
        for item in self.findings:
            if (
                item.rule_id in seen_rule_ids
                and item.rule_id not in duplicate_rule_ids
            ):
                duplicate_rule_ids.append(item.rule_id)
            seen_rule_ids.add(item.rule_id)
        if duplicate_rule_ids:
            raise ValueError(
                "findings must have unique rule_ids, got duplicate "
                f"rule_id(s): {duplicate_rule_ids}"
            )
        return self
