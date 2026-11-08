"""Pure comparison logic: peer search, screening, drug classes. No I/O."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from backend.agents.protocol_comparison.rules import (
    DRUG_CLASS_KEYWORDS,
    DRUG_CODE_ALIASES,
    DrugClass,
    PeerCriteria,
)
from backend.clients.clinicaltrials_gov import (
    PeerSearchQuery,
    Phase,
    Population,
    StudyRecord,
)
from backend.shared.messages import ProtocolDocument, TrialPhase

PLACEBO_WORD = "placebo"
# The product reviews type 2 diabetes protocols, and the parser does not
# extract a condition, so every search is for this registry condition.
PEER_CONDITION = "Diabetes Mellitus, Type 2"
PEER_LOOKBACK_YEARS = 10  # peers started at most this long before review
ADULT_AGE_YEARS = 18.0
# Registry phases searched for each parsed phase; a combined phase
# searches both of its phases.
REGISTRY_PHASES: dict[TrialPhase, tuple[Phase, ...]] = {
    TrialPhase.EARLY_PHASE1: (Phase.EARLY_PHASE1,),
    TrialPhase.PHASE1: (Phase.PHASE1,),
    TrialPhase.PHASE1_PHASE2: (Phase.PHASE1, Phase.PHASE2),
    TrialPhase.PHASE2: (Phase.PHASE2,),
    TrialPhase.PHASE2_PHASE3: (Phase.PHASE2, Phase.PHASE3),
    TrialPhase.PHASE3: (Phase.PHASE3,),
    TrialPhase.PHASE4: (Phase.PHASE4,),
    TrialPhase.NOT_APPLICABLE: (Phase.NOT_APPLICABLE,),
}
# Searched when the parser found no phase: the efficacy phases most
# diabetes drug protocols are written for.
UNKNOWN_PHASE_REGISTRY_PHASES = (Phase.PHASE2, Phase.PHASE3)


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
        and not is_placebo(intervention.name)
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
            if not is_placebo(intervention.name)
        )
    derived = study.derived_section
    if derived is not None and derived.intervention_browse_module is not None:
        names.extend(
            mesh.term.lower()
            for mesh in derived.intervention_browse_module.meshes
        )
    return names


def classify_drug_names(names: Sequence[str]) -> frozenset[DrugClass]:
    """Return the drug classes named in lower-case intervention names.

    Matches generic names (and known development codes). An unknown drug
    gives no class.
    """
    return frozenset(
        drug_class
        for drug_class, keywords in DRUG_CLASS_KEYWORDS.items()
        if any(keyword in name for name in names for keyword in keywords)
    )


def identify_drug_names(names: Sequence[str]) -> frozenset[str]:
    """Return the generic names of known drugs in lower-case names.

    Development codes are reported under their generic name, so two
    trials of the same drug match however they name it.
    """
    return frozenset(
        DRUG_CODE_ALIASES.get(keyword, keyword)
        for keywords in DRUG_CLASS_KEYWORDS.values()
        for keyword in keywords
        if any(keyword in name for name in names)
    )


def is_placebo(intervention_name: str) -> bool:
    return PLACEBO_WORD in intervention_name.lower()


def classify_drug_classes(study: StudyRecord) -> frozenset[DrugClass]:
    """Return the drug classes of a study's non-placebo interventions,
    read from intervention names and intervention MeSH terms."""
    return classify_drug_names(_intervention_names(study))


def identify_drugs(study: StudyRecord) -> frozenset[str]:
    """Return the generic names of a study's known non-placebo drugs."""
    return identify_drug_names(_intervention_names(study))


def protocol_nct_id(document: ProtocolDocument) -> str | None:
    """The NCT ID the protocol states about itself, if any."""
    design = document.design
    return design.nct_id.value if design and design.nct_id else None


def peer_population(document: ProtocolDocument) -> Population:
    """Pediatric when the protocol enrolls only children and teenagers.

    That is a minimum age under 18 and a maximum age of at most 18;
    anything else, including missing ages, searches adult trials.
    """
    design = document.design
    if design is None or design.min_age_years is None:
        return Population.ADULT
    if design.max_age_years is None:
        return Population.ADULT
    is_pediatric = (
        design.min_age_years.value < ADULT_AGE_YEARS
        and design.max_age_years.value <= ADULT_AGE_YEARS
    )
    return Population.PEDIATRIC if is_pediatric else Population.ADULT


def peer_query_for(
    document: ProtocolDocument, review_date: date
) -> PeerSearchQuery:
    """The registry search for the protocol's peers, from its parsed values.

    Same phase and population as the protocol, started in the
    PEER_LOOKBACK_YEARS calendar years before the review, never the
    protocol's own record. The window starts on 1 January, so the search
    (and its cache entry) only changes once a year.
    """
    design = document.design
    parsed_phase = design.phase.value if design and design.phase else None
    phases = (
        UNKNOWN_PHASE_REGISTRY_PHASES
        if parsed_phase is None
        else REGISTRY_PHASES.get(parsed_phase, UNKNOWN_PHASE_REGISTRY_PHASES)
    )
    own_nct_id = protocol_nct_id(document)
    return PeerSearchQuery(
        condition=PEER_CONDITION,
        phases=phases,
        population=peer_population(document),
        started_on_or_after=date(review_date.year - PEER_LOOKBACK_YEARS, 1, 1),
        exclude_nct_ids=(
            frozenset({own_nct_id}) if own_nct_id else frozenset()
        ),
    )
