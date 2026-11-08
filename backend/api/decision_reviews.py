"""Project durable review decisions into the final amendment report."""

from backend.api.schemas import RecommendationStatus, SavedDecisionReview
from backend.clients.protocol_db import (
    FieldChangeRecord,
    ProtocolReview,
    StoredField,
)

REVIEW_FIELD_PREFIX = "review_decision."


def saved_decisions(review: ProtocolReview) -> list[SavedDecisionReview]:
    return [
        SavedDecisionReview.model_validate_json(field.value)
        for field in review.fields
        if field.field.startswith(REVIEW_FIELD_PREFIX)
    ]


def reviewed_output(review: ProtocolReview) -> ProtocolReview:
    """Only currently accepted amendments enter the output, not old votes.

    The underlying store retains all votes for audit. The original parsed
    fields remain source facts; amendments appear separately in the report.
    """
    fields = [
        field
        for field in review.fields
        if not field.field.startswith(REVIEW_FIELD_PREFIX)
    ]
    changes = [
        change
        for change in review.changes
        if not change.field.startswith(REVIEW_FIELD_PREFIX)
    ]
    latest = {change.field: change for change in review.changes}
    for decision in saved_decisions(review):
        if decision.status != RecommendationStatus.ACCEPTED:
            continue
        amendment = decision.proposed_change
        event = latest[REVIEW_FIELD_PREFIX + decision.decision_id]
        fields.append(
            StoredField(
                field=f"Approved amendment: {amendment.path}",
                value=amendment.after,
                page=amendment.page,
            )
        )
        changes.append(
            FieldChangeRecord(
                change_id=event.change_id,
                field=amendment.path,
                old_value=amendment.before,
                new_value=amendment.after,
                decision_id=decision.decision_id,
                option_id=decision.option_id or "",
                rationale=amendment.rationale or "Accepted by reviewer",
                changed_at=event.changed_at,
            )
        )
    return ProtocolReview(
        protocol=review.protocol, fields=fields, changes=changes
    )
