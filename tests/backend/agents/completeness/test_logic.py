"""Unit tests for the completeness checker's pure engine logic."""

import pytest

from backend.agents.completeness.logic import (
    PERFECT_SCORE,
    CheckOutcome,
    EvaluatedRule,
    assemble_report,
    compute_run_result,
    condition_holds,
    evaluate_rule,
    finding_from_outcome,
    pre_decide,
    select_profile_pages,
)
from backend.agents.completeness.rules import (
    ApplicabilityCondition,
    RequiredInput,
    RuleCatalogue,
    RuleDefinition,
)
from backend.shared.messages import (
    AllocationType,
    CheckMethod,
    Citation,
    ControlType,
    DiabetesType,
    GateStatus,
    InterventionType,
    M11Heading,
    MaskingType,
    PageText,
    ProtocolDocument,
    ProtocolSection,
    RuleFamily,
    RuleFinding,
    RuleSeverity,
    RuleStatus,
    SourceTier,
    TrialDesignFacts,
    TrialProfile,
)

QUOTE = "Participants will be randomly assigned to two arms"
PROFILE_QUOTE = "a community-based behavioural meal intervention trial"


def _citation(quote: str = QUOTE, page_number: int = 3) -> Citation:
    return Citation(page_number=page_number, quote=quote, is_verified=True)


def _rule(
    rule_id: str = "XS-05",
    family: RuleFamily = RuleFamily.XS,
    severity: RuleSeverity = RuleSeverity.S1,
    applies_when: tuple[ApplicabilityCondition, ...] = (),
    needs_inputs: tuple[RequiredInput, ...] = (),
) -> RuleDefinition:
    return RuleDefinition(
        id=rule_id,
        family=family,
        severity=severity,
        detection=("X",),
        applies_when=applies_when,
        needs_inputs=needs_inputs,
        sections=(M11Heading.TRIAL_DESIGN,),
        check=CheckMethod.DETERMINISTIC,
        title="Example rule",
        flag_if="Example trigger.",
        fix="Example fix.",
        source="ICH M11 Template, Step 4",
        source_tier=SourceTier.ICH,
    )


def _finding(
    rule_id: str,
    family: RuleFamily,
    severity: RuleSeverity,
    status: RuleStatus,
) -> RuleFinding:
    rule = _rule(rule_id, family, severity)
    outcome = CheckOutcome(
        status=status,
        finding="Example finding.",
        evidence=(_citation(),) if status == RuleStatus.FIRED else (),
        status_reason=(
            None
            if status in (RuleStatus.FIRED, RuleStatus.PASSED)
            else "Example reason."
        ),
    )
    return finding_from_outcome(rule, outcome, CheckMethod.DETERMINISTIC)


def _catalogue(*rules: RuleDefinition) -> RuleCatalogue:
    return RuleCatalogue(rules=rules)


def _profile(**fields: object) -> TrialProfile:
    return TrialProfile.model_validate(
        {
            name: {"value": value, "citation": _citation(PROFILE_QUOTE)}
            for name, value in fields.items()
        }
    )


def _design(**fields: object) -> TrialDesignFacts:
    return TrialDesignFacts.model_validate(
        {
            name: {"value": value, "citation": _citation()}
            for name, value in fields.items()
        }
    )


# --- applicability conditions ------------------------------------------


@pytest.mark.parametrize(
    ("intervention", "expected"),
    [
        (InterventionType.DRUG, True),
        (InterventionType.BIOLOGIC, True),
        (InterventionType.BEHAVIORAL, False),
    ],
)
def test_intervention_is_drug_covers_drugs_and_biologics(
    intervention: InterventionType, expected: bool
) -> None:
    value = condition_holds(
        ApplicabilityCondition.INTERVENTION_IS_DRUG,
        _profile(intervention_type=intervention),
        None,
    )

    assert value.holds is expected
    assert value.citation is not None


def test_condition_is_unknown_when_profile_field_is_missing() -> None:
    value = condition_holds(
        ApplicabilityCondition.CONTROL_IS_PLACEBO, TrialProfile(), None
    )

    assert value.holds is None
    assert value.citation is None


def test_randomization_and_blinding_come_from_design_facts() -> None:
    design = _design(
        allocation=AllocationType.RANDOMIZED, masking=MaskingType.NONE
    )

    randomized = condition_holds(
        ApplicabilityCondition.IS_RANDOMIZED, TrialProfile(), design
    )
    blinded = condition_holds(
        ApplicabilityCondition.IS_BLINDED, TrialProfile(), design
    )

    assert randomized.holds is True
    assert blinded.holds is False


# --- pre-decisions: not applicable, missing inputs ---------------------


def test_rule_is_not_applicable_when_its_condition_is_false() -> None:
    rule = _rule(applies_when=(ApplicabilityCondition.CONTROL_IS_PLACEBO,))
    profile = _profile(control_type=ControlType.USUAL_CARE)

    outcome = pre_decide(rule, profile, None, frozenset())

    assert outcome is not None
    assert outcome.status == RuleStatus.NOT_APPLICABLE
    assert outcome.status_reason is not None
    assert "placebo" in outcome.status_reason.lower()
    assert [c.quote for c in outcome.evidence] == [PROFILE_QUOTE]


def test_unknown_condition_means_the_rule_is_still_evaluated() -> None:
    rule = _rule(applies_when=(ApplicabilityCondition.DIABETES_TYPE_T2D,))

    assert pre_decide(rule, TrialProfile(), None, frozenset()) is None


def test_missing_input_makes_the_rule_cannot_assess() -> None:
    rule = _rule(needs_inputs=(RequiredInput.INVESTIGATORS_BROCHURE,))

    outcome = pre_decide(rule, TrialProfile(), None, frozenset())

    assert outcome is not None
    assert outcome.status == RuleStatus.CANNOT_ASSESS
    assert outcome.status_reason is not None
    assert "brochure" in outcome.status_reason.lower()


def test_missing_comparator_corpus_is_insufficient_comparators() -> None:
    rule = _rule(needs_inputs=(RequiredInput.COMPARATOR_CORPUS,))

    outcome = pre_decide(rule, TrialProfile(), None, frozenset())

    assert outcome is not None
    assert outcome.status == RuleStatus.INSUFFICIENT_COMPARATORS


def test_not_applicable_takes_precedence_over_missing_input() -> None:
    rule = _rule(
        applies_when=(ApplicabilityCondition.INTERVENTION_IS_DRUG,),
        needs_inputs=(RequiredInput.INVESTIGATORS_BROCHURE,),
    )
    profile = _profile(intervention_type=InterventionType.BEHAVIORAL)

    outcome = pre_decide(rule, profile, None, frozenset())

    assert outcome is not None
    assert outcome.status == RuleStatus.NOT_APPLICABLE


def test_available_input_and_true_condition_mean_evaluate() -> None:
    rule = _rule(
        applies_when=(ApplicabilityCondition.DIABETES_TYPE_T2D,),
        needs_inputs=(RequiredInput.REGISTRY_RECORD,),
    )
    profile = _profile(diabetes_type=DiabetesType.T2D)

    outcome = pre_decide(
        rule, profile, None, frozenset({RequiredInput.REGISTRY_RECORD})
    )

    assert outcome is None


# --- findings ----------------------------------------------------------


def test_fired_finding_carries_the_rule_fix_and_metadata() -> None:
    rule = _rule()
    outcome = CheckOutcome(
        status=RuleStatus.FIRED,
        finding="Primary timepoint Week 26 has no visit.",
        evidence=(_citation(),),
    )

    finding = finding_from_outcome(rule, outcome, CheckMethod.DETERMINISTIC)

    assert finding.proposed_fix == rule.fix
    assert (finding.rule_id, finding.severity, finding.title) == (
        rule.id,
        rule.severity,
        rule.title,
    )
    assert (finding.source, finding.source_tier) == (
        rule.source,
        rule.source_tier,
    )


def test_passed_finding_has_no_proposed_fix() -> None:
    outcome = CheckOutcome(status=RuleStatus.PASSED, finding="Visit found.")

    finding = finding_from_outcome(_rule(), outcome, CheckMethod.DETERMINISTIC)

    assert finding.proposed_fix is None


# --- score -------------------------------------------------------------


def test_score_uses_only_fired_and_passed_weights() -> None:
    findings = [
        _finding("XS-01", RuleFamily.XS, RuleSeverity.S1, RuleStatus.FIRED),
        _finding("XS-02", RuleFamily.XS, RuleSeverity.S2, RuleStatus.PASSED),
        _finding("XS-03", RuleFamily.XS, RuleSeverity.S3, RuleStatus.PASSED),
        _finding(
            "XS-04", RuleFamily.XS, RuleSeverity.S1, RuleStatus.CANNOT_ASSESS
        ),
        _finding(
            "XS-05", RuleFamily.XS, RuleSeverity.S1, RuleStatus.NOT_APPLICABLE
        ),
    ]

    result = compute_run_result(findings)

    # fired weight 10 over applicable weight 10 + 4 + 1 = 15
    assert result.score == pytest.approx(100 * (1 - 10 / 15))


def test_score_is_perfect_when_no_rule_is_applicable() -> None:
    findings = [
        _finding(
            "XS-01", RuleFamily.XS, RuleSeverity.S1, RuleStatus.CANNOT_ASSESS
        )
    ]

    assert compute_run_result(findings).score == PERFECT_SCORE


# --- gates -------------------------------------------------------------


def test_registration_gate_fails_on_any_fired_s1_reg_rule() -> None:
    findings = [
        _finding("REG-27", RuleFamily.REG, RuleSeverity.S1, RuleStatus.FIRED),
        _finding("REG-24", RuleFamily.REG, RuleSeverity.S1, RuleStatus.FIRED),
        _finding("REG-26", RuleFamily.REG, RuleSeverity.S2, RuleStatus.FIRED),
    ]

    gate = compute_run_result(findings).registration_gate

    assert gate.status == GateStatus.FAIL
    assert gate.failing_rule_ids == ["REG-24", "REG-27"]


def test_s2_rule_alone_does_not_fail_a_gate() -> None:
    findings = [
        _finding("XS-06", RuleFamily.XS, RuleSeverity.S2, RuleStatus.FIRED)
    ]

    assert compute_run_result(findings).review_gate.status == GateStatus.PASS


def test_review_gate_fails_on_fired_s1_in_est_xs_or_dm() -> None:
    findings = [
        _finding("DM-13", RuleFamily.DM, RuleSeverity.S1, RuleStatus.FIRED),
        _finding("REG-27", RuleFamily.REG, RuleSeverity.S1, RuleStatus.FIRED),
    ]

    gate = compute_run_result(findings).review_gate

    assert gate.status == GateStatus.FAIL
    assert gate.failing_rule_ids == ["DM-13"]


def test_registration_gate_is_partial_while_reg_s1_rules_are_missing() -> None:
    findings = [
        _finding("REG-24", RuleFamily.REG, RuleSeverity.S1, RuleStatus.PASSED)
    ]

    assert compute_run_result(findings).registration_gate.is_partial is True


def test_gate_is_partial_when_one_of_its_s1_rules_cannot_be_assessed() -> None:
    findings = [
        _finding(
            "XS-17", RuleFamily.XS, RuleSeverity.S1, RuleStatus.CANNOT_ASSESS
        )
    ]

    assert compute_run_result(findings).review_gate.is_partial is True


# --- report assembly ---------------------------------------------------


def _document() -> ProtocolDocument:
    return ProtocolDocument(
        protocol_id="NCT00000000",
        title="Example protocol",
        page_count=1,
        pages=[PageText(page_number=1, text=QUOTE)],
    )


def test_report_has_one_finding_per_rule_in_catalogue_order() -> None:
    first, second = _rule("XS-01"), _rule("XS-02")
    findings = [
        _finding("XS-02", RuleFamily.XS, RuleSeverity.S1, RuleStatus.PASSED),
        _finding("XS-01", RuleFamily.XS, RuleSeverity.S1, RuleStatus.FIRED),
    ]

    report = assemble_report(
        _document(), TrialProfile(), _catalogue(first, second), findings
    )

    assert [f.rule_id for f in report.findings] == ["XS-01", "XS-02"]
    assert report.rules_evaluated == 2
    assert report.after is None


def test_report_rejects_findings_that_do_not_cover_the_catalogue() -> None:
    findings = [
        _finding("XS-01", RuleFamily.XS, RuleSeverity.S1, RuleStatus.PASSED)
    ]

    with pytest.raises(ValueError, match="XS-02"):
        assemble_report(
            _document(),
            TrialProfile(),
            _catalogue(_rule("XS-01"), _rule("XS-02")),
            findings,
        )


# --- rule evaluation ---------------------------------------------------


def test_rule_without_a_check_is_cannot_assess_not_implemented() -> None:
    evaluated = evaluate_rule(
        _rule(), _document(), TrialProfile(), frozenset(), {}
    )

    assert isinstance(evaluated, EvaluatedRule)
    assert evaluated.needs_second_opinion is False
    assert evaluated.finding.status == RuleStatus.CANNOT_ASSESS
    assert evaluated.finding.status_reason is not None
    assert "not implemented" in evaluated.finding.status_reason


def test_registered_check_decides_the_rule() -> None:
    def fires(
        document: ProtocolDocument, profile: TrialProfile
    ) -> CheckOutcome:
        return CheckOutcome(
            status=RuleStatus.FIRED,
            finding="Visit missing.",
            evidence=(_citation(),),
        )

    evaluated = evaluate_rule(
        _rule(), _document(), TrialProfile(), frozenset(), {"XS-05": fires}
    )

    assert evaluated.needs_second_opinion is False
    assert evaluated.finding.status == RuleStatus.FIRED
    assert evaluated.finding.check_method == CheckMethod.DETERMINISTIC


def test_absence_fire_sets_second_opinion_and_fills_searched_locations() -> (
    None
):
    def fires_on_absence(
        document: ProtocolDocument, profile: TrialProfile
    ) -> CheckOutcome:
        return CheckOutcome(
            status=RuleStatus.FIRED,
            finding="No sample-size calculation found.",
            needs_second_opinion=True,
        )

    document = ProtocolDocument(
        protocol_id="NCT00000000",
        title="Example protocol",
        page_count=10,
        pages=[PageText(page_number=1, text=QUOTE)],
        sections=[
            _section(M11Heading.PROTOCOL_SUMMARY, 1, 2),
            _section(M11Heading.TRIAL_DESIGN, 3, 6),
        ],
    )
    evaluated = evaluate_rule(
        _rule(),
        document,
        TrialProfile(),
        frozenset(),
        {"XS-05": fires_on_absence},
    )

    assert evaluated.needs_second_opinion is True
    assert evaluated.finding.status == RuleStatus.FIRED
    assert evaluated.finding.evidence == []
    assert [
        (loc.heading, loc.section_title, loc.start_page, loc.end_page)
        for loc in evaluated.finding.searched_locations
    ] == [(M11Heading.TRIAL_DESIGN, "TRIAL_DESIGN", 3, 6)]


def test_pre_decided_rule_never_runs_its_check() -> None:
    def must_not_run(
        document: ProtocolDocument, profile: TrialProfile
    ) -> CheckOutcome:
        raise AssertionError("check ran for a not-applicable rule")

    rule = _rule(applies_when=(ApplicabilityCondition.CONTROL_IS_PLACEBO,))
    profile = _profile(control_type=ControlType.ACTIVE)

    evaluated = evaluate_rule(
        rule, _document(), profile, frozenset(), {"XS-05": must_not_run}
    )

    assert evaluated.finding.status == RuleStatus.NOT_APPLICABLE
    assert evaluated.needs_second_opinion is False


# --- profile page selection --------------------------------------------


def test_profile_pages_come_from_trial_level_sections() -> None:
    document = ProtocolDocument(
        protocol_id="NCT00000000",
        title="Example protocol",
        page_count=6,
        pages=[PageText(page_number=n, text=f"page {n}") for n in range(1, 7)],
        sections=[
            _section(M11Heading.PROTOCOL_SUMMARY, 1, 2),
            _section(M11Heading.STATISTICAL_CONSIDERATIONS, 3, 4),
            _section(M11Heading.TRIAL_INTERVENTION, 5, 5),
        ],
    )

    pages = select_profile_pages(document)

    assert [page.page_number for page in pages] == [1, 2, 5]


def test_profile_pages_fall_back_to_the_first_pages_without_sections() -> None:
    document = ProtocolDocument(
        protocol_id="NCT00000000",
        title="Example protocol",
        page_count=40,
        pages=[PageText(page_number=n, text="x") for n in range(1, 41)],
    )

    pages = select_profile_pages(document)

    assert [page.page_number for page in pages] == list(range(1, 16))


def _section(heading: M11Heading, start: int, end: int) -> ProtocolSection:
    return ProtocolSection(
        heading=heading,
        title=heading.value,
        start_page=start,
        end_page=end,
        summary="Example.",
        citation=_citation(page_number=start),
    )
