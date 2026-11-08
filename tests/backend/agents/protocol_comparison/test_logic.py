"""Tests for peer screening and drug-class logic."""

from backend.agents.protocol_comparison.logic import (
    ExclusionReason,
    classify_drug_classes,
    screen_peers,
)
from backend.agents.protocol_comparison.rules import (
    TYPE_2_DIABETES_PEER_CRITERIA,
    DrugClass,
)
from backend.clients.clinicaltrials_gov import StudyRecord
from tests.backend.agents.protocol_comparison.builders import make_study


def reasons_for(study: StudyRecord) -> tuple[ExclusionReason, ...]:
    screening = screen_peers([study], TYPE_2_DIABETES_PEER_CRITERIA)
    assert len(screening.excluded) == 1
    return screening.excluded[0].reasons


def test_screen_keeps_type_2_drug_treatment_trial() -> None:
    study = make_study()

    screening = screen_peers([study], TYPE_2_DIABETES_PEER_CRITERIA)

    assert screening.peers == (study,)
    assert screening.excluded == ()


def test_screen_drops_type_1_trial() -> None:
    study = make_study(condition_mesh=("Diabetes Mellitus, Type 1",))

    assert reasons_for(study) == (
        ExclusionReason.MISSING_TARGET_CONDITION,
        ExclusionReason.EXCLUDED_CONDITION,
    )


def test_screen_drops_trial_listing_both_diabetes_types() -> None:
    study = make_study(
        condition_mesh=(
            "Diabetes Mellitus, Type 1",
            "Diabetes Mellitus, Type 2",
        )
    )

    assert reasons_for(study) == (ExclusionReason.EXCLUDED_CONDITION,)


def test_screen_drops_behavioural_and_supplement_only_trials() -> None:
    behavioural = make_study(interventions=(("BEHAVIORAL", "Coaching"),))
    supplement = make_study(
        interventions=(("DIETARY_SUPPLEMENT", "Vitamin D"),)
    )

    assert reasons_for(behavioural) == (ExclusionReason.NO_DRUG_INTERVENTION,)
    assert reasons_for(supplement) == (ExclusionReason.NO_DRUG_INTERVENTION,)


def test_screen_does_not_count_placebo_as_a_drug_intervention() -> None:
    study = make_study(interventions=(("DRUG", "Matching Placebo"),))

    assert reasons_for(study) == (ExclusionReason.NO_DRUG_INTERVENTION,)


def test_screen_accepts_biological_intervention() -> None:
    study = make_study(interventions=(("BIOLOGICAL", "Insulin glargine"),))

    screening = screen_peers([study], TYPE_2_DIABETES_PEER_CRITERIA)

    assert screening.peers == (study,)


def test_screen_drops_prevention_trial() -> None:
    study = make_study(primary_purpose="PREVENTION")

    assert reasons_for(study) == (ExclusionReason.NOT_TREATMENT_PURPOSE,)


def test_screen_treats_missing_registry_fields_as_not_meeting_criteria() -> (
    None
):
    study = make_study(condition_mesh=(), primary_purpose=None)

    assert reasons_for(study) == (
        ExclusionReason.MISSING_TARGET_CONDITION,
        ExclusionReason.NOT_TREATMENT_PURPOSE,
    )


def test_screen_keeps_search_order_of_peers() -> None:
    studies = [make_study(nct_id=f"NCT0000000{index}") for index in (3, 1, 2)]

    screening = screen_peers(studies, TYPE_2_DIABETES_PEER_CRITERIA)

    assert [study.nct_id for study in screening.peers] == [
        "NCT00000003",
        "NCT00000001",
        "NCT00000002",
    ]


def test_screen_of_empty_search_is_empty() -> None:
    screening = screen_peers([], TYPE_2_DIABETES_PEER_CRITERIA)

    assert screening.peers == ()
    assert screening.excluded == ()


def test_drug_class_from_intervention_name() -> None:
    study = make_study(interventions=(("DRUG", "Canagliflozin 100 mg"),))

    assert classify_drug_classes(study) == {DrugClass.SGLT2_INHIBITOR}


def test_drug_class_from_development_code_and_mesh_term() -> None:
    by_code = make_study(interventions=(("DRUG", "LY2189265"),))
    by_mesh = make_study(
        interventions=(("DRUG", "Study drug"),),
        intervention_mesh=("Insulin, Isophane",),
    )

    assert classify_drug_classes(by_code) == {DrugClass.GLP1_RECEPTOR_AGONIST}
    assert classify_drug_classes(by_mesh) == {DrugClass.INSULIN}


def test_drug_class_covers_combination_and_ignores_placebo_arms() -> None:
    study = make_study(
        interventions=(
            ("DRUG", "Sitagliptin plus metformin"),
            ("DRUG", "Placebo to insulin"),
        )
    )

    assert classify_drug_classes(study) == {
        DrugClass.DPP4_INHIBITOR,
        DrugClass.BIGUANIDE,
    }


def test_unknown_drug_has_no_class() -> None:
    study = make_study(interventions=(("DRUG", "Compound XYZ-123"),))

    assert classify_drug_classes(study) == frozenset()
