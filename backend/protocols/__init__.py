"""Protocol clustering, feature extraction, and defect recommendation package."""

from backend.protocols.clustering import ProtocolClusteringEngine
from backend.protocols.models import (
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
from backend.protocols.parser import (
    categorize_termination_reason,
    extract_protocol_features,
    parse_age_to_years,
    parse_eligibility_criteria_text,
)
from backend.protocols.recommender import evaluate_candidate_protocol

__all__ = [
    "AllocationType",
    "ClusterProfile",
    "InterventionModelType",
    "MaskingType",
    "OverallStatus",
    "ProtocolClusteringEngine",
    "ProtocolEvaluationReport",
    "ProtocolFeatures",
    "ProtocolRecommendation",
    "TerminationCategory",
    "TrialPhase",
    "categorize_termination_reason",
    "evaluate_candidate_protocol",
    "extract_protocol_features",
    "parse_age_to_years",
    "parse_eligibility_criteria_text",
]
