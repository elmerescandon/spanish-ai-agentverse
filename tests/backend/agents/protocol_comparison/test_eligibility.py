"""Tests for turning an LLM's reading of eligibility text into values."""

import pytest

from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.agents.protocol_comparison.eligibility import (
    ComparisonOperator,
    CriterionScope,
    LabLimitReply,
    LabPredicate,
    LabReading,
    LabVariable,
    RejectionReason,
    build_lab_prompt,
    clean_registry_text,
    interpret_reply,
    reading_cache_key,
)

RAW_TEXT = (
    "Inclusion Criteria\n\n"
    "1. HbA1c \\>= 6.5% and \\<= 11% obtained at screening visit\n\n"
    "Exclusion Criteria:\n\n"
    "1. ALT \\> 3 x ULN at screening\n"
    "2. eGFR \\< 30 mL/min/1.73 m2\n"
)
TEXT = clean_registry_text(RAW_TEXT)


def predicate(
    variable: LabVariable,
    operator: ComparisonOperator,
    value: float,
    unit: str,
    scope: CriterionScope,
    source_text: str,
) -> LabPredicate:
    return LabPredicate(
        variable=variable,
        operator=operator,
        value=value,
        unit=unit,
        scope=scope,
        source_text=source_text,
    )


HBA1C_FLOOR = predicate(
    LabVariable.HBA1C,
    ComparisonOperator.GREATER_OR_EQUAL,
    6.5,
    "%",
    CriterionScope.INCLUSION,
    "HbA1c >= 6.5% and <= 11%",
)
HBA1C_CEILING = predicate(
    LabVariable.HBA1C,
    ComparisonOperator.LESS_OR_EQUAL,
    11,
    "%",
    CriterionScope.INCLUSION,
    "HbA1c >= 6.5% and <= 11%",
)
ALT_LIMIT = predicate(
    LabVariable.ALT,
    ComparisonOperator.GREATER,
    3,
    "x ULN",
    CriterionScope.EXCLUSION,
    "ALT > 3 x ULN",
)
EGFR_LIMIT = predicate(
    LabVariable.EGFR,
    ComparisonOperator.LESS,
    30,
    "mL/min/1.73 m2",
    CriterionScope.EXCLUSION,
    "eGFR < 30 mL/min/1.73 m2",
)


def read(*predicates: LabPredicate, text: str = TEXT) -> LabReading:
    return interpret_reply(
        "NCT-T", text, LabLimitReply(predicates=list(predicates))
    )


def test_clean_text_removes_the_registry_backslash_escapes() -> None:
    assert "HbA1c >= 6.5% and <= 11%" in TEXT
    assert "\\" not in TEXT


def test_inclusion_range_gives_lower_and_upper_hba1c_bounds() -> None:
    values = read(HBA1C_FLOOR, HBA1C_CEILING).values

    assert values[DimensionId.HBA1C_LOWER_BOUND].value == 6.5
    assert values[DimensionId.HBA1C_UPPER_BOUND].value == 11.0
    assert "HbA1c >= 6.5% and <= 11%" in (
        values[DimensionId.HBA1C_LOWER_BOUND].source
    )


def test_exclusion_above_a_value_is_an_upper_bound() -> None:
    text = "Exclusion: HbA1c > 10.5% at screening"
    excluded_above = predicate(
        LabVariable.HBA1C,
        ComparisonOperator.GREATER,
        10.5,
        "%",
        CriterionScope.EXCLUSION,
        "HbA1c > 10.5%",
    )

    values = read(excluded_above, text=text).values

    assert values[DimensionId.HBA1C_UPPER_BOUND].value == 10.5
    assert DimensionId.HBA1C_LOWER_BOUND not in values


def test_hba1c_in_mmol_per_mol_is_converted_to_percent() -> None:
    text = "HbA1c >= 53 mmol/mol"
    in_mmol = predicate(
        LabVariable.HBA1C,
        ComparisonOperator.GREATER_OR_EQUAL,
        53,
        "mmol/mol",
        CriterionScope.INCLUSION,
        "HbA1c >= 53 mmol/mol",
    )

    values = read(in_mmol, text=text).values

    # (53 / 10.929) + 2.15 = 7.0 (Stefan's conversion table)
    assert values[DimensionId.HBA1C_LOWER_BOUND].value == pytest.approx(
        7.0, abs=0.01
    )


def test_liver_and_kidney_exclusions_become_their_limits() -> None:
    values = read(ALT_LIMIT, EGFR_LIMIT).values

    assert values[DimensionId.ALT_AST_LIMIT].value == 3.0
    assert values[DimensionId.EGFR_CUTOFF].value == 30.0


def test_egfr_inclusion_floor_is_the_same_cutoff_as_an_exclusion() -> None:
    text = "eGFR >= 45 mL/min/1.73m2"
    floor = predicate(
        LabVariable.EGFR,
        ComparisonOperator.GREATER_OR_EQUAL,
        45,
        "mL/min/1.73m2",
        CriterionScope.INCLUSION,
        "eGFR >= 45 mL/min/1.73m2",
    )

    values = read(floor, text=text).values

    assert values[DimensionId.EGFR_CUTOFF].value == 45.0


def test_alt_in_absolute_units_is_rejected_not_guessed() -> None:
    text = "ALT > 120 U/L"
    absolute = predicate(
        LabVariable.ALT,
        ComparisonOperator.GREATER,
        120,
        "U/L",
        CriterionScope.EXCLUSION,
        "ALT > 120 U/L",
    )

    reading = read(absolute, text=text)

    assert DimensionId.ALT_AST_LIMIT not in reading.values
    assert [rejected.reason for rejected in reading.rejected] == [
        RejectionReason.UNSUPPORTED_UNIT
    ]


def test_quote_missing_from_the_text_is_rejected() -> None:
    invented = predicate(
        LabVariable.EGFR,
        ComparisonOperator.LESS,
        45,
        "mL/min/1.73 m2",
        CriterionScope.EXCLUSION,
        "eGFR < 45 mL/min/1.73 m2",
    )

    reading = read(invented)

    assert reading.values == {}
    assert reading.rejected[0].reason == RejectionReason.QUOTE_NOT_FOUND


def test_quote_matching_ignores_case_and_spacing() -> None:
    sloppy = predicate(
        LabVariable.ALT,
        ComparisonOperator.GREATER,
        3,
        "x ULN",
        CriterionScope.EXCLUSION,
        "alt >  3 X uln",
    )

    assert DimensionId.ALT_AST_LIMIT in read(sloppy).values


def test_several_values_for_one_dimension_keep_the_loosest() -> None:
    text = "HbA1c >= 7.0% (on metformin) or >= 7.5% (on insulin)"
    on_metformin = predicate(
        LabVariable.HBA1C,
        ComparisonOperator.GREATER_OR_EQUAL,
        7.0,
        "%",
        CriterionScope.INCLUSION,
        "HbA1c >= 7.0%",
    )
    on_insulin = predicate(
        LabVariable.HBA1C,
        ComparisonOperator.GREATER_OR_EQUAL,
        7.5,
        "%",
        CriterionScope.INCLUSION,
        ">= 7.5% (on insulin)",
    )

    values = read(on_insulin, on_metformin, text=text).values

    # A higher HbA1c floor is stricter, so the loosest floor is 7.0.
    assert values[DimensionId.HBA1C_LOWER_BOUND].value == 7.0


def test_empty_reply_gives_no_values() -> None:
    reading = read()

    assert (reading.values, reading.rejected) == ({}, ())


def test_prompt_contains_the_text_and_every_allowed_variable() -> None:
    prompt = build_lab_prompt(TEXT)

    assert "ALT > 3 x ULN at screening" in prompt
    for variable in LabVariable:
        assert f'"{variable.value}"' in prompt


def test_cache_key_changes_when_the_text_changes() -> None:
    assert reading_cache_key(TEXT) == reading_cache_key(TEXT)
    assert reading_cache_key(TEXT) != reading_cache_key(TEXT + " ")


@pytest.mark.parametrize(
    "unit",
    [
        "x ULN",
        "*ULN",
        "times the upper limit of normal",
        "times upper limits of normal",
        "times upper normal limit",
    ],
)
def test_liver_limits_accept_every_way_of_writing_uln(unit: str) -> None:
    text = f"ALT > 3 {unit}"
    limit = predicate(
        LabVariable.ALT,
        ComparisonOperator.GREATER,
        3,
        unit,
        CriterionScope.EXCLUSION,
        text,
    )

    assert read(limit, text=text).values[DimensionId.ALT_AST_LIMIT].value == 3


def test_hba1c_written_as_percent_in_words_is_accepted() -> None:
    text = "HbA1c >=6.5 percent (%)"
    floor = predicate(
        LabVariable.HBA1C,
        ComparisonOperator.GREATER_OR_EQUAL,
        6.5,
        "percent (%)",
        CriterionScope.INCLUSION,
        text,
    )

    values = read(floor, text=text).values

    assert values[DimensionId.HBA1C_LOWER_BOUND].value == 6.5
