"""Data loader client for the CDC NHANES Diabetes cohort and peer protocols."""

import json
import logging
import re
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.alias_generators import to_camel

from backend.agents.cohort.models import (
    CohortComparisonReport,
    CriterionType,
    PatientRecord,
    PeerTrialProtocol,
    ProtocolCriterionInput,
)

logger = logging.getLogger(__name__)

DEFAULT_NHANES_COHORT_PATH = Path("data/cohort/nhanes_diabetes.json")
DEFAULT_PEER_PROTOCOLS_PATH = Path("data/cohort/peer_diabetes_protocols.json")
DEFAULT_THEO_PEERS_DIR = Path("data/peers/studies")
DEFAULT_RECOMMENDATIONS_JSON_PATH = Path(
    "data/cohort/cohort_recommendations.json"
)
MIN_ADULT_AGE_YEARS = 18.0
YEARS_NUMBER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)")
BULLET_PREFIX_PATTERN = re.compile(
    r"^\s*(?:[\*\-\u2022]+|\d+[\.\)]|[a-zA-Z][\.\)])\s*"
)

PATIENT_LIST_ADAPTER: TypeAdapter[list[PatientRecord]] = TypeAdapter(
    list[PatientRecord]
)
PEER_PROTOCOL_LIST_ADAPTER: TypeAdapter[list[PeerTrialProtocol]] = TypeAdapter(
    list[PeerTrialProtocol]
)


class CohortDataError(FileNotFoundError, ValueError):
    """Raised when the NHANES cohort or peer protocol files are invalid."""


class _RegistryModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class _RegistryIdentification(_RegistryModel):
    nct_id: str
    brief_title: str


class _RegistryStatus(_RegistryModel):
    overall_status: str = "COMPLETED"


class _RegistryEnrollment(_RegistryModel):
    count: int = 0


class _RegistryDesignInfo(_RegistryModel):
    primary_purpose: str | None = None


class _RegistryDesign(_RegistryModel):
    phases: list[str] = Field(default_factory=list)
    design_info: _RegistryDesignInfo | None = None
    enrollment_info: _RegistryEnrollment | None = None


class _RegistryEligibility(_RegistryModel):
    eligibility_criteria: str = ""
    minimum_age: str | None = None
    maximum_age: str | None = None
    std_ages: list[str] = Field(default_factory=list)


class _RegistryConditions(_RegistryModel):
    conditions: list[str] = Field(default_factory=list)


class _RegistryProtocolSection(_RegistryModel):
    identification_module: _RegistryIdentification
    status_module: _RegistryStatus = Field(default_factory=_RegistryStatus)
    design_module: _RegistryDesign = Field(default_factory=_RegistryDesign)
    eligibility_module: _RegistryEligibility = Field(
        default_factory=_RegistryEligibility
    )
    conditions_module: _RegistryConditions = Field(
        default_factory=_RegistryConditions
    )


class _RegistryMesh(_RegistryModel):
    term: str


class _RegistryBrowse(_RegistryModel):
    meshes: list[_RegistryMesh] = Field(default_factory=list)


class _RegistryDerivedSection(_RegistryModel):
    condition_browse_module: _RegistryBrowse | None = None


class _RegistryStudyEnvelope(_RegistryModel):
    protocol_section: _RegistryProtocolSection
    derived_section: _RegistryDerivedSection | None = None


def _parse_age_years(age_str: str | None) -> float | None:
    if not age_str:
        return None
    lower = age_str.lower()
    match = YEARS_NUMBER_PATTERN.search(lower)
    if match is None:
        return None
    val = float(match.group(1))
    if "month" in lower:
        return round(val / 12.0, 2)
    return val


def _split_eligibility_text(
    nct_id: str, raw_text: str
) -> list[ProtocolCriterionInput]:
    """Split ClinicalTrials.gov eligibility text into structured criteria."""
    criteria: list[ProtocolCriterionInput] = []
    current_kind = CriterionType.INCLUSION
    in_idx = 0
    ex_idx = 0

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("inclusion criteria"):
            current_kind = CriterionType.INCLUSION
            continue
        if lower.startswith("exclusion criteria"):
            current_kind = CriterionType.EXCLUSION
            continue

        cleaned = BULLET_PREFIX_PATTERN.sub("", line).strip()
        if len(cleaned) < 6:
            continue

        if current_kind == CriterionType.INCLUSION:
            in_idx += 1
            crit_id = f"{nct_id}-IN-{in_idx:02d}"
        else:
            ex_idx += 1
            crit_id = f"{nct_id}-EX-{ex_idx:02d}"

        criteria.append(
            ProtocolCriterionInput(
                criterion_id=crit_id,
                kind=current_kind,
                text=cleaned,
            )
        )
    return criteria


def parse_registry_study_to_peer_protocol(
    study_payload: dict[str, object],
) -> PeerTrialProtocol | None:
    """Convert a ClinicalTrials.gov v2 study record (Theo's format) to peer."""
    envelope = _RegistryStudyEnvelope.model_validate(study_payload)
    proto = envelope.protocol_section
    elig = proto.eligibility_module

    # Enforce strictly adult population (age >= 18, no CHILD stdAges)
    min_age = _parse_age_years(elig.minimum_age)
    max_age = _parse_age_years(elig.maximum_age)
    if "CHILD" in elig.std_ages and "ADULT" not in elig.std_ages:
        return None
    if min_age is not None and min_age < MIN_ADULT_AGE_YEARS:
        return None
    if max_age is not None and max_age < MIN_ADULT_AGE_YEARS:
        return None

    # Enforce Type 2 Diabetes condition and exclude Type 1 Diabetes
    mesh_terms: set[str] = set()
    if (
        envelope.derived_section is not None
        and envelope.derived_section.condition_browse_module is not None
    ):
        mesh_terms = {
            m.term.lower()
            for m in envelope.derived_section.condition_browse_module.meshes
        }
    condition_texts = {c.lower() for c in proto.conditions_module.conditions}
    all_conds = mesh_terms | condition_texts
    if any("type 1" in c for c in all_conds):
        return None
    if all_conds and not any(
        "type 2" in c or "diabetes" in c for c in all_conds
    ):
        return None

    criteria = _split_eligibility_text(
        proto.identification_module.nct_id,
        elig.eligibility_criteria,
    )
    if not criteria:
        return None

    phase = (
        proto.design_module.phases[0]
        if proto.design_module.phases
        else "PHASE3"
    )
    enrolled = (
        proto.design_module.enrollment_info.count
        if proto.design_module.enrollment_info is not None
        else 0
    )

    return PeerTrialProtocol(
        nct_id=proto.identification_module.nct_id,
        title=proto.identification_module.brief_title,
        phase=phase,
        status=proto.status_module.overall_status,
        target_enrollment=enrolled,
        min_age_years=min_age if min_age is not None else MIN_ADULT_AGE_YEARS,
        max_age_years=max_age,
        criteria=criteria,
    )


def load_peer_protocols_from_registry(
    studies_dir: Path = DEFAULT_THEO_PEERS_DIR,
) -> list[PeerTrialProtocol]:
    """Load adult T2D peer protocols from Theo's cached registry directory."""
    if not studies_dir.exists() or not studies_dir.is_dir():
        return []

    peers: list[PeerTrialProtocol] = []
    for study_file in sorted(studies_dir.glob("*.json")):
        raw_data = json.loads(study_file.read_text(encoding="utf-8"))
        if isinstance(raw_data, dict):
            parsed = parse_registry_study_to_peer_protocol(raw_data)
            if parsed is not None:
                peers.append(parsed)
    return peers


@cache
def load_nhanes_diabetes_cohort(
    cohort_path: Path = DEFAULT_NHANES_COHORT_PATH,
) -> list[PatientRecord]:
    """Load and validate the NaN-free CDC NHANES Diabetes patient cohort."""
    if not cohort_path.exists():
        raise CohortDataError(
            f"Expected NHANES cohort file at {cohort_path}, but it was missing"
        )
    raw_json = cohort_path.read_text(encoding="utf-8")
    patients = PATIENT_LIST_ADAPTER.validate_json(raw_json)
    if not patients:
        raise CohortDataError(
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
    registry_dir: Path = DEFAULT_THEO_PEERS_DIR,
) -> list[PeerTrialProtocol]:
    """Load peer Diabetes protocols, merging adult peers from Theo's store."""
    if not peer_path.exists():
        raise CohortDataError(
            f"Expected peer protocols file at {peer_path}, but it was missing"
        )
    raw_json = peer_path.read_text(encoding="utf-8")
    peers = PEER_PROTOCOL_LIST_ADAPTER.validate_json(raw_json)
    seen_ids = {peer.nct_id for peer in peers}

    for registry_peer in load_peer_protocols_from_registry(registry_dir):
        if registry_peer.nct_id not in seen_ids:
            peers.append(registry_peer)
            seen_ids.add(registry_peer.nct_id)

    if not peers:
        raise CohortDataError(
            f"Expected non-empty peer protocols in {peer_path}, got 0 items"
        )
    logger.info(
        "peer protocols loaded: path=%s peer_count=%d",
        peer_path,
        len(peers),
    )
    return peers


def save_cohort_recommendations_json(
    report: CohortComparisonReport,
    output_path: Path = DEFAULT_RECOMMENDATIONS_JSON_PATH,
) -> Path:
    """Persist API-ready cohort recommendations and summary metrics to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol_id": report.protocol_id,
        "protocol_title": report.protocol_title,
        "source_step": "cohort",
        "base_population_count": report.base_population_count,
        "target_eligible_count": report.target_eligible_count,
        "target_eligible_pct": report.target_eligible_pct,
        "peer_mean_eligible_pct": report.peer_mean_eligible_pct,
        "feasibility_status": report.feasibility_status.value,
        "data_transparency_notices": report.data_transparency_notices,
        "recommendations": [
            card.to_api_recommendation_dict()
            for card in report.recommendations
        ],
        "decision_audit_log": [
            entry.model_dump() for entry in report.decision_audit_log
        ],
    }
    temp_path = output_path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(output_path)
    logger.info(
        "cohort recommendations saved: path=%s count=%d",
        output_path,
        len(report.recommendations),
    )
    return output_path
