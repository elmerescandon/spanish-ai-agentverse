"""Code checks for Family ELQ: can a site apply each eligibility criterion.

Each check reads the extracted criteria one by one and reports offending
criteria by ID in the finding location.
"""

import re
from collections.abc import Callable, Mapping

from backend.agents.completeness.checks.common import (
    HBA1C_PATTERN,
    cannot_assess_outcome,
    find_pattern_citation,
    fired_outcome,
    format_offenders,
    passed_outcome,
)
from backend.agents.completeness.logic import (
    CheckOutcome,
    DeterministicCheck,
    criteria_location,
    verified_criterion_citations,
)
from backend.shared.messages import (
    CriterionKind,
    EligibilityCriterion,
    M11Heading,
    ProtocolDocument,
    TrialProfile,
)

# ELQ-01: wording that makes a criterion a judgement call unless a number
# (threshold, class or score) pins it down.
VAGUE_TERM_PATTERN = re.compile(
    r"\b(?:poorly\s+controlled|uncontrolled|clinically\s+(?:significant|"
    r"relevant)|significant)\b",
    re.IGNORECASE,
)
DIGIT_PATTERN = re.compile(r"\d")
# ELQ-03: a medical history clause and the look-back windows that bound it.
HISTORY_PATTERN = re.compile(r"\bhistory\s+of\b", re.IGNORECASE)
LOOK_BACK_WINDOW_PATTERN = re.compile(
    r"\b(?:within|ever|at\s+any\s+time|lifetime|prior\s+to|before|since|"
    r"in\s+the\s+(?:past|last|previous)|during\s+the\s+(?:past|last))\b"
    r"|\b\d+\s*(?:days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)
# ELQ-09: HbA1c given in percent needs the IFCC unit alongside; eGFR needs
# the estimating equation named.
PERCENT_PATTERN = re.compile(r"%")
MMOL_PER_MOL_PATTERN = re.compile(r"mmol\s*/\s*mol", re.IGNORECASE)
EGFR_PATTERN = re.compile(r"\begfr\b|\bestimated\s+glomerular", re.IGNORECASE)
EGFR_FORMULA_PATTERN = re.compile(
    r"ckd[\s-]?epi|\bmdrd\b|cockcroft", re.IGNORECASE
)
# ELQ-17: a language or literacy requirement, and a translation plan.
LANGUAGE_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:read|speak|write|understand)\w*\b[^.;]{0,40}?"
    r"\b(?:english|language)\b|\bfluen(?:t|cy)\b|\bliterate\b",
    re.IGNORECASE,
)
TRANSLATION_PLAN_PATTERN = re.compile(
    r"\btranslat\w*|\binterpret(?:er|ers|ation)\b", re.IGNORECASE
)
MAX_EXCLUSION_CRITERIA = 25  # above this, screen failure and amendments rise


def _flag_criteria(
    document: ProtocolDocument,
    is_offender: Callable[[EligibilityCriterion], bool],
    fired_text: str,
    passed_text: str,
) -> CheckOutcome:
    """Fire on every criterion is_offender selects, else pass."""
    if document.eligibility_criteria is None:
        return cannot_assess_outcome("ELIGIBILITY facet did not run.")
    offenders = [c for c in document.eligibility_criteria if is_offender(c)]
    if not offenders:
        return passed_outcome(passed_text)
    described = format_offenders(
        [f"{c.criterion_id} '{c.text}'" for c in offenders]
    )
    return fired_outcome(
        f"{fired_text}: {described}.",
        evidence=verified_criterion_citations(offenders),
        location=criteria_location(offenders),
    )


def _is_vague(criterion: EligibilityCriterion) -> bool:
    return (
        VAGUE_TERM_PATTERN.search(criterion.text) is not None
        and DIGIT_PATTERN.search(criterion.text) is None
    )


def check_elq_01(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """ELQ-01: A criterion uses a vague term with no number to anchor it."""
    return _flag_criteria(
        document,
        _is_vague,
        "Criteria use a vague term with no threshold",
        "Every criterion is stated without unanchored vague terms.",
    )


def _lacks_look_back_window(criterion: EligibilityCriterion) -> bool:
    return (
        HISTORY_PATTERN.search(criterion.text) is not None
        and LOOK_BACK_WINDOW_PATTERN.search(criterion.text) is None
    )


def check_elq_03(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """ELQ-03: A 'history of' criterion gives no look-back window."""
    return _flag_criteria(
        document,
        _lacks_look_back_window,
        "History criteria have no look-back window",
        "Every history criterion states its look-back window.",
    )


def check_elq_09(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """ELQ-09: HbA1c in % without mmol/mol, or eGFR without its formula.

    An eGFR formula named anywhere in the population section counts for
    every eGFR criterion.
    """
    formula_stated = (
        find_pattern_citation(
            document, EGFR_FORMULA_PATTERN, (M11Heading.TRIAL_POPULATION,)
        )
        is not None
    )

    def has_unit_gap(criterion: EligibilityCriterion) -> bool:
        text = criterion.text
        percent_only_hba1c = (
            HBA1C_PATTERN.search(text) is not None
            and PERCENT_PATTERN.search(text) is not None
            and MMOL_PER_MOL_PATTERN.search(text) is None
        )
        egfr_without_formula = (
            EGFR_PATTERN.search(text) is not None
            and EGFR_FORMULA_PATTERN.search(text) is None
            and not formula_stated
        )
        return percent_only_hba1c or egfr_without_formula

    return _flag_criteria(
        document,
        has_unit_gap,
        "Criteria give HbA1c only in % or eGFR without its formula",
        "HbA1c and eGFR criteria state both units and the eGFR formula.",
    )


def check_elq_17(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """ELQ-17: A language requirement with no translation plan."""
    if document.eligibility_criteria is None:
        return cannot_assess_outcome("ELIGIBILITY facet did not run.")
    language_criteria = [
        c
        for c in document.eligibility_criteria
        if LANGUAGE_REQUIREMENT_PATTERN.search(c.text) is not None
    ]
    if not language_criteria:
        return passed_outcome("No criterion requires a language or literacy.")
    plan = find_pattern_citation(
        document,
        TRANSLATION_PLAN_PATTERN,
        (M11Heading.TRIAL_POPULATION, M11Heading.REGULATORY_AND_ETHICAL),
    )
    if plan is not None:
        return passed_outcome(
            "A language requirement is paired with a translation plan.",
            evidence=[plan, *verified_criterion_citations(language_criteria)],
            location=criteria_location(language_criteria),
        )
    return fired_outcome(
        "A language requirement excludes non-fluent participants and no "
        "translated materials or interpreters are mentioned.",
        evidence=verified_criterion_citations(language_criteria),
        location=criteria_location(language_criteria),
        needs_second_opinion=True,
    )


def check_elq_21(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """ELQ-21: More than 25 exclusion criteria."""
    if document.eligibility_criteria is None:
        return cannot_assess_outcome("ELIGIBILITY facet did not run.")
    exclusions = [
        c
        for c in document.eligibility_criteria
        if c.kind == CriterionKind.EXCLUSION
    ]
    exclusion_count = len(exclusions)
    if exclusion_count > MAX_EXCLUSION_CRITERIA:
        last = exclusions[-1:]
        return fired_outcome(
            f"The protocol lists {exclusion_count} exclusion criteria, more "
            f"than {MAX_EXCLUSION_CRITERIA}.",
            evidence=verified_criterion_citations(last),
            location=criteria_location(last),
        )
    return passed_outcome(
        f"The protocol lists {exclusion_count} exclusion criteria, within "
        f"{MAX_EXCLUSION_CRITERIA}."
    )


ELIGIBILITY_CHECKS: Mapping[str, DeterministicCheck] = {
    "ELQ-01": check_elq_01,
    "ELQ-03": check_elq_03,
    "ELQ-09": check_elq_09,
    "ELQ-17": check_elq_17,
    "ELQ-21": check_elq_21,
}
