"""Pure comparison logic: peer screening and drug classes. No I/O."""

from dataclasses import dataclass
from enum import StrEnum

from backend.agents.protocol_comparison.rules import (
    DRUG_CLASS_KEYWORDS,
    DRUG_CODE_ALIASES,
    DrugClass,
    PeerCriteria,
)
from backend.clients.clinicaltrials_gov import StudyRecord

PLACEBO_WORD = "placebo"


class ExclusionReason(StrEnum):
    """Why a search result was not used as a peer."""

    MISSING_TARGET_CONDITION = "MISSING_TARGET_CONDITION"
    EXCLUDED_CONDITION = "EXCLUDED_CONDITION"
    NO_DRUG_INTERVENTION = "NO_DRUG_INTERVENTION"
    NOT_TREATMENT_PURPOSE = "NOT_TREATMENT_PURPOSE"


@dataclass(frozen=True)
class ExcludedPeer:
    """A search result dropped from the peer set, with every reason."""

    nct_id: str
    reasons: tuple[ExclusionReason, ...]


@dataclass(frozen=True)
class PeerScreening:
    """Search results split into peers and excluded trials."""

    peers: tuple[StudyRecord, ...]
    excluded: tuple[ExcludedPeer, ...]


def _condition_mesh_terms(study: StudyRecord) -> set[str]:
    derived = study.derived_section
    if derived is None or derived.condition_browse_module is None:
        return set()
    return {mesh.term for mesh in derived.condition_browse_module.meshes}


def _has_active_intervention(
    study: StudyRecord, intervention_types: frozenset[str]
) -> bool:
    arms = study.protocol_section.arms_interventions_module
    if arms is None:
        return False
    return any(
        intervention.type in intervention_types
        and PLACEBO_WORD not in intervention.name.lower()
        for intervention in arms.interventions
    )


def _exclusion_reasons(
    study: StudyRecord, criteria: PeerCriteria
) -> tuple[ExclusionReason, ...]:
    reasons: list[ExclusionReason] = []
    mesh_terms = _condition_mesh_terms(study)
    if criteria.required_condition_mesh not in mesh_terms:
        reasons.append(ExclusionReason.MISSING_TARGET_CONDITION)
    if mesh_terms & criteria.excluded_condition_mesh:
        reasons.append(ExclusionReason.EXCLUDED_CONDITION)
    if not _has_active_intervention(study, criteria.intervention_types):
        reasons.append(ExclusionReason.NO_DRUG_INTERVENTION)
    design = study.protocol_section.design_module
    design_info = design.design_info if design is not None else None
    primary_purpose = (
        design_info.primary_purpose if design_info is not None else None
    )
    if primary_purpose != criteria.primary_purpose:
        reasons.append(ExclusionReason.NOT_TREATMENT_PURPOSE)
    return tuple(reasons)


def screen_peers(
    studies: list[StudyRecord], criteria: PeerCriteria
) -> PeerScreening:
    """Keep studies that meet criteria; record why the others were dropped.

    Missing registry fields count as not meeting a criterion, so an
    incomplete record can never slip into the peer set.
    """
    peers: list[StudyRecord] = []
    excluded: list[ExcludedPeer] = []
    for study in studies:
        reasons = _exclusion_reasons(study, criteria)
        if reasons:
            excluded.append(ExcludedPeer(nct_id=study.nct_id, reasons=reasons))
        else:
            peers.append(study)
    return PeerScreening(peers=tuple(peers), excluded=tuple(excluded))


def _intervention_names(study: StudyRecord) -> list[str]:
    """Lower-case non-placebo intervention names and intervention MeSH."""
    names: list[str] = []
    arms = study.protocol_section.arms_interventions_module
    if arms is not None:
        names.extend(
            intervention.name.lower()
            for intervention in arms.interventions
            if PLACEBO_WORD not in intervention.name.lower()
        )
    derived = study.derived_section
    if derived is not None and derived.intervention_browse_module is not None:
        names.extend(
            mesh.term.lower()
            for mesh in derived.intervention_browse_module.meshes
        )
    return names


def classify_drug_classes(study: StudyRecord) -> frozenset[DrugClass]:
    """Return the drug classes of a study's non-placebo interventions.

    Matches generic names (and known development codes) in intervention
    names and intervention MeSH terms. An unknown drug gives no class.
    """
    names = _intervention_names(study)
    return frozenset(
        drug_class
        for drug_class, keywords in DRUG_CLASS_KEYWORDS.items()
        if any(keyword in name for name in names for keyword in keywords)
    )


def identify_drugs(study: StudyRecord) -> frozenset[str]:
    """Return the generic names of a study's known non-placebo drugs.

    Development codes are reported under their generic name, so two
    trials of the same drug match however they name it.
    """
    names = _intervention_names(study)
    return frozenset(
        DRUG_CODE_ALIASES.get(keyword, keyword)
        for keywords in DRUG_CLASS_KEYWORDS.values()
        for keyword in keywords
        if any(keyword in name for name in names)
    )
