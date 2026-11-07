"""Pure logic parser to extract normalized features from raw clinical trial protocol records."""

import re
from typing import Final

from backend.protocols.models import (
    AllocationType,
    InterventionModelType,
    MaskingType,
    OverallStatus,
    ProtocolFeatures,
    TerminationCategory,
    TrialPhase,
)

DAYS_IN_YEAR: Final[float] = 365.25
WEEKS_IN_YEAR: Final[float] = 52.143
MONTHS_IN_YEAR: Final[float] = 12.0

ENROLLMENT_KEYWORDS: Final[list[str]] = [
    "accrual",
    "recruitment",
    "enrollment",
    "enrolment",
    "lagged",
    "slow recruit",
    "poor recruit",
    "unable to recruit",
    "eligible patient",
    "insufficient participant",
]

SAFETY_KEYWORDS: Final[list[str]] = [
    "safety",
    "toxicity",
    "tolerability",
    "adverse event",
    "death",
    "dsmb recommendation",
    "benefit/tolerability",
]

FUTILITY_KEYWORDS: Final[list[str]] = [
    "futility",
    "efficacy",
    "lack of benefit",
    "low probability of achieving",
    "did not meet endpoint",
    "insufficient effect",
]

COVID_KEYWORDS: Final[list[str]] = [
    "covid",
    "pandemic",
    "sars-cov-2",
]

BUSINESS_KEYWORDS: Final[list[str]] = [
    "business decision",
    "funding",
    "financial",
    "sponsor decision",
    "commercial",
    "pipeline",
    "repriorit",
    "strategic decision",
]

REGULATORY_CMC_KEYWORDS: Final[list[str]] = [
    "regulatory",
    "fda",
    "crl",
    "gmp",
    "manufacturing",
    "supply shortage",
    "drug shortage",
]

STUDY_DESIGN_KEYWORDS: Final[list[str]] = [
    "scheduling",
    "complexity",
    "protocol deviation",
    "design flaw",
    "infeasible",
]


def parse_eligibility_criteria_text(text: str | None) -> tuple[int, int]:
    """Extracts counts of inclusion and exclusion criteria from raw criteria text."""
    if not text or not text.strip():
        return (0, 0)

    clean_text = text.replace("\r\n", "\n")
    lower_text = clean_text.lower()

    inclusion_pos = lower_text.find("inclusion criteria")
    exclusion_pos = lower_text.find("exclusion criteria")

    inclusion_block = ""
    exclusion_block = ""

    if inclusion_pos != -1 and exclusion_pos != -1:
        if inclusion_pos < exclusion_pos:
            inclusion_block = clean_text[inclusion_pos:exclusion_pos]
            exclusion_block = clean_text[exclusion_pos:]
        else:
            exclusion_block = clean_text[exclusion_pos:inclusion_pos]
            inclusion_block = clean_text[inclusion_pos:]
    elif inclusion_pos != -1:
        inclusion_block = clean_text[inclusion_pos:]
    elif exclusion_pos != -1:
        exclusion_block = clean_text[exclusion_pos:]
    else:
        # Fallback: treat entire text as inclusion criteria
        inclusion_block = clean_text

    def _count_bullet_items(block: str) -> int:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        count = 0
        for line in lines:
            if line.startswith(("*", "-", "•", "–")) or re.match(
                r"^\d+[\.\)]\s+", line
            ):
                count += 1
        # If no bullet markers found, count non-header lines
        if count == 0 and lines:
            non_headers = [
                line
                for line in lines
                if not line.lower().endswith("criteria:")
                and not line.lower().endswith("criteria")
            ]
            count = len(non_headers)
        return count

    return (_count_bullet_items(inclusion_block), _count_bullet_items(exclusion_block))


def parse_age_to_years(age_str: str | None) -> float | None:
    """Parses ClinicalTrials.gov age strings (e.g. '18 Years', '6 Months') into years."""
    if not age_str:
        return None

    match = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)", age_str.strip())
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2).lower()

    if "year" in unit:
        return round(value, 2)
    if "month" in unit:
        return round(value / MONTHS_IN_YEAR, 2)
    if "week" in unit:
        return round(value / WEEKS_IN_YEAR, 2)
    if "day" in unit:
        return round(value / DAYS_IN_YEAR, 2)

    return round(value, 2)


def categorize_termination_reason(
    why_stopped: str | None,
) -> TerminationCategory | None:
    """Categorizes the whyStopped text into standardized failure modes."""
    if not why_stopped or not why_stopped.strip():
        return None

    text = why_stopped.lower()

    if any(keyword in text for keyword in COVID_KEYWORDS):
        return TerminationCategory.COVID_PANDEMIC
    if any(keyword in text for keyword in ENROLLMENT_KEYWORDS):
        return TerminationCategory.ENROLLMENT_SHORTFALL
    if any(keyword in text for keyword in SAFETY_KEYWORDS):
        return TerminationCategory.SAFETY_TOXICITY
    if any(keyword in text for keyword in FUTILITY_KEYWORDS):
        return TerminationCategory.FUTILITY_EFFICACY
    if any(keyword in text for keyword in BUSINESS_KEYWORDS):
        return TerminationCategory.SPONSOR_BUSINESS
    if any(keyword in text for keyword in REGULATORY_CMC_KEYWORDS):
        return TerminationCategory.REGULATORY_CMC
    if any(keyword in text for keyword in STUDY_DESIGN_KEYWORDS):
        return TerminationCategory.STUDY_DESIGN

    return TerminationCategory.UNSPECIFIED_OR_OTHER


def _parse_phase(phases_raw: list[str] | None) -> TrialPhase:
    if not phases_raw:
        return TrialPhase.UNKNOWN
    joined = "/".join(phases_raw).upper()
    if "PHASE1" in joined and "PHASE2" in joined:
        return TrialPhase.PHASE1_PHASE2
    if "PHASE2" in joined and "PHASE3" in joined:
        return TrialPhase.PHASE2_PHASE3
    if "PHASE3" in joined:
        return TrialPhase.PHASE3
    if "PHASE2" in joined:
        return TrialPhase.PHASE2
    if "PHASE1" in joined:
        return TrialPhase.PHASE1
    if "PHASE4" in joined:
        return TrialPhase.PHASE4
    if "EARLY_PHASE1" in joined:
        return TrialPhase.EARLY_PHASE1
    if "NA" in joined:
        return TrialPhase.NOT_APPLICABLE
    return TrialPhase.UNKNOWN


def extract_protocol_features(study_dict: dict[str, object]) -> ProtocolFeatures:
    """Extracts normalized ProtocolFeatures from a raw ClinicalTrials.gov study record."""
    protocol_section = study_dict.get("protocolSection")
    if not isinstance(protocol_section, dict):
        raise TypeError("Missing or invalid 'protocolSection' in study record")

    # Safe cast helper for internal nested dictionaries
    def get_dict(parent: dict[str, object], key: str) -> dict[str, object]:
        val = parent.get(key)
        return dict(val) if isinstance(val, dict) else {}

    ident = get_dict(protocol_section, "identificationModule")
    status_mod = get_dict(protocol_section, "statusModule")
    design_mod = get_dict(protocol_section, "designModule")
    design_info = get_dict(design_mod, "designInfo")
    masking_info = get_dict(design_info, "maskingInfo")
    elig_mod = get_dict(protocol_section, "eligibilityModule")
    outcomes_mod = get_dict(protocol_section, "outcomesModule")
    oversight_mod = get_dict(protocol_section, "oversightModule")
    arms_mod = get_dict(protocol_section, "armsInterventionsModule")
    locs_mod = get_dict(protocol_section, "contactsLocationsModule")
    cond_mod = get_dict(protocol_section, "conditionsModule")

    nct_id = str(ident.get("nctId", "UNKNOWN"))
    title = str(ident.get("briefTitle", ident.get("officialTitle", "Untitled Study")))

    # Conditions & MeSH
    conditions_raw = cond_mod.get("conditions")
    conditions = (
        [str(c) for c in conditions_raw] if isinstance(conditions_raw, list) else []
    )

    derived = get_dict(study_dict, "derivedSection")
    cond_browse = get_dict(derived, "conditionBrowseModule")
    meshes_raw = cond_browse.get("meshes")
    mesh_conditions: list[str] = []
    if isinstance(meshes_raw, list):
        for m in meshes_raw:
            if isinstance(m, dict) and "term" in m:
                mesh_conditions.append(str(m["term"]))

    # Status & Ground Truth
    raw_status = str(status_mod.get("overallStatus", "OTHER")).upper()
    try:
        status = OverallStatus(raw_status)
    except ValueError:
        status = OverallStatus.OTHER

    why_stopped_raw = status_mod.get("whyStopped")
    why_stopped = str(why_stopped_raw) if why_stopped_raw is not None else None
    termination_cat = categorize_termination_reason(why_stopped)
    is_successful = status == OverallStatus.COMPLETED

    # Phase & Design
    phases_raw = design_mod.get("phases")
    phases_list = [str(p) for p in phases_raw] if isinstance(phases_raw, list) else None
    phase = _parse_phase(phases_list)

    alloc_raw = str(design_info.get("allocation", "NA")).upper()
    try:
        allocation = AllocationType(alloc_raw)
    except ValueError:
        allocation = AllocationType.NA

    model_raw = str(design_info.get("interventionModel", "OTHER")).upper()
    try:
        intervention_model = InterventionModelType(model_raw)
    except ValueError:
        intervention_model = InterventionModelType.OTHER

    mask_raw = str(masking_info.get("masking", "NONE")).upper()
    try:
        masking = MaskingType(mask_raw)
    except ValueError:
        masking = MaskingType.NONE

    # Enrollment
    enrollment_info = get_dict(design_mod, "enrollmentInfo")
    raw_count = enrollment_info.get("count", 0)
    target_enrollment = int(raw_count) if isinstance(raw_count, (int, float)) else 0

    # Arms & Outcomes
    arms_raw = arms_mod.get("armGroups")
    arm_count = len(arms_raw) if isinstance(arms_raw, list) and arms_raw else 1

    primary_outcomes = outcomes_mod.get("primaryOutcomes")
    num_primary = len(primary_outcomes) if isinstance(primary_outcomes, list) else 1

    secondary_outcomes = outcomes_mod.get("secondaryOutcomes")
    num_secondary = (
        len(secondary_outcomes) if isinstance(secondary_outcomes, list) else 0
    )

    # Eligibility
    crit_text = elig_mod.get("eligibilityCriteria")
    num_inc, num_exc = parse_eligibility_criteria_text(
        str(crit_text) if crit_text is not None else None
    )
    exc_ratio = round(num_exc / max(1, num_inc), 2)

    min_age = parse_age_to_years(
        str(elig_mod.get("minimumAge")) if elig_mod.get("minimumAge") else None
    )
    max_age = parse_age_to_years(
        str(elig_mod.get("maximumAge")) if elig_mod.get("maximumAge") else None
    )
    age_span = (
        round(max_age - min_age, 2)
        if (min_age is not None and max_age is not None and max_age >= min_age)
        else None
    )
    healthy_vols = bool(elig_mod.get("healthyVolunteers", False))

    # Locations
    locs_raw = locs_mod.get("locations")
    site_count = len(locs_raw) if isinstance(locs_raw, list) and locs_raw else 1
    countries: set[str] = set()
    if isinstance(locs_raw, list):
        for loc in locs_raw:
            if isinstance(loc, dict) and "country" in loc:
                countries.add(str(loc["country"]))
    country_count = max(1, len(countries))

    pts_per_site = (
        round(target_enrollment / max(1, site_count), 2)
        if target_enrollment > 0
        else 0.0
    )

    # Oversight
    has_dmc = bool(oversight_mod.get("oversightHasDmc", False))
    is_fda = bool(
        oversight_mod.get("isFdaRegulatedDrug", False)
        or oversight_mod.get("isFdaRegulatedDevice", False)
    )

    return ProtocolFeatures(
        nct_id=nct_id,
        title=title,
        conditions=conditions,
        mesh_conditions=mesh_conditions,
        phase=phase,
        study_type=str(design_mod.get("studyType", "INTERVENTIONAL")),
        allocation=allocation,
        intervention_model=intervention_model,
        masking=masking,
        target_enrollment=target_enrollment,
        arm_count=arm_count,
        num_primary_outcomes=num_primary,
        num_secondary_outcomes=num_secondary,
        num_inclusion_criteria=num_inc,
        num_exclusion_criteria=num_exc,
        exclusion_ratio=exc_ratio,
        min_age_years=min_age,
        max_age_years=max_age,
        age_span_years=age_span,
        healthy_volunteers=healthy_vols,
        site_count=site_count,
        country_count=country_count,
        patients_per_site=pts_per_site,
        has_dmc=has_dmc,
        is_fda_regulated=is_fda,
        status=status,
        is_successful=is_successful,
        why_stopped=why_stopped,
        termination_category=termination_cat,
    )
