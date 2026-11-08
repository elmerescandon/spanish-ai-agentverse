"""Unit tests for Family REG deterministic checks (REG-24 to REG-29)."""

from backend.agents.completeness.checks.registration import (
    check_reg_24,
    check_reg_25,
    check_reg_26,
    check_reg_27,
    check_reg_28,
    check_reg_29,
)
from backend.shared.messages import (
    EndpointKind,
    RuleStatus,
    ScaleDirection,
)
from tests.backend.agents.completeness.factories import (
    make_document,
    make_endpoint,
    make_profile,
)


def test_reg_24_passes_when_primary_endpoint_has_metric_and_timeframe() -> (
    None
):
    doc = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
                time_frame="Baseline and Week 26",
                kind=EndpointKind.PRIMARY,
            )
        ]
    )

    outcome = check_reg_24(doc, make_profile())

    assert outcome.status == RuleStatus.PASSED
    assert len(outcome.evidence) == 1
    assert outcome.needs_second_opinion is False


def test_reg_24_fires_when_primary_endpoint_missing_or_lacks_timeframe() -> (
    None
):
    no_primary = make_document(
        endpoints=[
            make_endpoint(
                description="Change in fasting plasma glucose",
                time_frame="Week 26",
                kind=EndpointKind.SECONDARY,
            )
        ]
    )
    missing_tf = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
                time_frame=None,
                kind=EndpointKind.PRIMARY,
            )
        ]
    )

    outcome_none = check_reg_24(no_primary, make_profile())
    outcome_no_tf = check_reg_24(missing_tf, make_profile())

    assert outcome_none.status == RuleStatus.FIRED
    assert outcome_none.needs_second_opinion is True
    assert outcome_no_tf.status == RuleStatus.FIRED
    assert outcome_no_tf.needs_second_opinion is True
    assert len(outcome_no_tf.evidence) == 1


def test_reg_24_cannot_assess_when_endpoints_facet_failed() -> None:
    doc = make_document(endpoints=None)

    outcome = check_reg_24(doc, make_profile())

    assert outcome.status == RuleStatus.CANNOT_ASSESS


def test_reg_25_fires_on_bundled_variables_and_passes_single_metric() -> None:
    bundled = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c and FPG at Week 26",
            )
        ]
    )
    single = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c at Week 26",
            )
        ]
    )

    fired = check_reg_25(bundled, make_profile())
    passed = check_reg_25(single, make_profile())

    assert fired.status == RuleStatus.FIRED
    assert "HbA1c and FPG" in fired.finding
    assert len(fired.evidence) == 1
    assert passed.status == RuleStatus.PASSED


def test_reg_26_fires_on_directional_wording_and_passes_neutral() -> None:
    directional = make_document(
        endpoints=[
            make_endpoint(
                description="Reduction in HbA1c from baseline to Week 26",
            )
        ]
    )
    neutral = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c at Week 26",
            )
        ]
    )

    fired = check_reg_26(directional, make_profile())
    passed = check_reg_26(neutral, make_profile())

    assert fired.status == RuleStatus.FIRED
    assert "Reduction" in fired.finding
    assert len(fired.evidence) == 1
    assert passed.status == RuleStatus.PASSED


def test_reg_27_fires_on_vague_timeframe_and_passes_concrete_week() -> None:
    vague = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
                time_frame="Until end of treatment",
            )
        ]
    )
    concrete = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
                time_frame="Baseline and Week 26",
            )
        ]
    )

    fired = check_reg_27(vague, make_profile())
    passed = check_reg_27(concrete, make_profile())

    assert fired.status == RuleStatus.FIRED
    assert "Until end of treatment" in fired.finding
    assert len(fired.evidence) == 1
    assert passed.status == RuleStatus.PASSED


def test_reg_28_fires_on_bundled_timepoints_or_missing_baseline() -> None:
    bundled_times = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
                time_frame="Week 12, Week 26, and Week 52",
            )
        ]
    )
    no_baseline = make_document(
        endpoints=[
            make_endpoint(
                description="Change in HbA1c",
                time_frame="Week 26",
            )
        ]
    )
    valid_change = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
                time_frame="Baseline to Week 26",
            )
        ]
    )

    fired_bundled = check_reg_28(bundled_times, make_profile())
    fired_no_base = check_reg_28(no_baseline, make_profile())
    passed = check_reg_28(valid_change, make_profile())

    assert fired_bundled.status == RuleStatus.FIRED
    assert len(fired_bundled.evidence) == 1
    assert fired_no_base.status == RuleStatus.FIRED
    assert passed.status == RuleStatus.PASSED


def test_reg_29_fires_on_incomplete_scale_and_passes_complete_scale() -> None:
    incomplete_scale = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in DTSQ total score",
                scale_name="DTSQ",
                scale_min=0.0,
                scale_max=None,
                scale_better_direction=None,
            )
        ]
    )
    complete_scale = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in DTSQ total score",
                scale_name="DTSQ",
                scale_min=0.0,
                scale_max=36.0,
                scale_better_direction=ScaleDirection.HIGHER,
            )
        ]
    )
    non_scale = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
            )
        ]
    )

    fired = check_reg_29(incomplete_scale, make_profile())
    passed = check_reg_29(complete_scale, make_profile())
    not_app = check_reg_29(non_scale, make_profile())

    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True
    assert "scale_max" in fired.finding
    assert passed.status == RuleStatus.PASSED
    assert not_app.status == RuleStatus.NOT_APPLICABLE


def test_reg_checks_collect_multiple_offenders_and_cap_at_five() -> None:
    """REG-25..28 collect all offending endpoints and cap at 5."""
    six_directional = make_document(
        endpoints=[
            make_endpoint(
                description=f"Reduction in metric {idx} at Week 26",
                page_number=idx,
            )
            for idx in range(1, 7)
        ]
    )
    outcome_26 = check_reg_26(six_directional, make_profile())
    assert outcome_26.status == RuleStatus.FIRED
    assert "Reduction in metric 1" in outcome_26.finding
    assert "Reduction in metric 5" in outcome_26.finding
    assert "and 1 more" in outcome_26.finding
    assert len(outcome_26.evidence) == 5

    two_vague = make_document(
        endpoints=[
            make_endpoint(
                description="Outcome A", time_frame="During the study"
            ),
            make_endpoint(
                description="Outcome B", time_frame="End of treatment"
            ),
        ]
    )
    outcome_27 = check_reg_27(two_vague, make_profile())
    assert outcome_27.status == RuleStatus.FIRED
    assert "Outcome A" in outcome_27.finding
    assert "Outcome B" in outcome_27.finding
    assert len(outcome_27.evidence) == 2
