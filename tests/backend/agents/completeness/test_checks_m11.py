"""Unit tests for Family M11 (ICH M11 structure) code checks."""

from backend.agents.completeness.checks.consistency import (
    check_xs_12,
    check_xs_15,
)
from backend.agents.completeness.checks.prechecks import (
    precheck_m11_01,
    precheck_m11_07,
    precheck_m11_18,
    precheck_m11_19,
    precheck_m11_20,
    precheck_m11_27,
)
from backend.agents.completeness.checks.structure import (
    STRUCTURE_CHECKS,
    check_m11_03,
    check_m11_05,
    check_m11_21,
    check_m11_35,
    check_m11_39,
    check_m11_47,
    check_m11_71,
)
from backend.shared.messages import (
    CommitteeType,
    CriterionKind,
    EligibilityCriterion,
    EpochType,
    M11Heading,
    PageText,
    ProtocolDocument,
    RuleStatus,
    SynopsisConsistencyExtraction,
    TrialDesignFacts,
    TrialPhase,
    TrialProfile,
)
from tests.backend.agents.completeness.factories import (
    cited,
    make_citation,
    make_committees,
    make_document,
    make_epoch,
    make_profile,
    make_section,
    make_subsection,
    make_visit,
)


def _pages_doc(*texts: str) -> ProtocolDocument:
    return make_document(
        pages=[
            PageText(page_number=number, text=text)
            for number, text in enumerate(texts, start=1)
        ]
    )


def test_m11_03_lists_leftover_template_text() -> None:
    doc = _pages_doc(
        "Sponsor: <Enter sponsor legal name here>",
        "Phase: [Select phase from the pick-list]",
    )

    outcome = check_m11_03(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert {c.page_number for c in outcome.evidence} == {1, 2}


def test_m11_03_passes_on_a_clean_protocol() -> None:
    doc = _pages_doc("Sponsor: Example Pharma Ltd, 1 Main Street.")

    assert check_m11_03(doc, make_profile()).status == RuleStatus.PASSED


def test_m11_05_flags_subjects_but_not_subject_to() -> None:
    flagged = _pages_doc("All subjects will attend the screening visit.")
    allowed = _pages_doc(
        "Dosing is subject to the investigator's review at each visit."
    )

    outcome = check_m11_05(flagged, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert outcome.evidence[0].is_verified
    assert check_m11_05(allowed, make_profile()).status == RuleStatus.PASSED


def test_m11_21_passes_with_visit_windows_and_fires_without() -> None:
    windows = _pages_doc("Visit 3 (Week 4, ±3 days): HbA1c, vital signs")
    no_windows = _pages_doc("Visit 3 (Week 4): HbA1c, vital signs")

    assert check_m11_21(windows, make_profile()).status == RuleStatus.PASSED
    outcome = check_m11_21(no_windows, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is True


def _age_doc(text: str) -> ProtocolDocument:
    return make_document(
        eligibility_criteria=[
            EligibilityCriterion(
                criterion_id="IN-01",
                kind=CriterionKind.INCLUSION,
                text=text,
                citation=make_citation(quote=text, page_number=20),
            )
        ]
    )


def test_m11_35_needs_the_age_qualification_timepoint() -> None:
    timed = _age_doc("Aged 18 to 75 years at the time of signing consent")
    untimed = _age_doc("Aged 18 to 75 years")

    assert check_m11_35(timed, make_profile()).status == RuleStatus.PASSED
    outcome = check_m11_35(untimed, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.location.section == "IN-01"


def test_m11_35_cannot_assess_without_an_age_criterion() -> None:
    doc = _age_doc("Type 2 diabetes diagnosed at least 6 months ago")

    assert check_m11_35(doc, make_profile()).status == (
        RuleStatus.CANNOT_ASSESS
    )


def test_m11_39_flags_waivers_but_not_their_prohibition() -> None:
    allowed = _pages_doc(
        "Exceptions to the eligibility criteria may be granted by the "
        "medical monitor."
    )
    forbidden = _pages_doc(
        "No waivers of the eligibility criteria will be granted."
    )
    regulatory = _pages_doc("The trial is conducted under an IND exemption.")

    assert check_m11_39(allowed, make_profile()).status == RuleStatus.FIRED
    assert check_m11_39(forbidden, make_profile()).status == (
        RuleStatus.PASSED
    )
    assert check_m11_39(regulatory, make_profile()).status == (
        RuleStatus.PASSED
    )


def test_m11_47_flags_a_disclosed_block_size() -> None:
    disclosed = _pages_doc("Randomisation uses permuted blocks of 4.")
    hidden = _pages_doc("The block size will not be disclosed to sites.")

    outcome = check_m11_47(disclosed, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert outcome.evidence
    assert check_m11_47(hidden, make_profile()).status == RuleStatus.PASSED


def test_m11_58_and_m11_67_reuse_the_consistency_checks() -> None:
    assert STRUCTURE_CHECKS["M11-58"] is check_xs_15
    assert STRUCTURE_CHECKS["M11-67"] is check_xs_12


def test_m11_71_names_missing_appendices() -> None:
    doc = make_document(
        pages=[
            PageText(page_number=1, text="Appendix 1: Clinical Laboratory "),
            PageText(page_number=2, text="12 References\nSmith J, 2020."),
        ],
        subsections=[make_subsection("A2", "List of Abbreviations", 3)],
    )

    outcome = check_m11_71(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert "regional" in outcome.finding
    assert "laboratory" not in outcome.finding
    assert outcome.needs_second_opinion is True


# --- pre-checks ---------------------------------------------------------


def test_m11_01_fires_when_a_main_section_is_missing() -> None:
    partial = make_document(
        sections=[make_section(M11Heading.PROTOCOL_SUMMARY, "1", 1, 2)]
    )
    complete = make_document(
        sections=[
            make_section(heading, heading.value, 1, 1)
            for heading in M11Heading
            if heading != M11Heading.OTHER
        ]
    )

    outcome = precheck_m11_01(partial, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.FIRED
    assert "TRIAL_DESIGN" in outcome.finding
    assert precheck_m11_01(complete, make_profile()) is None


def test_m11_07_fires_without_title_or_phase() -> None:
    no_phase = make_document(
        design=TrialDesignFacts(official_title=cited("A trial of X"))
    )
    both = make_document(
        design=TrialDesignFacts(
            official_title=cited("A trial of X"),
            phase=cited(TrialPhase.PHASE3),
        )
    )

    outcome = precheck_m11_07(no_phase, make_profile())

    assert outcome is not None
    assert "phase" in outcome.finding
    assert precheck_m11_07(both, make_profile()) is None


def test_m11_18_and_19_pass_on_extracted_committees_and_epochs() -> None:
    doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_committees=make_committees(
                (CommitteeType.DATA_MONITORING, "Independent DMC")
            ),
            schema_epochs=[make_epoch(EpochType.SCREENING)],
        )
    )
    empty = make_document(synopsis_check=SynopsisConsistencyExtraction())

    for precheck in (precheck_m11_18, precheck_m11_19):
        outcome = precheck(doc, make_profile())
        assert outcome is not None
        assert outcome.status == RuleStatus.PASSED
        assert precheck(empty, make_profile()) is None


def test_m11_20_handles_missing_phone_and_empty_schedules() -> None:
    with_phone = make_document(
        schedule=[make_visit("Telephone contact", procedures=["AE review"])]
    )
    empty = make_document(schedule=[])
    clinic_only = make_document(schedule=[make_visit()])

    passed = precheck_m11_20(with_phone, make_profile())
    fired = precheck_m11_20(empty, make_profile())

    assert passed is not None
    assert passed.status == RuleStatus.PASSED
    assert fired is not None
    assert fired.status == RuleStatus.FIRED
    assert precheck_m11_20(clinic_only, make_profile()) is None


def test_m11_27_passes_when_the_hypothesis_type_is_known() -> None:
    assert precheck_m11_27(make_document(), TrialProfile()) is None
    outcome = precheck_m11_27(make_document(), make_profile())
    assert outcome is not None
    assert outcome.status == RuleStatus.PASSED
