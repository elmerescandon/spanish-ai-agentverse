"""A parsed protocol (ProtocolDocument) to use as the comparison draft."""

from datetime import date

from backend.agents.protocol_comparison.eligibility import (
    ComparisonOperator,
    CriterionScope,
    LabLimitReply,
    LabPredicate,
    LabVariable,
)
from backend.agents.protocol_comparison.logic import peer_query_for
from backend.shared.messages import (
    Citation,
    CitedValue,
    CriterionKind,
    EligibilityCriterion,
    InterventionArm,
    InterventionExtraction,
    InterventionType,
    PageText,
    ProtocolDocument,
    TrialDesignFacts,
    TrialPhase,
)

PROTOCOL_ID = "proto-draft"
REVIEW_DATE = date(2026, 11, 8)
DRAFT_NCT_ID = "NCT03170518"
HBA1C_CRITERION = "HbA1c of >=7.0% to <=10.5% at screening"
ALT_CRITERION = "ALT > 2 x ULN at screening"
HBA1C_REPLY = LabLimitReply(
    predicates=[
        LabPredicate(
            variable=LabVariable.HBA1C,
            operator=ComparisonOperator.LESS_OR_EQUAL,
            value=10.5,
            unit="%",
            scope=CriterionScope.INCLUSION,
            source_text="HbA1c of >=7.0% to <=10.5%",
        )
    ]
)


def cited[ValueT](value: ValueT, quote: str, page: int) -> CitedValue[ValueT]:
    return CitedValue(
        value=value, citation=Citation(page_number=page, quote=quote)
    )


def criterion(
    criterion_id: str, kind: CriterionKind, text: str
) -> EligibilityCriterion:
    return EligibilityCriterion(
        criterion_id=criterion_id,
        kind=kind,
        text=text,
        citation=Citation(page_number=12, quote=text),
    )


def parsed_protocol(
    criteria: list[EligibilityCriterion] | None = None,
) -> ProtocolDocument:
    """A parsed canagliflozin protocol for 10 to 17 year olds."""
    return ProtocolDocument(
        protocol_id=PROTOCOL_ID,
        title="my_trial",
        page_count=1,
        pages=[PageText(page_number=1, text="Protocol")],
        design=TrialDesignFacts(
            phase=cited(TrialPhase.PHASE3, "a Phase 3 study", 1),
            min_age_years=cited(10.0, "aged 10 to 17 years", 11),
            max_age_years=cited(17.0, "aged 10 to 17 years", 11),
            target_enrollment=cited(150, "approximately 150 participants", 3),
            nct_id=cited(DRAFT_NCT_ID, DRAFT_NCT_ID, 1),
        ),
        eligibility_criteria=criteria,
        interventions=InterventionExtraction(
            arms=[
                InterventionArm(
                    name="Canagliflozin 100 mg",
                    intervention_type=InterventionType.DRUG,
                    citation=Citation(page_number=4, quote="Canagliflozin"),
                ),
                InterventionArm(
                    name="Placebo",
                    intervention_type=InterventionType.DRUG,
                    is_control=True,
                    citation=Citation(page_number=4, quote="Placebo"),
                ),
            ]
        ),
    )


PEER_SEARCH = peer_query_for(parsed_protocol(), REVIEW_DATE)
