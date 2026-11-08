"""Code checks for Family M11: ICH M11 template structure and hygiene."""

import re
from collections.abc import Mapping

from backend.agents.completeness.checks.common import (
    absence_fired_outcome,
    cannot_assess_outcome,
    find_heading_citation,
    find_pattern_citation,
    find_pattern_citations,
    fired_outcome,
    passed_outcome,
)
from backend.agents.completeness.checks.consistency import (
    check_xs_12,
    check_xs_15,
)
from backend.agents.completeness.logic import (
    CheckOutcome,
    DeterministicCheck,
    criteria_location,
    verified_criterion_citations,
)
from backend.shared.messages import (
    Citation,
    ProtocolDocument,
    TrialProfile,
)

# M11-03: template residue: <Enter ...> insertion points, [Select ...]
# pick-lists and leftover template instructions.
TEMPLATE_RESIDUE_PATTERN = re.compile(
    r"<\s*(?:enter|insert|specify|select|add)\b[^>\n]{0,80}>"
    r"|\[\s*(?:enter|insert|specify|select|choose|add)\b[^\]\n]{0,80}\]"
    r"|\binstructional\s+text\b|\bdelete\s+(?:this|if\s+not\s+applicable)\b",
    re.IGNORECASE,
)
# M11-05: "subject(s)" for enrolled people; "subject to" is ordinary
# English. "Patient" is left alone: protocols rightly use it for the
# disease population outside the trial.
SUBJECT_TERM_PATTERN = re.compile(r"\b[Ss]ubjects?\b(?!\s+to\b)")
# M11-21: a visit window such as "±3 days", "+/- 2", "(-3/+3)".
VISIT_WINDOW_PATTERN = re.compile(
    r"±\s*\d+|\+\s*/\s*-\s*\d+|\(\s*[-–−]\s*\d+\s*/\s*\+\s*\d+\s*\)"
    r"|\bvisit\s+windows?\b|\bwindow\s+of\s+[±+]?\s*\d+",
    re.IGNORECASE,
)
# M11-35: an age criterion and the moment age is measured.
AGE_CRITERION_PATTERN = re.compile(
    r"\baged?\b|\byears?\s+(?:of\s+age|old)\b", re.IGNORECASE
)
AGE_TIMEPOINT_PATTERN = re.compile(
    r"\b(?:at|on|by)\s+(?:the\s+)?(?:time\s+of\s+)?(?:screening|signing|"
    r"(?:informed\s+)?consent|enrol(?:l)?ment|randomi[sz]ation|visit\s*1)\b",
    re.IGNORECASE,
)
# M11-39: waivers or exceptions to eligibility; IND exemptions and other
# regulatory wording do not count. A negation in the quote means the
# protocol is ruling waivers out, which M11 asks for.
ELIGIBILITY_WAIVER_PATTERN = re.compile(
    r"(?:eligibility|inclusion|exclusion|entry)\s+(?:criteria\s+)?"
    r"(?:waivers?|exemptions?|exceptions?)"
    r"|(?:waivers?|exemptions?|exceptions?)\s+(?:to|from|of)\s+(?:the\s+)?"
    r"(?:eligibility|inclusion|exclusion|entry|protocol)"
    r"|\bprotocol\s+waivers?\b",
    re.IGNORECASE,
)
NEGATION_PATTERN = re.compile(
    r"\b(?:no|not|never|nor|without|prohibited|forbidden)\b|n't",
    re.IGNORECASE,
)
# M11-47: a disclosed randomisation block size such as "blocks of 4".
BLOCK_SIZE_PATTERN = re.compile(
    r"\bblock\s+sizes?\s+(?:of\s+|=\s*|:\s*)?\d+"
    r"|\bblocks?\s+of\s+(?:size\s+)?\d+",
    re.IGNORECASE,
)
# M11-71: required back matter, as a subsection title or a heading line.
APPENDIX_PATTERNS: Mapping[str, tuple[re.Pattern[str], re.Pattern[str]]] = {
    "laboratory appendix": (
        re.compile(r"laborator", re.IGNORECASE),
        re.compile(
            r"^[ \t]*(?:appendix|annex)\b[^\n]{0,40}laborator",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    "regional differences appendix": (
        re.compile(r"regional|country[\s-]specific", re.IGNORECASE),
        re.compile(
            r"^[ \t]*(?:appendix|annex)\b[^\n]{0,40}"
            r"(?:regional|country[\s-]specific)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    "glossary or list of abbreviations": (
        re.compile(r"abbreviation|glossary", re.IGNORECASE),
        re.compile(
            r"^[ \t]*(?:(?:appendix|annex)\b[^\n]{0,40}"
            r"|\d+(?:\.\d+)*\.?[ \t]+)?(?:list\s+of\s+)?"
            r"(?:abbreviations|glossary)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    "references": (
        re.compile(r"\breferences\b", re.IGNORECASE),
        re.compile(
            r"^[ \t]*(?:\d+(?:\.\d+)*\.?[ \t]+)?references[ \t]*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
}


def _offending_text_outcome(
    citations: list[Citation], fired_text: str, passed_text: str
) -> CheckOutcome:
    """Fire citing each offending quote, else pass."""
    if citations:
        return fired_outcome(fired_text, evidence=citations)
    return passed_outcome(passed_text)


def check_m11_03(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """M11-03: No template insertion points or instructions remain."""
    return _offending_text_outcome(
        find_pattern_citations(document, TEMPLATE_RESIDUE_PATTERN),
        "Template placeholders or instructions remain in the protocol.",
        "No template placeholders or instructions remain.",
    )


def check_m11_05(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """M11-05: Enrolled people are 'participants', not 'subjects'."""
    return _offending_text_outcome(
        find_pattern_citations(document, SUBJECT_TERM_PATTERN),
        "The protocol calls enrolled people 'subjects' instead of "
        "'participants'.",
        "The protocol does not call enrolled people 'subjects'.",
    )


def check_m11_21(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """M11-21: The schedule of activities gives visit windows."""
    citation = find_pattern_citation(document, VISIT_WINDOW_PATTERN)
    if citation is None:
        return absence_fired_outcome(
            "No visit windows (such as ±3 days) were found."
        )
    return passed_outcome("Visit windows are given.", evidence=[citation])


def check_m11_35(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """M11-35: The age criterion says when age is assessed."""
    if document.eligibility_criteria is None:
        return cannot_assess_outcome("ELIGIBILITY facet did not run.")
    age_criteria = [
        c
        for c in document.eligibility_criteria
        if AGE_CRITERION_PATTERN.search(c.text) is not None
    ]
    if not age_criteria:
        return cannot_assess_outcome("No age criterion was extracted.")
    timed = [
        c
        for c in age_criteria
        if AGE_TIMEPOINT_PATTERN.search(c.text) is not None
    ]
    if timed:
        return passed_outcome(
            "The age criterion states when age is assessed.",
            evidence=verified_criterion_citations(timed),
            location=criteria_location(timed),
        )
    return fired_outcome(
        "The age criterion does not say when age is assessed (for "
        "example at screening).",
        evidence=verified_criterion_citations(age_criteria),
        location=criteria_location(age_criteria),
    )


def check_m11_39(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """M11-39: The protocol does not allow eligibility waivers."""
    allowing = [
        citation
        for citation in find_pattern_citations(
            document, ELIGIBILITY_WAIVER_PATTERN
        )
        if NEGATION_PATTERN.search(citation.quote) is None
    ]
    return _offending_text_outcome(
        allowing,
        "The protocol allows waivers or exceptions to eligibility, which "
        "M11 forbids.",
        "The protocol does not allow eligibility waivers.",
    )


def check_m11_47(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """M11-47: The randomisation block size is not disclosed."""
    return _offending_text_outcome(
        find_pattern_citations(document, BLOCK_SIZE_PATTERN),
        "The protocol discloses the randomisation block size.",
        "The randomisation block size is not disclosed.",
    )


def check_m11_71(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """M11-71: Lab, regional, glossary and reference back matter exist."""
    found: dict[str, Citation] = {}
    for name, (title_pattern, line_pattern) in APPENDIX_PATTERNS.items():
        citation = find_heading_citation(document, title_pattern, line_pattern)
        if citation is not None:
            found[name] = citation
    missing = [name for name in APPENDIX_PATTERNS if name not in found]
    if missing:
        return fired_outcome(
            f"Missing back matter: {', '.join(missing)}.",
            evidence=found.values(),
            needs_second_opinion=True,
        )
    return passed_outcome(
        "Laboratory, regional, glossary and reference sections exist.",
        evidence=found.values(),
    )


STRUCTURE_CHECKS: Mapping[str, DeterministicCheck] = {
    "M11-03": check_m11_03,
    "M11-05": check_m11_05,
    "M11-21": check_m11_21,
    "M11-35": check_m11_35,
    "M11-39": check_m11_39,
    "M11-47": check_m11_47,
    "M11-58": check_xs_15,  # same retention comparison as XS-15
    "M11-67": check_xs_12,  # same committee comparison as XS-12
    "M11-71": check_m11_71,
}
