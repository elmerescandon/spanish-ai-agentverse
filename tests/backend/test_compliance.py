"""Tests for compliance report API schemas, fixture and mappers."""

from pathlib import Path

from backend.api.compliance import (
    FAMILY_LABELS,
    finding_to_recommendation,
    to_compliance_report_response,
    to_recommendations,
)
from backend.api.schemas import (
    ComplianceReportResponse,
    FamilySummary,
    FindingView,
    PipelineStep,
    RecommendationStatus,
    Severity,
    StatusCounts,
)
from backend.shared.messages import (
    CheckMethod,
    Citation,
    ComplianceReport,
    FindingLocation,
    GateResult,
    GateStatus,
    M11Heading,
    RuleFamily,
    RuleFinding,
    RuleSeverity,
    RuleStatus,
    RunResult,
    SearchedLocation,
    SourceTier,
    TrialProfile,
)

EXAMPLE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "compliance_report_example.json"
)
SAMPLE_PROTOCOL_ID = "NCT04828785"
SAMPLE_PROTOCOL_TITLE = "Food is Medicine Trial"
SAMPLE_PROTOCOL_VERSION = "1.41, 25 July 2023"
MAX_TOP_FINDINGS_COUNT = 15


def _make_finding(
    rule_id: str,
    family: RuleFamily,
    severity: RuleSeverity = RuleSeverity.S1,
    status: RuleStatus = RuleStatus.FIRED,
    confidence: float = 1.0,
    requires_medical_review: bool = False,
) -> RuleFinding:
    status_reason = (
        None
        if status in (RuleStatus.FIRED, RuleStatus.PASSED)
        else f"Non-scored status: {status}"
    )
    return RuleFinding(
        rule_id=rule_id,
        family=family,
        severity=severity,
        status=status,
        status_reason=status_reason,
        title=f"Title for {rule_id}",
        finding=f"Detailed explanation for {rule_id}.",
        location=FindingLocation(
            section="3.1.1",
            heading=M11Heading.OBJECTIVES_AND_ESTIMANDS,
            page=12,
        ),
        evidence=[
            Citation(
                page_number=12,
                quote="Change in HbA1c from baseline to Month 6.",
                is_verified=True,
            )
        ],
        searched_locations=[
            SearchedLocation(
                heading=M11Heading.OBJECTIVES_AND_ESTIMANDS,
                section_title="3. Objectives and Estimands",
                start_page=11,
                end_page=13,
            )
        ],
        proposed_fix=(
            f"Proposed fix for {rule_id}"
            if status == RuleStatus.FIRED
            else None
        ),
        requires_medical_review=requires_medical_review,
        confidence=confidence,
        source="ICH M11 Template, Step 4",
        source_tier=SourceTier.ICH,
        check_method=CheckMethod.DETERMINISTIC,
    )


def _make_report(findings: list[RuleFinding]) -> ComplianceReport:
    return ComplianceReport(
        protocol_id=SAMPLE_PROTOCOL_ID,
        protocol_title=SAMPLE_PROTOCOL_TITLE,
        protocol_version=SAMPLE_PROTOCOL_VERSION,
        trial_profile=TrialProfile(),
        rules_evaluated=len(findings),
        comparators_used=0,
        before=RunResult(
            score=62.5,
            registration_gate=GateResult(
                status=GateStatus.FAIL,
                is_partial=True,
                failing_rule_ids=["REG-27"],
            ),
            review_gate=GateResult(
                status=GateStatus.FAIL,
                is_partial=False,
                failing_rule_ids=["EST-04", "XS-05"],
            ),
        ),
        findings=findings,
    )


def _build_illustrative_example_report() -> ComplianceReport:
    """Build the 5-finding illustrative ComplianceReport (one per status)."""
    findings = [
        RuleFinding(
            rule_id="REG-27",
            family=RuleFamily.REG,
            severity=RuleSeverity.S1,
            status=RuleStatus.FIRED,
            status_reason=None,
            title="Outcome time frame is vague",
            finding=(
                "Time frame is not a specific time point measured from "
                "baseline."
            ),
            location=FindingLocation(
                section="1.1",
                heading=M11Heading.PROTOCOL_SUMMARY,
                page=10,
            ),
            evidence=[
                Citation(
                    page_number=10,
                    quote=(
                        "at the end of treatment (6 months, primary analysis)"
                    ),
                    is_verified=True,
                )
            ],
            searched_locations=[],
            proposed_fix="Change from baseline in HbA1c at Month 6",
            requires_medical_review=False,
            confidence=1.0,
            source="ClinicalTrials.gov PRS Quality Control Review Criteria",
            source_tier=SourceTier.REGISTRY_QC,
            check_method=CheckMethod.DETERMINISTIC,
        ),
        RuleFinding(
            rule_id="EST-01",
            family=RuleFamily.EST,
            severity=RuleSeverity.S1,
            status=RuleStatus.PASSED,
            status_reason=None,
            title="Primary objective stated as treatment effect",
            finding=(
                "Primary objective clearly states the treatment effect on "
                "glycemic control."
            ),
            location=FindingLocation(
                section="3.1",
                heading=M11Heading.OBJECTIVES_AND_ESTIMANDS,
                page=12,
            ),
            evidence=[
                Citation(
                    page_number=12,
                    quote=(
                        "evaluate the effect of the produce prescription "
                        "program on HbA1c compared with usual care"
                    ),
                    is_verified=True,
                )
            ],
            searched_locations=[],
            proposed_fix=None,
            requires_medical_review=False,
            confidence=0.95,
            source="ICH E9(R1) Estimands and Sensitivity Analysis",
            source_tier=SourceTier.ICH,
            check_method=CheckMethod.JUDGEMENT,
        ),
        RuleFinding(
            rule_id="DM-43",
            family=RuleFamily.DM,
            severity=RuleSeverity.S1,
            status=RuleStatus.NOT_APPLICABLE,
            status_reason=(
                "Trial population is adult Type 2 diabetes, not Type 1 "
                "diabetes."
            ),
            title=(
                "Non-insulin adjunct in Type 1 diabetes run-in and extension"
            ),
            finding="Rule applies only to Type 1 diabetes trials.",
            location=FindingLocation(section=None, heading=None, page=None),
            evidence=[],
            searched_locations=[],
            proposed_fix=None,
            requires_medical_review=False,
            confidence=1.0,
            source="EMA CPMP/EWP/1080/00 Rev. 2",
            source_tier=SourceTier.FINAL_GUIDANCE,
            check_method=CheckMethod.DETERMINISTIC,
        ),
        RuleFinding(
            rule_id="EST-23",
            family=RuleFamily.EST,
            severity=RuleSeverity.S2,
            status=RuleStatus.INSUFFICIENT_COMPARATORS,
            status_reason=(
                "Comparator corpus was not supplied for this completeness run."
            ),
            title="Sample-size effect size and SD grounded in prior trials",
            finding=(
                "Comparator benchmark requires at least 5 comparable prior "
                "protocols."
            ),
            location=FindingLocation(
                section="9.2",
                heading=M11Heading.STATISTICAL_CONSIDERATIONS,
                page=25,
            ),
            evidence=[],
            searched_locations=[],
            proposed_fix=None,
            requires_medical_review=False,
            confidence=1.0,
            source="ICH M11 Template, Step 4",
            source_tier=SourceTier.COMPARATOR_NORM,
            check_method=CheckMethod.DETERMINISTIC,
        ),
        RuleFinding(
            rule_id="XS-17",
            family=RuleFamily.XS,
            severity=RuleSeverity.S1,
            status=RuleStatus.CANNOT_ASSESS,
            status_reason=(
                "Investigator's Brochure was not provided to verify drug "
                "half-life."
            ),
            title=(
                "Contraception duration covers at least 5 half-lives after "
                "last dose"
            ),
            finding=(
                "Cannot compare contraception follow-up window against IB "
                "half-life."
            ),
            location=FindingLocation(
                section="5.4",
                heading=M11Heading.TRIAL_POPULATION,
                page=16,
            ),
            evidence=[],
            searched_locations=[
                SearchedLocation(
                    heading=M11Heading.TRIAL_POPULATION,
                    section_title="5. Eligibility Criteria",
                    start_page=14,
                    end_page=17,
                )
            ],
            proposed_fix=None,
            requires_medical_review=False,
            confidence=1.0,
            source="Investigator's Brochure and ICH M11 §5.4",
            source_tier=SourceTier.PRODUCT_EVIDENCE,
            check_method=CheckMethod.DETERMINISTIC,
        ),
    ]
    return ComplianceReport(
        protocol_id=SAMPLE_PROTOCOL_ID,
        protocol_title=(
            "Food is Medicine: A Randomized Clinical Trial of Produce "
            "Prescriptions for Type 2 Diabetes (Illustrative Example)"
        ),
        protocol_version=SAMPLE_PROTOCOL_VERSION,
        trial_profile=TrialProfile(),
        rules_evaluated=len(findings),
        comparators_used=0,
        before=RunResult(
            score=50.0,
            registration_gate=GateResult(
                status=GateStatus.FAIL,
                is_partial=True,
                failing_rule_ids=["REG-27"],
            ),
            review_gate=GateResult(
                status=GateStatus.PASS,
                is_partial=False,
                failing_rule_ids=[],
            ),
        ),
        findings=findings,
    )


def test_compliance_report_example_fixture_matches_mapper_output() -> None:
    expected = to_compliance_report_response(
        _build_illustrative_example_report()
    )
    raw_json = EXAMPLE_FIXTURE_PATH.read_text(encoding="utf-8")
    from_fixture = ComplianceReportResponse.model_validate_json(raw_json)

    assert raw_json.strip() == expected.model_dump_json(indent=2)
    assert from_fixture == expected
    assert from_fixture.after is None
    assert from_fixture.fixes == []
    assert from_fixture.new_findings_after_fixes == []
    assert from_fixture.sponsor_inputs_needed == []
    assert {item.status for item in from_fixture.findings} == set(RuleStatus)


def test_finding_view_subclasses_rule_finding_and_includes_all_fields() -> (
    None
):
    assert issubclass(FindingView, RuleFinding)
    assert set(RuleFinding.model_fields).issubset(FindingView.model_fields)
    assert set(FindingView.model_fields) - set(RuleFinding.model_fields) == {
        "finding_id"
    }


def test_mapper_computes_counts_families_and_finding_ids() -> None:
    # Intentionally put XS before REG and EST to verify families follow
    # RuleFamily definition order (REG, M11, EST, XS, DM, ELQ, EX, AMD).
    findings = [
        _make_finding("XS-05", RuleFamily.XS, status=RuleStatus.FIRED),
        _make_finding("XS-17", RuleFamily.XS, status=RuleStatus.CANNOT_ASSESS),
        _make_finding("REG-27", RuleFamily.REG, status=RuleStatus.FIRED),
        _make_finding("REG-28", RuleFamily.REG, status=RuleStatus.PASSED),
        _make_finding("EST-01", RuleFamily.EST, status=RuleStatus.PASSED),
        _make_finding(
            "EST-23",
            RuleFamily.EST,
            status=RuleStatus.INSUFFICIENT_COMPARATORS,
        ),
        _make_finding(
            "DM-43", RuleFamily.DM, status=RuleStatus.NOT_APPLICABLE
        ),
    ]
    report = _make_report(findings)

    response = to_compliance_report_response(report)

    assert response.run.rules_evaluated == len(findings)
    assert response.run.comparators_used == 0
    assert response.counts == StatusCounts(
        fired=2,
        passed=2,
        not_applicable=1,
        insufficient_comparators=1,
        cannot_assess=1,
        total=7,
    )
    assert response.families == [
        FamilySummary(
            family=RuleFamily.REG,
            label=FAMILY_LABELS[RuleFamily.REG],
            fired=1,
            applicable=2,
        ),
        FamilySummary(
            family=RuleFamily.EST,
            label=FAMILY_LABELS[RuleFamily.EST],
            fired=0,
            applicable=1,
        ),
        FamilySummary(
            family=RuleFamily.XS,
            label=FAMILY_LABELS[RuleFamily.XS],
            fired=1,
            applicable=1,
        ),
        FamilySummary(
            family=RuleFamily.DM,
            label=FAMILY_LABELS[RuleFamily.DM],
            fired=0,
            applicable=0,
        ),
    ]
    assert [view.finding_id for view in response.findings] == [
        f"{SAMPLE_PROTOCOL_ID}:{item.rule_id}" for item in findings
    ]


def test_top_finding_ids_ranks_by_weight_times_confidence_with_ties() -> None:
    # Weights: S1=10, S2=4, S3=1.
    # XS-05 (10 * 1.0 = 10.0) and EST-04 (10 * 1.0 = 10.0) tie;
    # tie must break by rule_id ascending -> EST-04 before XS-05.
    # REG-27 (10 * 0.8 = 8.0) > DM-03 (4 * 1.0 = 4.0) > REG-26 (4 * 0.5 = 2.0)
    # > XS-21 (1 * 1.0 = 1.0). Passed S1 rule EST-01 must be excluded.
    findings = [
        _make_finding(
            "XS-05",
            RuleFamily.XS,
            severity=RuleSeverity.S1,
            status=RuleStatus.FIRED,
            confidence=1.0,
        ),
        _make_finding(
            "REG-26",
            RuleFamily.REG,
            severity=RuleSeverity.S2,
            status=RuleStatus.FIRED,
            confidence=0.5,
        ),
        _make_finding(
            "EST-01",
            RuleFamily.EST,
            severity=RuleSeverity.S1,
            status=RuleStatus.PASSED,
            confidence=1.0,
        ),
        _make_finding(
            "EST-04",
            RuleFamily.EST,
            severity=RuleSeverity.S1,
            status=RuleStatus.FIRED,
            confidence=1.0,
        ),
        _make_finding(
            "XS-21",
            RuleFamily.XS,
            severity=RuleSeverity.S3,
            status=RuleStatus.FIRED,
            confidence=1.0,
        ),
        _make_finding(
            "REG-27",
            RuleFamily.REG,
            severity=RuleSeverity.S1,
            status=RuleStatus.FIRED,
            confidence=0.8,
        ),
        _make_finding(
            "DM-03",
            RuleFamily.DM,
            severity=RuleSeverity.S2,
            status=RuleStatus.FIRED,
            confidence=1.0,
        ),
    ]
    response = to_compliance_report_response(_make_report(findings))

    assert response.top_finding_ids == [
        f"{SAMPLE_PROTOCOL_ID}:EST-04",
        f"{SAMPLE_PROTOCOL_ID}:XS-05",
        f"{SAMPLE_PROTOCOL_ID}:REG-27",
        f"{SAMPLE_PROTOCOL_ID}:DM-03",
        f"{SAMPLE_PROTOCOL_ID}:REG-26",
        f"{SAMPLE_PROTOCOL_ID}:XS-21",
    ]


def test_top_finding_ids_caps_at_fifteen_items() -> None:
    findings = [
        _make_finding(
            f"EST-{index:02d}",
            RuleFamily.EST,
            severity=RuleSeverity.S1,
            status=RuleStatus.FIRED,
        )
        for index in range(1, 20)
    ]
    response = to_compliance_report_response(_make_report(findings))

    assert len(response.top_finding_ids) == MAX_TOP_FINDINGS_COUNT
    assert response.top_finding_ids[0] == f"{SAMPLE_PROTOCOL_ID}:EST-01"
    assert response.top_finding_ids[-1] == f"{SAMPLE_PROTOCOL_ID}:EST-15"


def test_finding_to_recommendation_maps_severity_and_details() -> None:
    expected_by_rule_severity = {
        RuleSeverity.S1: Severity.CRITICAL,
        RuleSeverity.S2: Severity.WARNING,
        RuleSeverity.S3: Severity.INFO,
    }
    for (
        rule_severity,
        expected_card_severity,
    ) in expected_by_rule_severity.items():
        finding = _make_finding(
            "REG-27",
            RuleFamily.REG,
            severity=rule_severity,
            status=RuleStatus.FIRED,
            confidence=0.9,
            requires_medical_review=True,
        )
        card = finding_to_recommendation(SAMPLE_PROTOCOL_ID, finding)

        assert card.recommendation_id == f"{SAMPLE_PROTOCOL_ID}:REG-27"
        assert card.protocol_id == SAMPLE_PROTOCOL_ID
        assert card.source_step == PipelineStep.COMPLETENESS
        assert card.severity == expected_card_severity
        assert card.title == finding.title
        assert card.description == finding.finding
        assert card.status == RecommendationStatus.PENDING
        assert card.details == {
            "rule_id": "REG-27",
            "family": "REG",
            "rule_severity": str(rule_severity),
            "location": {
                "section": "3.1.1",
                "heading": "OBJECTIVES_AND_ESTIMANDS",
                "page": 12,
            },
            "evidence": [
                {
                    "page_number": 12,
                    "quote": "Change in HbA1c from baseline to Month 6.",
                    "is_verified": True,
                }
            ],
            "searched_locations": [
                {
                    "heading": "OBJECTIVES_AND_ESTIMANDS",
                    "section_title": "3. Objectives and Estimands",
                    "start_page": 11,
                    "end_page": 13,
                }
            ],
            "proposed_fix": "Proposed fix for REG-27",
            "requires_medical_review": True,
            "confidence": 0.9,
            "source": "ICH M11 Template, Step 4",
            "source_tier": "ich",
            "check_method": "deterministic",
        }


def test_to_recommendations_emits_only_fired_findings() -> None:
    findings = [
        _make_finding("REG-27", RuleFamily.REG, status=RuleStatus.FIRED),
        _make_finding("EST-01", RuleFamily.EST, status=RuleStatus.PASSED),
        _make_finding(
            "DM-43", RuleFamily.DM, status=RuleStatus.NOT_APPLICABLE
        ),
        _make_finding(
            "EST-23",
            RuleFamily.EST,
            status=RuleStatus.INSUFFICIENT_COMPARATORS,
        ),
        _make_finding("XS-17", RuleFamily.XS, status=RuleStatus.CANNOT_ASSESS),
        _make_finding("XS-05", RuleFamily.XS, status=RuleStatus.FIRED),
    ]
    cards = to_recommendations(_make_report(findings))

    assert [card.recommendation_id for card in cards] == [
        f"{SAMPLE_PROTOCOL_ID}:REG-27",
        f"{SAMPLE_PROTOCOL_ID}:XS-05",
    ]


def test_partial_gate_round_trips_through_json() -> None:
    report = _make_report(
        [_make_finding("REG-27", RuleFamily.REG, status=RuleStatus.FIRED)]
    )
    response = to_compliance_report_response(report)
    round_tripped = ComplianceReportResponse.model_validate_json(
        response.model_dump_json()
    )

    assert round_tripped.before.registration_gate.status == GateStatus.FAIL
    assert round_tripped.before.registration_gate.is_partial is True
    assert round_tripped.before.registration_gate.failing_rule_ids == [
        "REG-27"
    ]
    assert round_tripped.before.review_gate.is_partial is False
