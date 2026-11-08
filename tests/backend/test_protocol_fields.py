"""Tests for turning analysis results into stored fields and offers."""

import pytest

from backend.agents.protocol_comparison.agent import ProtocolComparison
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.agents.protocol_comparison.step_data import to_step_data
from backend.api.protocol_fields import (
    ACCEPTABLE_FIELDS,
    MAX_FIELD_VALUE_CHARS,
    ChangeRejectedError,
    comparison_field,
    document_fields,
    format_number,
    match_offer,
    offered_values,
    starting_comparison_fields,
)
from backend.api.schemas import StepData
from backend.clients.protocol_db import OfferedValue
from backend.shared.messages import (
    Citation,
    CitedValue,
    CriterionKind,
    EligibilityCriterion,
    M11Heading,
    PageText,
    ProtocolDocument,
    ProtocolSection,
    StatisticalAssumptions,
    TrialDesignFacts,
    TrialPhase,
)
from tests.conftest import OFFERED_HBA1C_VALUES, flagged_demo_comparison

PAGE_TEXT = "Full page text that must never reach the database. " * 3
LONG_CRITERION = "x" * (MAX_FIELD_VALUE_CHARS + 1)
HBA1C_FIELD = comparison_field(DimensionId.HBA1C_UPPER_BOUND)


def _cited[ValueT](value: ValueT, page: int) -> CitedValue[ValueT]:
    return CitedValue[ValueT](
        value=value, citation=Citation(page_number=page, quote="quote")
    )


def _document() -> ProtocolDocument:
    return ProtocolDocument(
        protocol_id="proto-1",
        title="Trial",
        page_count=2,
        pages=[
            PageText(page_number=1, text=PAGE_TEXT),
            PageText(page_number=2, text=PAGE_TEXT),
        ],
        design=TrialDesignFacts(
            phase=_cited(TrialPhase.PHASE3, page=1),
            min_age_years=_cited(18.0, page=2),
            is_min_age_inclusive=True,
        ),
        statistics=StatisticalAssumptions(sample_size=_cited(200, page=2)),
        eligibility_criteria=[
            EligibilityCriterion(
                criterion_id="IN-05",
                kind=CriterionKind.INCLUSION,
                text="HbA1c >= 7.0% and <= 10.5%",
                citation=Citation(page_number=2, quote="HbA1c"),
            ),
            EligibilityCriterion(
                criterion_id="EX-09",
                kind=CriterionKind.EXCLUSION,
                text=LONG_CRITERION,
            ),
        ],
        sections=[
            ProtocolSection(
                heading=M11Heading.TRIAL_POPULATION,
                title="5 Trial Population",
                start_page=2,
                end_page=2,
                summary="A paragraph-sized summary of the section.",
                citation=Citation(page_number=2, quote="5 Trial"),
            )
        ],
    )


def _by_name(document: ProtocolDocument) -> dict[str, tuple[str, int | None]]:
    return {f.field: (f.value, f.page) for f in document_fields(document)}


def test_parsed_facts_become_short_named_fields_with_pages() -> None:
    fields = _by_name(_document())

    assert fields["design.phase"] == ("PHASE3", 1)
    assert fields["design.min_age_years"] == ("18", 2)
    assert fields["design.is_min_age_inclusive"] == ("true", None)
    assert fields["statistics.sample_size"] == ("200", 2)
    assert fields["eligibility.IN-05.text"] == (
        "HbA1c >= 7.0% and <= 10.5%",
        2,
    )
    assert fields["eligibility.IN-05.kind"] == ("INCLUSION", 2)
    assert fields["sections.1.title"] == ("5 Trial Population", 2)
    assert fields["sections.1.start_page"] == ("2", 2)


def test_page_text_summaries_and_long_values_are_not_stored() -> None:
    fields = document_fields(_document())

    values = [f.value for f in fields]
    assert all(len(value) <= MAX_FIELD_VALUE_CHARS for value in values)
    assert not any(PAGE_TEXT.strip() in value for value in values)
    assert "sections.1.summary" not in {f.field for f in fields}
    assert "eligibility.EX-09.text" not in {f.field for f in fields}


def test_field_names_are_stable_for_the_same_document() -> None:
    assert document_fields(_document()) == document_fields(_document())


def test_format_number_drops_a_trailing_zero_only() -> None:
    assert format_number(18.0) == "18"
    assert format_number(10.5) == "10.5"


@pytest.fixture
async def comparison() -> ProtocolComparison:
    return await flagged_demo_comparison()


@pytest.fixture
def peers_step(comparison: ProtocolComparison) -> StepData:
    return to_step_data(_document(), comparison)


def test_starting_fields_hold_the_draft_values_with_units(
    comparison: ProtocolComparison,
) -> None:
    fields = {
        f.field: f for f in starting_comparison_fields(comparison.results)
    }

    with_values = [r for r in comparison.results if r.draft_value]
    assert len(fields) == len(with_values)
    assert set(fields) <= ACCEPTABLE_FIELDS
    assert fields[HBA1C_FIELD].value == "11"
    assert fields[HBA1C_FIELD].unit == "%"


def test_every_value_option_on_the_peers_step_has_one_offer(
    comparison: ProtocolComparison, peers_step: StepData
) -> None:
    offers = offered_values(comparison.cards, peers_step)

    change_options = {
        option.option_id: option
        for decision in peers_step.decisions
        for option in decision.options
        if option.proposed_change is not None
    }
    assert sorted(o.option_id for o in offers) == sorted(change_options)
    assert {o.value for o in offers} == set(OFFERED_HBA1C_VALUES.values())
    for offer in offers:
        assert offer.field == HBA1C_FIELD
        assert offer.rationale == change_options[offer.option_id].rationale


def test_no_flag_means_nothing_is_offered(peers_step: StepData) -> None:
    assert offered_values((), peers_step) == []


OFFER = OfferedValue(HBA1C_FIELD, 10.5, "%", "d", "o", "in line with peers")


def test_offered_value_is_matched() -> None:
    assert match_offer(HBA1C_FIELD, 10.5, [OFFER]) == OFFER


@pytest.mark.parametrize(
    ("field", "value", "offers", "message"),
    [
        ("design.phase", 3.0, [OFFER], "expected field to be one of"),
        (HBA1C_FIELD, 10.5, [], "run the PEERS step"),
        (HBA1C_FIELD, 9.0, [OFFER], "expected one of the offered values"),
    ],
    ids=["field_not_changeable", "nothing_offered", "value_not_offered"],
)
def test_change_that_was_not_offered_is_rejected(
    field: str, value: float, offers: list[OfferedValue], message: str
) -> None:
    with pytest.raises(ChangeRejectedError, match=message):
        match_offer(field, value, offers)
