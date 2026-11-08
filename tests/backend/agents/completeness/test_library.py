"""Unit tests for the exclusion-library matcher (Family EX, Part G)."""

from backend.agents.completeness.logic import (
    LibraryItemMatch,
    LibraryMatches,
    build_judgement_batches,
    format_library_prompt,
    resolve_library_batch,
)
from backend.agents.completeness.rules import (
    ApplicabilityCondition,
    LibraryTag,
    RuleDefinition,
)
from backend.shared.messages import (
    CheckMethod,
    CriterionKind,
    DrugClass,
    EligibilityCriterion,
    M11Heading,
    PageText,
    ProtocolDocument,
    RuleFamily,
    RuleSeverity,
    RuleStatus,
    SourceTier,
    TrialProfile,
)
from tests.backend.agents.completeness.factories import (
    make_citation,
    make_document,
    make_profile,
    make_section,
)

DKA_TEXT = "Diabetic ketoacidosis within 6 months before screening"
HIV_TEXT = "Known HIV infection"


def _library_rule(
    rule_id: str,
    tag: LibraryTag,
    applies_when: tuple[ApplicabilityCondition, ...] = (),
) -> RuleDefinition:
    return RuleDefinition(
        id=rule_id,
        family=RuleFamily.EX,
        severity=RuleSeverity.S2,
        detection=("J",),
        applies_when=applies_when,
        sections=(M11Heading.TRIAL_POPULATION,),
        check=CheckMethod.JUDGEMENT,
        title="Example library item",
        flag_if="No criterion excludes the example condition.",
        fix="Exclude the example condition.",
        source="EMA CPMP/EWP/1080/00 Rev. 2",
        source_tier=SourceTier.FINAL_GUIDANCE,
        library_tag=tag,
    )


def _document() -> ProtocolDocument:
    return make_document(
        pages=[PageText(page_number=1, text=f"{DKA_TEXT}\n{HIV_TEXT}")],
        sections=[make_section(M11Heading.TRIAL_POPULATION, "5", 1, 1)],
        eligibility_criteria=[
            EligibilityCriterion(
                criterion_id="EX-03",
                kind=CriterionKind.EXCLUSION,
                text=DKA_TEXT,
                citation=make_citation(DKA_TEXT, page_number=1),
            ),
            EligibilityCriterion(
                criterion_id="EX-09",
                kind=CriterionKind.EXCLUSION,
                text=HIV_TEXT,
                citation=make_citation(HIV_TEXT, page_number=1),
            ),
        ],
    )


def _resolve(
    rule: RuleDefinition,
    match: LibraryItemMatch | None,
    profile: TrialProfile | None = None,
) -> tuple[RuleStatus, object]:
    batch = build_judgement_batches([rule])[0]
    response = LibraryMatches(matches=[match] if match else [])
    [evaluated] = resolve_library_batch(
        batch, response, _document(), profile or make_profile()
    )
    return evaluated.finding.status, evaluated


def test_absent_core_item_fires_as_an_absence_for_second_opinion() -> None:
    rule = _library_rule("EX-03", LibraryTag.CORE)

    status, evaluated = _resolve(
        rule, LibraryItemMatch(rule_id="EX-03", is_present=False)
    )

    assert status == RuleStatus.FIRED
    assert evaluated.needs_second_opinion is True
    assert [loc.heading for loc in evaluated.finding.searched_locations] == [
        M11Heading.TRIAL_POPULATION
    ]


def test_present_core_item_passes_citing_the_matched_criterion() -> None:
    rule = _library_rule("EX-03", LibraryTag.CORE)

    status, evaluated = _resolve(
        rule,
        LibraryItemMatch(
            rule_id="EX-03",
            is_present=True,
            criterion_ids=["EX-03"],
            is_operable=True,
            has_rationale=False,
        ),
    )

    assert status == RuleStatus.PASSED
    assert evaluated.finding.location.section == "EX-03"
    assert [c.quote for c in evaluated.finding.evidence] == [DKA_TEXT]
    assert "operable: yes" in evaluated.finding.finding
    assert "justified: no" in evaluated.finding.finding


def test_absent_class_item_fires_only_when_the_class_is_confirmed() -> None:
    rule = _library_rule(
        "EX-36",
        LibraryTag.CLASS,
        (ApplicabilityCondition.DRUG_CLASS_IS_SGLT2,),
    )
    absent = LibraryItemMatch(rule_id="EX-36", is_present=False)

    confirmed_status, _ = _resolve(
        rule, absent, make_profile(drug_class=DrugClass.SGLT2_INHIBITOR)
    )
    unknown_status, unknown = _resolve(rule, absent, TrialProfile())

    assert confirmed_status == RuleStatus.FIRED
    assert unknown_status == RuleStatus.CANNOT_ASSESS
    assert unknown.finding.status_reason


def test_breadth_item_without_rationale_fires_pointing_to_elq_11() -> None:
    rule = _library_rule("EX-39", LibraryTag.BREADTH)

    status, evaluated = _resolve(
        rule,
        LibraryItemMatch(
            rule_id="EX-39",
            is_present=True,
            criterion_ids=["EX-09"],
            is_operable=True,
            has_rationale=False,
        ),
    )

    assert status == RuleStatus.FIRED
    assert "ELQ-11" in evaluated.finding.finding
    assert evaluated.finding.location.section == "EX-09"
    assert evaluated.needs_second_opinion is True


def test_breadth_item_passes_when_justified_or_not_excluded() -> None:
    rule = _library_rule("EX-39", LibraryTag.BREADTH)

    justified, _ = _resolve(
        rule,
        LibraryItemMatch(
            rule_id="EX-39",
            is_present=True,
            criterion_ids=["EX-09"],
            has_rationale=True,
        ),
    )
    not_excluded, _ = _resolve(
        rule, LibraryItemMatch(rule_id="EX-39", is_present=False)
    )

    assert justified == RuleStatus.PASSED
    assert not_excluded == RuleStatus.PASSED


def test_unknown_criterion_ids_or_missing_match_cannot_be_assessed() -> None:
    rule = _library_rule("EX-03", LibraryTag.CORE)

    invented_ids, _ = _resolve(
        rule,
        LibraryItemMatch(
            rule_id="EX-03", is_present=True, criterion_ids=["EX-99"]
        ),
    )
    omitted, _ = _resolve(rule, None)

    assert invented_ids == RuleStatus.CANNOT_ASSESS
    assert omitted == RuleStatus.CANNOT_ASSESS


def test_library_prompt_lists_criteria_and_items_with_their_tags() -> None:
    rule = _library_rule("EX-03", LibraryTag.CORE)
    batch = build_judgement_batches([rule])[0]

    prompt = format_library_prompt(batch, _document())

    assert DKA_TEXT in prompt
    assert '"tag":"CORE"' in prompt
    assert "EX-03" in prompt
