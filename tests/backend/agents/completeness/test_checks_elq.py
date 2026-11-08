"""Unit tests for Family ELQ (eligibility quality) code checks."""

from backend.agents.completeness.checks.eligibility import (
    check_elq_01,
    check_elq_03,
    check_elq_09,
    check_elq_17,
    check_elq_21,
)
from backend.agents.completeness.checks.prechecks import (
    precheck_elq_12,
    precheck_elq_19,
)
from backend.shared.messages import (
    CriterionKind,
    EligibilityCriterion,
    M11Heading,
    PageText,
    ProtocolDocument,
    RuleStatus,
    TrialDesignFacts,
)
from tests.backend.agents.completeness.factories import (
    cited,
    make_citation,
    make_document,
    make_profile,
    make_section,
)


def _criterion(
    criterion_id: str,
    text: str,
    kind: CriterionKind = CriterionKind.EXCLUSION,
) -> EligibilityCriterion:
    return EligibilityCriterion(
        criterion_id=criterion_id,
        kind=kind,
        text=text,
        citation=make_citation(quote=text, page_number=20),
    )


def _criteria_doc(
    *criteria: EligibilityCriterion, population_text: str = "Population"
) -> ProtocolDocument:
    return make_document(
        eligibility_criteria=list(criteria),
        pages=[PageText(page_number=1, text=population_text)],
        sections=[make_section(M11Heading.TRIAL_POPULATION, "5", 1, 1)],
    )


def test_elq_01_flags_vague_terms_without_a_threshold() -> None:
    doc = _criteria_doc(
        _criterion("EX-01", "Poorly controlled hypertension"),
        _criterion("EX-02", "Clinically significant ALT > 3 x ULN"),
        _criterion("EX-03", "Type 1 diabetes"),
    )

    outcome = check_elq_01(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert outcome.location.section == "EX-01"
    assert [c.quote for c in outcome.evidence] == [
        "Poorly controlled hypertension"
    ]


def test_elq_01_passes_when_every_criterion_is_answerable() -> None:
    doc = _criteria_doc(
        _criterion("EX-01", "Systolic blood pressure >= 160 mmHg"),
    )

    assert check_elq_01(doc, make_profile()).status == RuleStatus.PASSED


def test_elq_01_cannot_assess_without_extracted_criteria() -> None:
    doc = make_document()

    assert check_elq_01(doc, make_profile()).status == (
        RuleStatus.CANNOT_ASSESS
    )


def test_elq_03_flags_history_without_a_look_back_window() -> None:
    doc = _criteria_doc(
        _criterion("EX-04", "History of pancreatitis"),
        _criterion("EX-05", "History of pancreatitis within 6 months"),
        _criterion("EX-06", "Personal history of MTC at any time"),
    )

    outcome = check_elq_03(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert outcome.location.section == "EX-04"


def test_elq_09_flags_percent_only_hba1c_and_egfr_without_formula() -> None:
    doc = _criteria_doc(
        _criterion(
            "IN-02", "HbA1c 7.0-10.5% at screening", CriterionKind.INCLUSION
        ),
        _criterion("EX-07", "eGFR < 30 mL/min/1.73 m2"),
    )

    outcome = check_elq_09(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert outcome.location.section == "IN-02, EX-07"


def test_elq_09_passes_with_both_units_and_a_named_formula() -> None:
    doc = _criteria_doc(
        _criterion(
            "IN-02",
            "HbA1c 7.0-10.5% (53-91 mmol/mol)",
            CriterionKind.INCLUSION,
        ),
        _criterion("EX-07", "eGFR < 30 mL/min/1.73 m2 (CKD-EPI)"),
    )

    assert check_elq_09(doc, make_profile()).status == RuleStatus.PASSED


def test_elq_17_fires_on_language_requirement_without_translation() -> None:
    doc = _criteria_doc(
        _criterion(
            "IN-05",
            "Able to read and understand English",
            CriterionKind.INCLUSION,
        )
    )

    outcome = check_elq_17(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is True
    assert outcome.location.section == "IN-05"


def test_elq_17_passes_with_translation_plan_or_no_requirement() -> None:
    with_plan = _criteria_doc(
        _criterion(
            "IN-05",
            "Able to read and understand English",
            CriterionKind.INCLUSION,
        ),
        population_text="Consent forms will be translated where needed.",
    )
    no_requirement = _criteria_doc(_criterion("EX-01", "Type 1 diabetes"))

    assert check_elq_17(with_plan, make_profile()).status == (
        RuleStatus.PASSED
    )
    assert check_elq_17(no_requirement, make_profile()).status == (
        RuleStatus.PASSED
    )


def test_elq_21_fires_above_twenty_five_exclusions_only() -> None:
    def exclusions(count: int) -> ProtocolDocument:
        return _criteria_doc(
            *(
                _criterion(f"EX-{index:02d}", f"Exclusion number {index}")
                for index in range(1, count + 1)
            )
        )

    assert check_elq_21(exclusions(25), make_profile()).status == (
        RuleStatus.PASSED
    )
    over = check_elq_21(exclusions(26), make_profile())
    assert over.status == RuleStatus.FIRED
    assert "26" in over.finding


def test_elq_12_passes_without_upper_age_and_defers_with_one() -> None:
    no_limit = make_document(
        design=TrialDesignFacts(min_age_years=cited(18.0))
    )
    with_limit = make_document(
        design=TrialDesignFacts(max_age_years=cited(75.0))
    )

    outcome = precheck_elq_12(no_limit, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.PASSED
    assert precheck_elq_12(with_limit, make_profile()) is None


def test_elq_19_passes_without_bmi_criterion_and_defers_with_one() -> None:
    no_bmi = _criteria_doc(_criterion("EX-01", "Type 1 diabetes"))
    with_bmi = _criteria_doc(
        _criterion("IN-03", "BMI 25 to 35 kg/m2", CriterionKind.INCLUSION)
    )

    outcome = precheck_elq_19(no_bmi, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.PASSED
    assert precheck_elq_19(with_bmi, make_profile()) is None
