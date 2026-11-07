"""Protocol clustering, feature extraction, and defect recommendation package for ClinicalTrials.gov."""

from backend.protocol_clinicaltrials.client import (
    ClinicalTrialsClient,
    StudySearchResult,
)
from backend.protocol_clinicaltrials.clustering import ProtocolClusteringEngine
from backend.protocol_clinicaltrials.models import (
    AllocationType,
    ClusterProfile,
    InterventionModelType,
    MaskingType,
    OverallStatus,
    ProtocolEvaluationReport,
    ProtocolFeatures,
    ProtocolRecommendation,
    TerminationCategory,
    TrialPhase,
)
from backend.protocol_clinicaltrials.parser import (
    categorize_termination_reason,
    extract_protocol_features,
    parse_age_to_years,
    parse_eligibility_criteria_text,
)
from backend.protocol_clinicaltrials.recommender import evaluate_candidate_protocol

__all__ = [
    "AllocationType",
    "ClinicalTrialsClient",
    "ClusterProfile",
    "InterventionModelType",
    "MaskingType",
    "OverallStatus",
    "ProtocolClusteringEngine",
    "ProtocolEvaluationReport",
    "ProtocolFeatures",
    "ProtocolRecommendation",
    "StudySearchResult",
    "TerminationCategory",
    "TrialPhase",
    "categorize_termination_reason",
    "evaluate_candidate_protocol",
    "extract_protocol_features",
    "parse_age_to_years",
    "parse_eligibility_criteria_text",
]
