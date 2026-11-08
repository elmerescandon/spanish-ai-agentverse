"""Deterministic checks for Family REG (outcome-measure registration)."""

import re
from collections.abc import Mapping

from backend.agents.completeness.checks.common import (
    absence_fired_outcome,
    cannot_assess_outcome,
    extract_all_timepoints_weeks,
    fired_outcome,
    format_offenders,
    location_for_page,
    not_applicable_outcome,
    parse_duration_to_weeks,
    passed_outcome,
)
from backend.agents.completeness.logic import CheckOutcome, DeterministicCheck
from backend.shared.messages import (
    Citation,
    Endpoint,
    EndpointKind,
    M11Heading,
    ProtocolDocument,
    TrialProfile,
)

# REG-25: Matches two or more distinct clinical or laboratory metrics bundled
# with "and", "&", or "/" inside one endpoint description (e.g. "HbA1c and FPG"
# or "systolic and diastolic blood pressure").
BUNDLED_VARIABLES_PATTERN = re.compile(
    r"(?:\b(?:hba1c|a1c|glycated hemoglobin)\b.*\b(?:and|&|/)\b.*"
    r"\b(?:fpg|fasting plasma glucose|body weight|bmi|lipids|insulin|"
    r"c-peptide|blood pressure)\b)"
    r"|(?:\bsystolic\s+(?:and|&|/)\s+diastolic\s+blood\s+pressure\b)"
    r"|(?:\b(?:ldl|hdl|triglycerides)\s+(?:and|&|/)\s+"
    r"(?:ldl|hdl|triglycerides|cholesterol)\b)",
    re.IGNORECASE,
)

# REG-26: Matches non-neutral directional wording in an endpoint title or
# description (such as "reduction in", "improvement in", "decrease in").
DIRECTIONAL_OUTCOME_PATTERN = re.compile(
    r"\b(?P<term>improvement|reduction|decrease|increase|lowering|"
    r"amelioration|worsening|benefit)s?\s+(?:in|of|from)\b",
    re.IGNORECASE,
)

# REG-28: Matches change-from-baseline endpoints and baseline mentions.
CHANGE_ENDPOINT_PATTERN = re.compile(r"\bchange\b", re.IGNORECASE)
BASELINE_MENTION_PATTERN = re.compile(r"\bbaseline\b", re.IGNORECASE)

# REG-29: Matches rating scales, questionnaires, or patient-reported score
# instruments in an endpoint description.
SCALE_ENDPOINT_PATTERN = re.compile(
    r"\b(?:scale|score|questionnaire|index|inventory|survey|"
    r"dtsq|sf-36|eq-5d|dds|phq-9|paid)\b",
    re.IGNORECASE,
)


def check_reg_24(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """REG-24: Primary outcome must state a metric and time frame."""
    if document.endpoints is None:
        return cannot_assess_outcome("ENDPOINTS facet did not run.")
    primary = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.PRIMARY
    ]
    if not primary:
        return absence_fired_outcome(
            "No primary outcome measure is defined in the protocol."
        )
    offenders: list[str] = []
    citations: list[Citation] = []
    for ep in primary:
        if not ep.description.strip():
            offenders.append(
                "primary endpoint with empty measurement description"
            )
            citations.append(ep.citation)
        elif ep.time_frame is None or not ep.time_frame.strip():
            offenders.append(f"'{ep.description}' (omits time frame)")
            citations.append(ep.citation)
    if offenders:
        return fired_outcome(
            f"Primary endpoint(s) incomplete: {format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document,
                citations[0].page_number,
                M11Heading.OBJECTIVES_AND_ESTIMANDS,
            ),
            needs_second_opinion=True,
        )
    first = primary[0]
    return passed_outcome(
        f"Primary endpoint '{first.description}' specifies time frame "
        f"'{first.time_frame}'.",
        evidence=[first.citation],
        location=location_for_page(
            document,
            first.citation.page_number,
            M11Heading.OBJECTIVES_AND_ESTIMANDS,
        ),
    )


def check_reg_25(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """REG-25: Single outcome entry must not bundle multiple variables."""
    if document.endpoints is None:
        return cannot_assess_outcome("ENDPOINTS facet did not run.")
    if not document.endpoints:
        return cannot_assess_outcome("No endpoints extracted to evaluate.")
    offenders: list[str] = []
    citations: list[Citation] = []
    for ep in document.endpoints:
        if BUNDLED_VARIABLES_PATTERN.search(ep.description):
            offenders.append(f"'{ep.description}'")
            citations.append(ep.citation)
    if offenders:
        return fired_outcome(
            f"Endpoint(s) bundle multiple variables or units into a single "
            f"outcome entry: {format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document,
                citations[0].page_number,
                M11Heading.OBJECTIVES_AND_ESTIMANDS,
            ),
        )
    first = document.endpoints[0]
    return passed_outcome(
        "Each extracted endpoint defines a single clinical variable.",
        evidence=[first.citation],
        location=location_for_page(
            document,
            first.citation.page_number,
            M11Heading.OBJECTIVES_AND_ESTIMANDS,
        ),
    )


def check_reg_26(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """REG-26: Outcome title must use neutral rather than directional terms."""
    if document.endpoints is None:
        return cannot_assess_outcome("ENDPOINTS facet did not run.")
    if not document.endpoints:
        return cannot_assess_outcome("No endpoints extracted to evaluate.")
    offenders: list[str] = []
    citations: list[Citation] = []
    for ep in document.endpoints:
        match = DIRECTIONAL_OUTCOME_PATTERN.search(ep.description)
        if match is not None:
            term = match.group("term")
            offenders.append(f"'{ep.description}' (uses '{term}')")
            citations.append(ep.citation)
    if offenders:
        return fired_outcome(
            f"Endpoint(s) use directional wording instead of neutral "
            f"wording: {format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document,
                citations[0].page_number,
                M11Heading.OBJECTIVES_AND_ESTIMANDS,
            ),
        )
    first = document.endpoints[0]
    return passed_outcome(
        "All extracted endpoints use neutral outcome wording.",
        evidence=[first.citation],
        location=location_for_page(
            document,
            first.citation.page_number,
            M11Heading.OBJECTIVES_AND_ESTIMANDS,
        ),
    )


def check_reg_27(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """REG-27: Outcome assessment time frame must not be vague."""
    if document.endpoints is None:
        return cannot_assess_outcome("ENDPOINTS facet did not run.")
    with_tf = [
        ep
        for ep in document.endpoints
        if ep.time_frame is not None and ep.time_frame.strip()
    ]
    if not with_tf:
        return cannot_assess_outcome(
            "No endpoints with a stated time frame to check."
        )
    offenders: list[str] = []
    citations: list[Citation] = []
    for ep in with_tf:
        assert ep.time_frame is not None
        weeks = parse_duration_to_weeks(ep.time_frame)
        if weeks is None:
            offenders.append(
                f"'{ep.description}' (time_frame='{ep.time_frame}')"
            )
            citations.append(ep.citation)
    if offenders:
        return fired_outcome(
            f"Endpoint(s) have vague time frames without a concrete "
            f"timepoint: {format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document,
                citations[0].page_number,
                M11Heading.OBJECTIVES_AND_ESTIMANDS,
            ),
        )
    first = with_tf[0]
    return passed_outcome(
        f"Endpoint time frames state concrete timepoints (e.g. "
        f"'{first.time_frame}').",
        evidence=[first.citation],
        location=location_for_page(
            document,
            first.citation.page_number,
            M11Heading.OBJECTIVES_AND_ESTIMANDS,
        ),
    )


def check_reg_28(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """REG-28: Change outcome must state baseline and one post timepoint."""
    if document.endpoints is None:
        return cannot_assess_outcome("ENDPOINTS facet did not run.")
    change_eps = [
        ep
        for ep in document.endpoints
        if CHANGE_ENDPOINT_PATTERN.search(ep.description)
    ]
    if not change_eps:
        return not_applicable_outcome(
            "No change-from-baseline endpoints are defined."
        )
    offenders: list[str] = []
    citations: list[Citation] = []
    for ep in change_eps:
        combined = f"{ep.description} {ep.time_frame or ''}"
        if not BASELINE_MENTION_PATTERN.search(combined):
            offenders.append(
                f"'{ep.description}' (omits baseline reference point)"
            )
            citations.append(ep.citation)
            continue
        timepoints = extract_all_timepoints_weeks(combined)
        if not timepoints:
            offenders.append(
                f"'{ep.description}' (omits concrete post-baseline timepoint)"
            )
            citations.append(ep.citation)
        elif len(timepoints) > 1:
            offenders.append(
                f"'{ep.description}' (bundles {timepoints} weeks in "
                f"'{ep.time_frame}')"
            )
            citations.append(ep.citation)
    if offenders:
        return fired_outcome(
            f"Change endpoint(s) violate single baseline-to-target "
            f"timepoint rule: {format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document,
                citations[0].page_number,
                M11Heading.OBJECTIVES_AND_ESTIMANDS,
            ),
        )
    first = change_eps[0]
    return passed_outcome(
        f"Change endpoint '{first.description}' states baseline and one "
        f"post-baseline timepoint ('{first.time_frame}').",
        evidence=[first.citation],
        location=location_for_page(
            document,
            first.citation.page_number,
            M11Heading.OBJECTIVES_AND_ESTIMANDS,
        ),
    )


def _is_scale_endpoint(endpoint: Endpoint) -> bool:
    return (
        endpoint.scale_name is not None
        or endpoint.scale_min is not None
        or endpoint.scale_max is not None
        or endpoint.scale_better_direction is not None
        or SCALE_ENDPOINT_PATTERN.search(endpoint.description) is not None
    )


def check_reg_29(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """REG-29: Scale outcome must state scale name, range, and direction."""
    if document.endpoints is None:
        return cannot_assess_outcome("ENDPOINTS facet did not run.")
    scale_eps = [ep for ep in document.endpoints if _is_scale_endpoint(ep)]
    if not scale_eps:
        return not_applicable_outcome(
            "No rating-scale or questionnaire endpoints are present."
        )
    offenders: list[str] = []
    citations: list[Citation] = []
    for ep in scale_eps:
        missing: list[str] = []
        if ep.scale_name is None:
            missing.append("scale_name")
        if ep.scale_min is None:
            missing.append("scale_min")
        if ep.scale_max is None:
            missing.append("scale_max")
        if ep.scale_better_direction is None:
            missing.append("scale_better_direction")
        if missing:
            offenders.append(
                f"'{ep.description}' (omits {', '.join(missing)})"
            )
            citations.append(ep.citation)
    if offenders:
        return fired_outcome(
            f"Scale endpoint(s) incomplete: {format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document,
                citations[0].page_number,
                M11Heading.OBJECTIVES_AND_ESTIMANDS,
            ),
            needs_second_opinion=True,
        )
    first = scale_eps[0]
    assert first.scale_name is not None
    assert first.scale_min is not None
    assert first.scale_max is not None
    assert first.scale_better_direction is not None
    return passed_outcome(
        f"Scale endpoint '{first.description}' specifies scale "
        f"'{first.scale_name.value}' ({first.scale_min.value} to "
        f"{first.scale_max.value}, better="
        f"{first.scale_better_direction.value}).",
        evidence=[first.citation],
        location=location_for_page(
            document,
            first.citation.page_number,
            M11Heading.OBJECTIVES_AND_ESTIMANDS,
        ),
    )


REGISTRATION_CHECKS: Mapping[str, DeterministicCheck] = {
    "REG-24": check_reg_24,
    "REG-25": check_reg_25,
    "REG-26": check_reg_26,
    "REG-27": check_reg_27,
    "REG-28": check_reg_28,
    "REG-29": check_reg_29,
}
