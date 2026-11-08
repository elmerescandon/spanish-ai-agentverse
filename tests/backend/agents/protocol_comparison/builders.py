"""Builders for registry study records used across comparison tests."""

from backend.clients.clinicaltrials_gov import StudyRecord


def make_study(
    nct_id: str = "NCT00000001",
    condition_mesh: tuple[str, ...] = ("Diabetes Mellitus, Type 2",),
    interventions: tuple[tuple[str, str], ...] = (("DRUG", "Dapagliflozin"),),
    intervention_mesh: tuple[str, ...] = (),
    primary_purpose: str | None = "TREATMENT",
    minimum_age: str | None = None,
    maximum_age: str | None = None,
    enrollment: tuple[int, str] | None = None,
    start_date: str | None = None,
    overall_status: str = "COMPLETED",
    eligibility_criteria: str | None = None,
) -> StudyRecord:
    """Build a minimal registry record; defaults describe a valid peer.

    enrollment is (count, type), e.g. (120, "ACTUAL").
    """
    design: dict[str, object] = {"phases": ["PHASE3"]}
    if primary_purpose is not None:
        design["designInfo"] = {"primaryPurpose": primary_purpose}
    if enrollment is not None:
        count, enrollment_type = enrollment
        design["enrollmentInfo"] = {"count": count, "type": enrollment_type}
    status: dict[str, object] = {"overallStatus": overall_status}
    if start_date is not None:
        status["startDateStruct"] = {"date": start_date}
    eligibility: dict[str, object] = {}
    if minimum_age is not None:
        eligibility["minimumAge"] = minimum_age
    if maximum_age is not None:
        eligibility["maximumAge"] = maximum_age
    if eligibility_criteria is not None:
        eligibility["eligibilityCriteria"] = eligibility_criteria
    return StudyRecord.model_validate(
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": nct_id,
                    "briefTitle": f"Study {nct_id}",
                },
                "statusModule": status,
                "designModule": design,
                "eligibilityModule": eligibility,
                "armsInterventionsModule": {
                    "interventions": [
                        {"type": kind, "name": name}
                        for kind, name in interventions
                    ]
                },
            },
            "derivedSection": {
                "conditionBrowseModule": {
                    "meshes": [{"term": term} for term in condition_mesh]
                },
                "interventionBrowseModule": {
                    "meshes": [{"term": term} for term in intervention_mesh]
                },
            },
        }
    )
