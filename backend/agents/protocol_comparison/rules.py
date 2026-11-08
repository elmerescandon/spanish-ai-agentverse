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


@dataclass(frozen=True)
class FlagRules:
    """When a draft's value counts as unusual against its peers.

    Proposed thresholds, pending clinical sign-off; see section 3 of
    docs/protocol_comparison_rules.md.
    """

    # Below this many peers stating a value, no flag is raised at all.
    min_peers: int = 10
    # A recent or same-class group needs this many peers stating a value
    # before "stricter than every peer in it" means anything.
    min_group_peers: int = 3
    # Peers that started this many years before the protocol are recent.
    recent_window_years: int = 3
    low_percentile: int = 10
    high_percentile: int = 90

    def __post_init__(self) -> None:
        # A percentile range needs at least two values to interpolate.
        if self.min_peers < 2:
            raise ValueError(
                f"min_peers must be at least 2, got {self.min_peers}"
            )
        if not 0 < self.low_percentile < self.high_percentile < 100:
            raise ValueError(
                "percentiles must satisfy 0 < low < high < 100, got "
                f"low={self.low_percentile} high={self.high_percentile}"
            )


DEFAULT_FLAG_RULES = FlagRules()
