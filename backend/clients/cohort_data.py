"""Data loader client for the CDC NHANES Diabetes cohort and peer protocols."""

import logging
from functools import cache
from pathlib import Path

from pydantic import TypeAdapter

from backend.agents.cohort.models import PatientRecord, PeerTrialProtocol

logger = logging.getLogger(__name__)

DEFAULT_NHANES_COHORT_PATH = Path("data/cohort/nhanes_diabetes.json")
DEFAULT_PEER_PROTOCOLS_PATH = Path("data/cohort/peer_diabetes_protocols.json")

PATIENT_LIST_ADAPTER: TypeAdapter[list[PatientRecord]] = TypeAdapter(
    list[PatientRecord]
)
PEER_PROTOCOL_LIST_ADAPTER: TypeAdapter[list[PeerTrialProtocol]] = TypeAdapter(
    list[PeerTrialProtocol]
)


@cache
def load_nhanes_diabetes_cohort(
    cohort_path: Path = DEFAULT_NHANES_COHORT_PATH,
) -> list[PatientRecord]:
    """Load and validate the NaN-free CDC NHANES Diabetes patient cohort."""
    if not cohort_path.exists():
        raise FileNotFoundError(
            f"Expected NHANES cohort file at {cohort_path}, but it was missing"
        )
    raw_json = cohort_path.read_text(encoding="utf-8")
    patients = PATIENT_LIST_ADAPTER.validate_json(raw_json)
    if not patients:
        raise ValueError(
            f"Expected non-empty patient cohort in {cohort_path}, got 0 rows"
        )
    logger.info(
        "nhanes cohort loaded: path=%s patient_count=%d",
        cohort_path,
        len(patients),
    )
    return patients


@cache
def load_peer_diabetes_protocols(
    peer_path: Path = DEFAULT_PEER_PROTOCOLS_PATH,
) -> list[PeerTrialProtocol]:
    """Load and validate historical peer Diabetes trial protocols."""
    if not peer_path.exists():
        raise FileNotFoundError(
            f"Expected peer protocols file at {peer_path}, but it was missing"
        )
    raw_json = peer_path.read_text(encoding="utf-8")
    peers = PEER_PROTOCOL_LIST_ADAPTER.validate_json(raw_json)
    if not peers:
        raise ValueError(
            f"Expected non-empty peer protocols in {peer_path}, got 0 items"
        )
    logger.info(
        "peer protocols loaded: path=%s peer_count=%d",
        peer_path,
        len(peers),
    )
    return peers
