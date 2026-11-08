"""Typed domain models for Step 3: Cohort Comparison (Part 1 & Part 2)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

PIPELINE_STEP_COHORT = "cohort"
DEFAULT_DECISION_OWNER = "Principal Investigator / Medical Monitor"


class CriterionType(StrEnum):
    """Whether an eligibility criterion includes or excludes participants."""

    INCLUSION = "INCLUSION"
    EXCLUSION = "EXCLUSION"


class CohortVariable(StrEnum):
    """Standardized clinical, demographic, vital, and lab patient variables."""

    AGE = "age"
    SEX = "sex"
    RACE = "race"
    DIABETES_TYPE = "diabetes_type"
    YEARS_WITH_DIABETES = "years_with_diabetes"
    HBA1C = "hba1c"
    EGFR = "egfr"
    CREATININE = "creatinine"
    GLUCOSE = "glucose"
    ALT = "alt"
    AST = "ast"
    CHOLESTEROL = "cholesterol"
    TRIGLYCERIDES = "triglycerides"
    BMI = "bmi"
    WEIGHT_KG = "weight_kg"
    SBP = "sbp"
    DBP = "dbp"
    HR = "hr"
    UACR = "uacr"
    ON_INSULIN = "on_insulin"
    ON_ORAL_MEDS = "on_oral_meds"
    HAS_RETINOPATHY = "has_retinopathy"
    HAS_HEART_FAILURE = "has_heart_failure"
    HAS_CHD_OR_MI = "has_chd_or_mi"
    HAS_CANCER = "has_cancer"
    IS_PREGNANT = "is_pregnant"
    FOOD_INSECURE = "food_insecure"
    PRIOR_BARIATRIC_SURGERY = "prior_bariatric_surgery"
    HISTORY_OF_DKA = "history_of_dka"


class ComparisonOperator(StrEnum):
    """Comparison operators for evaluating patient attributes against rules."""

    GTE = ">="
    LTE = "<="
    GT = ">"
    LT = "<"
    EQ = "=="
    NEQ = "!="
    BETWEEN = "between"


class RuleSimulability(StrEnum):
    """How a protocol criterion can be evaluated on the patient cohort."""

    SIMULATABLE = "SIMULATABLE"
    ADMINISTRATIVE_NON_CLINICAL = "ADMINISTRATIVE_NON_CLINICAL"
    REQUIRES_DOCTOR_REVIEW = "REQUIRES_DOCTOR_REVIEW"


class CriterionClassification(StrEnum):
    """Benchmark classification of a criterion's cohort drop vs peer trials."""

    ACCEPTABLE = "ACCEPTABLE"
    NORMAL_FIELD_STANDARD = "NORMAL_FIELD_STANDARD"
    PROTOCOL_BOTTLENECK = "PROTOCOL_BOTTLENECK"
    UNSIMULATABLE_NEEDS_REVIEW = "UNSIMULATABLE_NEEDS_REVIEW"


class FeasibilityStatus(StrEnum):
    """Overall accrual feasibility rating compared to peer trials."""

    HIGH_FEASIBILITY = "HIGH_FEASIBILITY"
    MODERATE_RISK = "MODERATE_RISK"
    HIGH_ACCRUAL_RISK = "HIGH_ACCRUAL_RISK"


class SeverityLevel(StrEnum):
    """Severity level matching backend/api/schemas.py."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class DecisionStatus(StrEnum):
    """Human-in-the-loop doctor decision status."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DoctorOptionKind(StrEnum):
    """Clinical action option types presented to the reviewing physician."""

    RELAX_TO_PEER_STANDARD = "RELAX_TO_PEER_STANDARD"
    ADD_STRATIFIED_SUBCOHORT = "ADD_STRATIFIED_SUBCOHORT"
    KEEP_STRICT_WITH_JUSTIFICATION = "KEEP_STRICT_WITH_JUSTIFICATION"
    MANUAL_CLINICAL_REVIEW = "MANUAL_CLINICAL_REVIEW"


class PatientRecord(BaseModel):
    """Validated patient record from the CDC NHANES Diabetes cohort."""

    model_config = ConfigDict(extra="ignore")

    patient_id: int
    cycle: str
    age: int = Field(ge=18, le=120)
    sex: str
    race: str
    diabetes_type: str
    years_with_diabetes: float = Field(ge=0.0)
    hba1c: float = Field(gt=0.0)
    egfr: float = Field(gt=0.0)
    creatinine: float = Field(gt=0.0)
    glucose: float = Field(gt=0.0)
    alt: float = Field(ge=0.0)
    ast: float = Field(ge=0.0)
    cholesterol: float = Field(gt=0.0)
    triglycerides: float = Field(gt=0.0)
    bmi: float = Field(gt=0.0)
    weight_kg: float = Field(gt=0.0)
    sbp: float = Field(gt=0.0)
    dbp: float = Field(gt=0.0)
    hr: float = Field(gt=0.0)
    uacr: float = Field(ge=0.0)
    on_insulin: bool
    on_oral_meds: bool
    has_retinopathy: bool
    has_heart_failure: bool
    has_chd_or_mi: bool
    has_cancer: bool
    is_pregnant: bool
    food_insecure: bool
    prior_bariatric_surgery: bool
    history_of_dka: bool


class ProtocolCriterionInput(BaseModel):
    """Input eligibility criterion extracted by the protocol parser."""

    criterion_id: str
    kind: CriterionType
    text: str
    page_number: int | None = None
    quote: str | None = None


class PublishedBaselineSummary(BaseModel):
    """Published baseline characteristics from ClinicalTrials.gov."""

    enrolled_n: int
    mean_age: float
    age_65_plus_pct: float
    female_pct: float
    mean_hba1c: float
    mean_bmi: float
    mean_egfr: float


class PeerTrialProtocol(BaseModel):
    """Historical Diabetes trial protocol for cohort benchmarking."""

    nct_id: str
    title: str
    phase: str
    status: str
    target_enrollment: int
    min_age_years: float | None = None
    max_age_years: float | None = None
    criteria: list[ProtocolCriterionInput]
    published_baseline: PublishedBaselineSummary | None = None


class AtomicPredicate(BaseModel):
    """Single computable condition on a standardized patient variable."""

    variable: CohortVariable
    operator: ComparisonOperator
    value: float | bool | str
    upper_value: float | None = None
    unit: str | None = None


class EligibilityRule(BaseModel):
    """Executable representation of a protocol eligibility criterion."""

    criterion_id: str
    kind: CriterionType
    original_text: str
    page_number: int | None = None
    quote: str | None = None
    simulability: RuleSimulability = RuleSimulability.SIMULATABLE
    unsimulatable_reason: str | None = None
    estimated_literature_drop_pct: float | None = None
    doctor_review_note: str | None = None
    predicates: list[AtomicPredicate] = Field(default_factory=list)


class ContinuousVariableStats(BaseModel):
    """Summary statistics for a continuous clinical variable."""

    mean: float
    sd: float
    median: float
    min_val: float
    max_val: float


class CohortProfile(BaseModel):
    """Demographic, vital sign, lab, and clinical profile of a cohort."""

    patient_count: int
    share_of_base_pct: float
    age_mean: float
    age_sd: float
    age_65_plus_pct: float
    pediatric_under_18_pct: float
    female_pct: float
    race_distribution_pct: dict[str, float]
    vitals: dict[str, ContinuousVariableStats]
    labs: dict[str, ContinuousVariableStats]
    comorbidity_rates_pct: dict[str, float]


class SubgroupDropImpact(BaseModel):
    """Quantifies how a criterion impacts a specific demographic subgroup."""

    subgroup_name: str
    base_share_pct: float
    retained_share_pct: float
    relative_drop_pct: float


class CriterionAttritionStep(BaseModel):
    """Attrition waterfall step and peer benchmark for one criterion."""

    criterion_id: str
    kind: CriterionType
    original_text: str
    page_number: int | None = None
    rule_summary: str
    simulability: RuleSimulability
    patients_before: int
    patients_after: int
    sequential_drop_count: int
    sequential_drop_pct: float
    marginal_drop_count: int
    marginal_drop_pct: float
    peer_mean_drop_pct: float | None = None
    excess_drop_vs_peers_pct: float | None = None
    peer_standard_threshold: str | None = None
    classification: CriterionClassification
    subgroup_impacts: list[SubgroupDropImpact] = Field(default_factory=list)
    doctor_review_note: str | None = None


class WhatIfRelaxationResult(BaseModel):
    """Simulated cohort impact of relaxing a bottleneck to peer standard."""

    criterion_id: str
    original_rule_summary: str
    proposed_rule_summary: str
    proposed_protocol_wording: str
    eligible_before: int
    eligible_after: int
    eligible_pct_before: float
    eligible_pct_after: float
    patients_gained: int
    relative_gain_pct: float
    recovered_subgroup_shares_pct: dict[str, float]
    clinical_safety_note: str


class DoctorOption(BaseModel):
    """Actionable clinical option for the doctor to review and select."""

    option_id: str
    kind: DoctorOptionKind
    title: str
    clinical_rationale: str
    proposed_protocol_text: str | None = None
    replacement_predicates: list[AtomicPredicate] | None = None
    what_if_simulation: WhatIfRelaxationResult | None = None
    safety_monitoring_requirement: str | None = None


class DecisionTraceEntry(BaseModel):
    """Immutable audit log entry for a doctor's human-in-the-loop decision."""

    trace_id: str
    recommendation_id: str
    criterion_id: str
    decision_status: DecisionStatus
    selected_option_id: str | None = None
    decided_by_role: str = DEFAULT_DECISION_OWNER
    doctor_comment: str
    timestamp_iso: str
    eligible_pct_before: float
    eligible_pct_after: float


class CohortRecommendationCard(BaseModel):
    """Doctor-facing decision card with full traceability and HITL options."""

    recommendation_id: str
    protocol_id: str
    criterion_id: str
    severity: SeverityLevel
    classification: CriterionClassification
    title: str
    description: str
    original_criterion_text: str
    page_number: int | None = None
    quote: str | None = None
    compiled_rule_summary: str
    target_drop_pct: float
    peer_benchmark_drop_pct: float | None = None
    subgroup_impacts: list[SubgroupDropImpact] = Field(default_factory=list)
    doctor_options: list[DoctorOption] = Field(default_factory=list)
    decision_owner: str = DEFAULT_DECISION_OWNER
    status: DecisionStatus = DecisionStatus.PENDING
    selected_option_id: str | None = None
    doctor_comment: str | None = None

    def to_api_recommendation_dict(self) -> dict[str, object]:
        """Convert to a dict matching backend.api.schemas.Recommendation."""
        return {
            "recommendation_id": self.recommendation_id,
            "protocol_id": self.protocol_id,
            "source_step": PIPELINE_STEP_COHORT,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "comment": self.doctor_comment,
            "details": {
                "criterion_id": self.criterion_id,
                "classification": self.classification.value,
                "original_criterion_text": self.original_criterion_text,
                "page_number": self.page_number,
                "quote": self.quote,
                "compiled_rule_summary": self.compiled_rule_summary,
                "target_drop_pct": self.target_drop_pct,
                "peer_benchmark_drop_pct": self.peer_benchmark_drop_pct,
                "subgroup_impacts": [
                    impact.model_dump() for impact in self.subgroup_impacts
                ],
                "doctor_options": [
                    opt.model_dump() for opt in self.doctor_options
                ],
                "decision_owner": self.decision_owner,
                "selected_option_id": self.selected_option_id,
            },
        }


class PeerTrialBenchmarkRun(BaseModel):
    """Result of running one peer trial's criteria on the NHANES cohort."""

    nct_id: str
    title: str
    phase: str
    eligible_count: int
    eligible_pct: float
    profile: CohortProfile
    published_baseline: PublishedBaselineSummary | None = None


class CohortComparisonReport(BaseModel):
    """Complete output of Step 3 (Part 1 & Part 2) Cohort Comparison."""

    protocol_id: str
    protocol_title: str
    base_population_count: int
    target_eligible_count: int
    target_eligible_pct: float
    peer_mean_eligible_pct: float
    feasibility_status: FeasibilityStatus
    disease_population_profile: CohortProfile
    target_cohort_profile: CohortProfile
    peer_benchmark_profile: CohortProfile
    peer_trial_runs: list[PeerTrialBenchmarkRun]
    compiled_rules: list[EligibilityRule]
    attrition_funnel: list[CriterionAttritionStep]
    unsimulatable_criteria_for_doctor: list[EligibilityRule]
    recommendations: list[CohortRecommendationCard]
    decision_audit_log: list[DecisionTraceEntry] = Field(default_factory=list)
