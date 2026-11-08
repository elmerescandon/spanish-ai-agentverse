"""Builders for registry study records used across comparison tests."""

from backend.clients.clinicaltrials_gov import StudyRecord


def make_study(
    nct_id: str = "NCT00000001",
    condition_mesh: tuple[str, ...] = ("Diabetes Mellitus, Type 2",),
    interventions: tuple[tuple[str, str], ...] = (("DRUG", "Dapagliflozin"),),
    intervention_mesh: tuple[str, ...] = (),
    primary_purpose: str | None = "TREATMENT",
) -> StudyRecord:
    """Build a minimal registry record; defaults describe a valid peer."""
    design: dict[str, object] = {"phases": ["PHASE3"]}
    if primary_purpose is not None:
        design["designInfo"] = {"primaryPurpose": primary_purpose}
    return StudyRecord.model_validate(
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": nct_id,
                    "briefTitle": f"Study {nct_id}",
                },
                "statusModule": {"overallStatus": "COMPLETED"},
                "designModule": design,
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
