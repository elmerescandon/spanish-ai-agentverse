"""Unit tests for the shared parser contract and serialization helpers."""

import pytest
from pydantic import ValidationError

from backend.shared.messages import (
    Citation,
    CitedValue,
    CriterionKind,
    EligibilityCriterion,
    PageText,
    ParseProtocolResponse,
    ProtocolDocument,
    TrialDesignFacts,
    decode_criteria,
    encode_criteria,
)

SAMPLE_PAGE_NUMBER = 4
SAMPLE_PAGE_COUNT = 1
SAMPLE_TARGET_ENROLLMENT = 240


def test_criteria_round_trip_through_json() -> None:
    criteria = [
        EligibilityCriterion(
            criterion_id="IN-01",
            kind=CriterionKind.INCLUSION,
            text="Adults aged 18 to 75 years with type 2 diabetes mellitus.",
            citation=Citation(
                page_number=SAMPLE_PAGE_NUMBER,
                quote=(
                    "Adults aged 18 to 75 years with type 2 diabetes mellitus."
                ),
                is_verified=True,
            ),
        ),
        EligibilityCriterion(
            criterion_id="EX-01",
            kind=CriterionKind.EXCLUSION,
            text=(
                "History of diabetic ketoacidosis within 6 months "
                "prior to screening."
            ),
            citation=None,
        ),
    ]

    encoded = encode_criteria(criteria)
    decoded = decode_criteria(encoded)

    assert decoded == criteria


def test_decode_criteria_rejects_malformed_json() -> None:
    with pytest.raises(ValidationError):
        decode_criteria("{not valid json")


def test_cited_value_validates_typed_value() -> None:
    citation = Citation(
        page_number=SAMPLE_PAGE_NUMBER,
        quote="Approximately 240 participants will be randomized.",
    )
    valid_item = CitedValue[int](
        value=SAMPLE_TARGET_ENROLLMENT, citation=citation
    )
    assert valid_item.value == SAMPLE_TARGET_ENROLLMENT

    with pytest.raises(ValidationError):
        CitedValue[int].model_validate(
            {"value": "abc", "citation": citation.model_dump()}
        )


def test_design_facts_accepts_all_fields_missing() -> None:
    facts = TrialDesignFacts()

    assert facts.phase is None
    assert facts.allocation is None
    assert facts.intervention_model is None
    assert facts.masking is None
    assert facts.target_enrollment is None
    assert facts.arm_count is None
    assert facts.min_age_years is None
    assert facts.max_age_years is None
    assert facts.accepts_healthy_volunteers is None
    assert facts.site_count is None
    assert facts.country_count is None
    assert facts.has_data_monitoring_committee is None
    assert facts.nct_id is None


def test_protocol_document_distinguishes_failed_facet_from_empty_facet() -> (
    None
):
    document = ProtocolDocument(
        protocol_id="proto-001",
        title="Phase 3 Study in Type 2 Diabetes",
        page_count=SAMPLE_PAGE_COUNT,
        pages=[
            PageText(page_number=SAMPLE_PAGE_COUNT, text="Protocol cover page")
        ],
        design=None,
        eligibility_criteria=[],
        sections=None,
        endpoints=[],
        schedule=None,
        statistics=None,
        extraction_warnings=[],
    )

    restored = ProtocolDocument.model_validate_json(document.model_dump_json())

    assert restored.design is None
    assert restored.eligibility_criteria == []
    assert restored.sections is None
    assert restored.endpoints == []
    assert restored.schedule is None
    assert restored.statistics is None


def test_parse_response_envelope_round_trips() -> None:
    document = ProtocolDocument(
        protocol_id="proto-002",
        title="Glycemic Control Trial",
        page_count=SAMPLE_PAGE_COUNT,
        pages=[PageText(page_number=SAMPLE_PAGE_COUNT, text="Page 1 text")],
    )
    envelope = ParseProtocolResponse(
        review_id="rev-123",
        document_json=document.model_dump_json(),
    )

    raw_envelope = envelope.json()
    restored_envelope = ParseProtocolResponse.parse_raw(raw_envelope)
    restored_document = ProtocolDocument.model_validate_json(
        restored_envelope.document_json
    )

    assert restored_envelope.review_id == "rev-123"
    assert restored_document == document


def test_age_inclusivity_is_unknown_by_default() -> None:
    facts = TrialDesignFacts()

    assert facts.is_min_age_inclusive is None
    assert facts.is_max_age_inclusive is None
