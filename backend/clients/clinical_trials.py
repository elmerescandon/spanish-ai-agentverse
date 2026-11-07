"""ClinicalTrials.gov client re-export for backwards compatibility."""

from backend.protocol_clinicaltrials.client import (
    ClinicalTrialsClient,
    StudySearchResult,
)

__all__ = ["ClinicalTrialsClient", "StudySearchResult"]
