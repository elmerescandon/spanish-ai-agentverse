"""Comparison rules as typed data: what counts as a peer, drug classes.

Human-readable version for clinical sign-off:
docs/protocol_comparison_rules.md. Keep the two in step.
"""

from dataclasses import dataclass
from enum import StrEnum


class DrugClass(StrEnum):
    """Glucose-lowering drug classes used to group same-class peers."""

    SGLT2_INHIBITOR = "SGLT2_INHIBITOR"
    GLP1_RECEPTOR_AGONIST = "GLP1_RECEPTOR_AGONIST"
    GIP_GLP1_RECEPTOR_AGONIST = "GIP_GLP1_RECEPTOR_AGONIST"
    DPP4_INHIBITOR = "DPP4_INHIBITOR"
    BIGUANIDE = "BIGUANIDE"
    INSULIN = "INSULIN"
    SULFONYLUREA = "SULFONYLUREA"
    THIAZOLIDINEDIONE = "THIAZOLIDINEDIONE"


# Lower-case words matched against intervention names and the registry's
# intervention MeSH terms. Development codes are included where trials
# name the drug only by code (e.g. dulaglutide as LY2189265).
DRUG_CLASS_KEYWORDS: dict[DrugClass, tuple[str, ...]] = {
    DrugClass.SGLT2_INHIBITOR: (
        "canagliflozin",
        "dapagliflozin",
        "empagliflozin",
        "ertugliflozin",
        "sotagliflozin",
    ),
    DrugClass.GLP1_RECEPTOR_AGONIST: (
        "exenatide",
        "liraglutide",
        "dulaglutide",
        "ly2189265",
        "semaglutide",
        "lixisenatide",
        "albiglutide",
    ),
    DrugClass.GIP_GLP1_RECEPTOR_AGONIST: ("tirzepatide",),
    DrugClass.DPP4_INHIBITOR: (
        "sitagliptin",
        "saxagliptin",
        "alogliptin",
        "linagliptin",
        "vildagliptin",
    ),
    DrugClass.BIGUANIDE: ("metformin",),
    DrugClass.INSULIN: ("insulin",),
    DrugClass.SULFONYLUREA: (
        "glimepiride",
        "glipizide",
        "glyburide",
        "glibenclamide",
        "gliclazide",
    ),
    DrugClass.THIAZOLIDINEDIONE: ("pioglitazone", "rosiglitazone"),
}


@dataclass(frozen=True)
class PeerCriteria:
    """What a registry search result must satisfy to count as a peer.

    The search itself is broad (free-text condition match), so these
    checks run on the registry's normalised fields afterwards.
    """

    required_condition_mesh: str
    excluded_condition_mesh: frozenset[str]
    intervention_types: frozenset[str]
    primary_purpose: str


TYPE_2_DIABETES_PEER_CRITERIA = PeerCriteria(
    required_condition_mesh="Diabetes Mellitus, Type 2",
    # Trials that also list type 1 (e.g. "double diabetes") study a
    # different population, so they are not peers.
    excluded_condition_mesh=frozenset({"Diabetes Mellitus, Type 1"}),
    # Supplements and behavioural programmes are not comparable to a drug
    # trial's eligibility or design.
    intervention_types=frozenset({"DRUG", "BIOLOGICAL"}),
    primary_purpose="TREATMENT",
)
