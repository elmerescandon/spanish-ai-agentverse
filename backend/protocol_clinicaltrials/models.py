"""Domain models and schemas for clinical trial protocols, features, and clusters."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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


class OverallStatus(StrEnum):
    """ClinicalTrials.gov recruitment and completion statuses."""

    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"
    WITHDRAWN = "WITHDRAWN"
    SUSPENDED = "SUSPENDED"
    RECRUITING = "RECRUITING"
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    NOT_YET_RECRUITING = "NOT_YET_RECRUITING"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION"
    OTHER = "OTHER"


class TerminationCategory(StrEnum):
    """Normalized categories for why a trial terminated or halted early."""

    ENROLLMENT_SHORTFALL = "ENROLLMENT_SHORTFALL"
    SAFETY_TOXICITY = "SAFETY_TOXICITY"
    FUTILITY_EFFICACY = "FUTILITY_EFFICACY"
    SPONSOR_BUSINESS = "SPONSOR_BUSINESS"
    COVID_PANDEMIC = "COVID_PANDEMIC"
    REGULATORY_CMC = "REGULATORY_CMC"
    STUDY_DESIGN = "STUDY_DESIGN"
    UNSPECIFIED_OR_OTHER = "UNSPECIFIED_OR_OTHER"


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


class ProtocolFeatures(BaseModel):
    """Normalized feature vector for a clinical protocol."""

    model_config = ConfigDict(extra="ignore")

    nct_id: str
    title: str
    conditions: list[str] = Field(default_factory=list)
    mesh_conditions: list[str] = Field(default_factory=list)
    phase: TrialPhase = TrialPhase.UNKNOWN
    study_type: str = "INTERVENTIONAL"
    allocation: AllocationType = AllocationType.NA
    intervention_model: InterventionModelType = InterventionModelType.OTHER
    masking: MaskingType = MaskingType.NONE
    target_enrollment: int = 0
    arm_count: int = 1
    num_primary_outcomes: int = 1
    num_secondary_outcomes: int = 0
    num_inclusion_criteria: int = 0
    num_exclusion_criteria: int = 0
    exclusion_ratio: float = 0.0
    min_age_years: float | None = None
    max_age_years: float | None = None
    age_span_years: float | None = None
    healthy_volunteers: bool = False
    site_count: int = 1
    country_count: int = 1
    patients_per_site: float = 0.0
    has_dmc: bool = False
    is_fda_regulated: bool = False
    status: OverallStatus = OverallStatus.OTHER
    is_successful: bool = False
    why_stopped: str | None = None
    termination_category: TerminationCategory | None = None


class ClusterProfile(BaseModel):
    """Summary profile and statistical distribution of a protocol cluster."""

    model_config = ConfigDict(extra="ignore")

    cluster_id: int
    name: str
    study_count: int
    completed_count: int
    terminated_count: int
    termination_rate: float
    top_mesh_conditions: list[str] = Field(default_factory=list)
    top_phases: list[str] = Field(default_factory=list)
    median_enrollment: float
    median_exclusion_count: float
    p90_exclusion_count: float
    median_primary_outcomes: float
    median_secondary_outcomes: float
    median_site_count: float
    median_patients_per_site: float


class ProtocolRecommendation(BaseModel):
    """Defect prevention recommendation for a candidate protocol."""

    model_config = ConfigDict(extra="ignore")

    category: str
    severity: str
    message: str
    evidence_cluster_metric: str
    recommended_action: str


class ProtocolEvaluationReport(BaseModel):
    """Comprehensive analysis report comparing candidate against peer cluster."""

    model_config = ConfigDict(extra="ignore")

    candidate_nct_id: str
    candidate_title: str
    matched_cluster_id: int
    matched_cluster_name: str
    peer_similarity_score: float
    cluster_termination_rate: float
    recommendations: list[ProtocolRecommendation] = Field(default_factory=list)
