"""Tests for reading comparison dimensions from registry records."""

from datetime import date

import pytest

from backend.agents.protocol_comparison.dimensions import (
    DimensionId,
    profile_registry_study,
)
from backend.agents.protocol_comparison.rules import DrugClass
from tests.backend.agents.protocol_comparison.builders import make_study


def test_profile_reads_age_limits_in_years_with_their_source() -> None:
    study = make_study(minimum_age="10 Years", maximum_age="17 Years")

    values = profile_registry_study(study).values

    assert values[DimensionId.MINIMUM_AGE].value == 10.0
    assert values[DimensionId.MAXIMUM_AGE].value == 17.0
    assert "10 Years" in values[DimensionId.MINIMUM_AGE].source


@pytest.mark.parametrize(
    ("registry_age", "expected_years"),
    [("18 Months", 1.5), ("52 Weeks", 1.0), ("365 Days", 1.0)],
)
def test_profile_converts_age_units_to_years(
    registry_age: str, expected_years: float
) -> None:
    study = make_study(minimum_age=registry_age)

    values = profile_registry_study(study).values

    assert values[DimensionId.MINIMUM_AGE].value == pytest.approx(
        expected_years, abs=0.01
    )


def test_profile_skips_age_it_cannot_read() -> None:
    study = make_study(minimum_age="N/A")

    values = profile_registry_study(study).values

    assert DimensionId.MINIMUM_AGE not in values


def test_profile_skips_values_the_record_does_not_state() -> None:
    values = profile_registry_study(make_study()).values

    assert values == {}


def test_profile_reads_enrollment_and_says_whether_it_is_actual() -> None:
    study = make_study(enrollment=(122, "ACTUAL"))

    values = profile_registry_study(study).values

    enrollment = values[DimensionId.ENROLLMENT]
    assert enrollment.value == 122.0
    assert "ACTUAL" in enrollment.source


@pytest.mark.parametrize(
    ("registry_date", "expected"),
    [("2016-06-22", date(2016, 6, 22)), ("2012-05", date(2012, 5, 1))],
)
def test_profile_reads_start_date_at_day_or_month_precision(
    registry_date: str, expected: date
) -> None:
    study = make_study(start_date=registry_date)

    assert profile_registry_study(study).start_date == expected


def test_profile_without_start_date_has_none() -> None:
    assert profile_registry_study(make_study()).start_date is None


def test_profile_carries_drug_classes() -> None:
    study = make_study(interventions=(("DRUG", "Canagliflozin"),))

    profile = profile_registry_study(study)

    assert profile.drug_classes == frozenset({DrugClass.SGLT2_INHIBITOR})
    assert profile.trial_id == "NCT00000001"


def test_profile_names_drugs_including_development_codes() -> None:
    study = make_study(
        interventions=(
            ("DRUG", "LY2189265"),
            ("DRUG", "Metformin"),
            ("DRUG", "Placebo for metformin"),
        )
    )

    profile = profile_registry_study(study)

    assert profile.drugs == frozenset({"dulaglutide", "metformin"})


@pytest.mark.parametrize(
    ("overall_status", "is_ongoing"),
    [
        ("COMPLETED", False),
        ("TERMINATED", False),
        ("RECRUITING", True),
        ("ACTIVE_NOT_RECRUITING", True),
    ],
)
def test_profile_marks_trials_still_running_as_ongoing(
    overall_status: str, is_ongoing: bool
) -> None:
    study = make_study(overall_status=overall_status)

    assert profile_registry_study(study).is_ongoing is is_ongoing
