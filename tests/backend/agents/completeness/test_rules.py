"""Tests for the completeness rule catalogue and validating TOML loader."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.agents.completeness.rules import (
    DEFAULT_RULES_PATH,
    MAX_RULE_TITLE_LENGTH,
    ApplicabilityCondition,
    DetectionCode,
    LibraryTag,
    RequiredInput,
    RuleCatalogue,
    RuleDefinition,
    load_rule_catalogue,
)
from backend.shared.messages import CheckMethod, RuleFamily, SourceTier

EXPECTED_DM_NUMBERS = (
    1,
    2,
    6,
    11,
    12,
    13,
    14,
    15,
    17,
    20,
    21,
    23,
    28,
    32,
    43,
    45,
)
EXPECTED_RULE_IDS: frozenset[str] = frozenset(
    [f"XS-{index:02d}" for index in range(1, 23)]
    + [f"EST-{index:02d}" for index in range(1, 27)]
    + [f"REG-{index:02d}" for index in range(1, 40)]
    + [f"DM-{index:02d}" for index in EXPECTED_DM_NUMBERS]
    + [f"ELQ-{index:02d}" for index in range(1, 24)]
    + [f"EX-{index:02d}" for index in range(1, 51)]
)
EXPECTED_FAMILY_COUNTS: dict[RuleFamily, int] = {
    RuleFamily.XS: 22,
    RuleFamily.EST: 26,
    RuleFamily.REG: 39,
    RuleFamily.DM: 16,
    RuleFamily.ELQ: 23,
    RuleFamily.EX: 50,
}


def _write_toml(tmp_path: Path, body: str) -> Path:
    toml_path = tmp_path / "rules.toml"
    toml_path.write_text(body, encoding="utf-8")
    return toml_path


def _valid_rule_toml_block(
    rule_id: str = "XS-05",
    family: str = "XS",
    severity: str = "S1",
    detection: str = '["X"]',
    applies_when: str = "[]",
    needs_inputs: str = "[]",
    sections: str = (
        '["OBJECTIVES_AND_ESTIMANDS", "ASSESSMENTS_AND_PROCEDURES"]'
    ),
    check: str = "deterministic",
    title: str = "Primary endpoint timepoint has no scheduled visit",
    flag_if: str = "Primary endpoint timepoint lacks a matching visit.",
    fix: str = "Add a scheduled visit at the primary endpoint timepoint.",
    source: str = "ICH M11 Template, Step 4",
    source_tier: str = "ich",
    extra_line: str = "",
) -> str:
    return (
        "[[rule]]\n"
        f'id = "{rule_id}"\n'
        f'family = "{family}"\n'
        f'severity = "{severity}"\n'
        f"detection = {detection}\n"
        f"applies_when = {applies_when}\n"
        f"needs_inputs = {needs_inputs}\n"
        f"sections = {sections}\n"
        f'check = "{check}"\n'
        f'title = "{title}"\n'
        f'flag_if = "{flag_if}"\n'
        f'fix = "{fix}"\n'
        f'source = "{source}"\n'
        f'source_tier = "{source_tier}"\n'
        f"{extra_line}"
    )


def test_default_rules_catalogue_loads_every_expected_rule() -> None:
    catalogue = load_rule_catalogue()

    assert isinstance(catalogue, RuleCatalogue)
    assert len(catalogue.rules) == len(EXPECTED_RULE_IDS)
    assert {rule.id for rule in catalogue.rules} == EXPECTED_RULE_IDS

    counts_by_family: dict[RuleFamily, int] = {}
    for rule in catalogue.rules:
        counts_by_family[rule.family] = (
            counts_by_family.get(rule.family, 0) + 1
        )
    assert counts_by_family == EXPECTED_FAMILY_COUNTS


def test_every_rule_has_valid_non_empty_fields_and_bounded_title() -> None:
    catalogue = load_rule_catalogue(DEFAULT_RULES_PATH)

    for rule in catalogue.rules:
        assert isinstance(rule, RuleDefinition)
        assert rule.title.strip()
        assert len(rule.title) <= MAX_RULE_TITLE_LENGTH
        assert rule.flag_if.strip()
        assert rule.fix.strip()
        assert rule.source.strip()
        assert len(rule.sections) >= 1
        assert len(rule.detection) >= 1
        if set(rule.detection) == {DetectionCode.J}:
            assert rule.check == CheckMethod.JUDGEMENT
        if rule.source_tier == SourceTier.DRAFT_GUIDANCE:
            assert "FDA draft guidance (non-binding)" in rule.source


def test_catalogue_get_returns_rule_and_raises_key_error_when_missing() -> (
    None
):
    catalogue = load_rule_catalogue()
    rule = catalogue.get("XS-05")
    assert rule.id == "XS-05"
    assert rule.family == RuleFamily.XS

    with pytest.raises(KeyError) as exc_info:
        catalogue.get("XS-999")
    assert "XS-999" in str(exc_info.value)


def test_catalogue_and_rule_models_are_frozen_and_check_enums() -> None:
    catalogue = load_rule_catalogue()
    xs_17 = catalogue.get("XS-17")
    assert xs_17.needs_inputs == (RequiredInput.INVESTIGATORS_BROCHURE,)
    assert xs_17.applies_when == (ApplicabilityCondition.INTERVENTION_IS_DRUG,)

    with pytest.raises(ValidationError):
        xs_17.title = "Mutated title"  # type: ignore[misc]


def test_loader_rejects_unknown_extra_field_with_rule_id(
    tmp_path: Path,
) -> None:
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(
            rule_id="XS-07", extra_line='unexpected_key = "bad"\n'
        ),
    )
    with pytest.raises(ValueError, match="XS-07"):
        load_rule_catalogue(path)


def test_loader_rejects_missing_required_field_with_rule_id(
    tmp_path: Path,
) -> None:
    incomplete_toml = (
        '[[rule]]\nid = "EST-02"\nfamily = "EST"\nseverity = "S1"\n'
    )
    path = _write_toml(tmp_path, incomplete_toml)
    with pytest.raises(ValueError, match="EST-02"):
        load_rule_catalogue(path)


def test_loader_rejects_duplicate_rule_ids(tmp_path: Path) -> None:
    content = (
        _valid_rule_toml_block(rule_id="XS-05")
        + "\n"
        + _valid_rule_toml_block(rule_id="XS-05")
    )
    path = _write_toml(tmp_path, content)
    with pytest.raises(ValueError, match="XS-05"):
        load_rule_catalogue(path)


def test_loader_rejects_id_prefix_not_matching_family(tmp_path: Path) -> None:
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(rule_id="REG-25", family="XS"),
    )
    with pytest.raises(ValueError, match="REG-25"):
        load_rule_catalogue(path)


def test_loader_rejects_empty_detection_with_rule_id(tmp_path: Path) -> None:
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(rule_id="DM-01", family="DM", detection="[]"),
    )
    with pytest.raises(ValueError, match="DM-01"):
        load_rule_catalogue(path)


def test_loader_rejects_j_only_rule_marked_deterministic(
    tmp_path: Path,
) -> None:
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(
            rule_id="EST-01",
            family="EST",
            detection='["J"]',
            check="deterministic",
        ),
    )
    with pytest.raises(ValueError, match="EST-01"):
        load_rule_catalogue(path)


def test_loader_rejects_title_exceeding_sixty_characters(
    tmp_path: Path,
) -> None:
    long_title = "A" * (MAX_RULE_TITLE_LENGTH + 1)
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(rule_id="XS-12", title=long_title),
    )
    with pytest.raises(ValueError, match="XS-12"):
        load_rule_catalogue(path)


def test_loader_rejects_invalid_enum_values_with_rule_id(
    tmp_path: Path,
) -> None:
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(
            rule_id="REG-27",
            family="REG",
            source_tier="not_a_real_tier",
        ),
    )
    with pytest.raises(ValueError, match="REG-27"):
        load_rule_catalogue(path)


def test_loader_rejects_empty_sections_and_blank_strings_with_rule_id(
    tmp_path: Path,
) -> None:
    empty_sections_path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(rule_id="XS-08", sections="[]"),
    )
    with pytest.raises(ValueError, match="XS-08"):
        load_rule_catalogue(empty_sections_path)

    blank_fix_path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(rule_id="XS-09", fix="   "),
    )
    with pytest.raises(ValueError, match="XS-09"):
        load_rule_catalogue(blank_fix_path)


def test_loader_requires_library_tag_on_exclusion_library_rules(
    tmp_path: Path,
) -> None:
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(
            rule_id="EX-03", family="EX", check="judgement"
        ),
    )
    with pytest.raises(ValueError, match="EX-03"):
        load_rule_catalogue(path)


def test_loader_rejects_library_tag_outside_exclusion_library(
    tmp_path: Path,
) -> None:
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(extra_line='library_tag = "CORE"\n'),
    )
    with pytest.raises(ValueError, match="XS-05"):
        load_rule_catalogue(path)


def test_loader_accepts_tagged_exclusion_library_rule(tmp_path: Path) -> None:
    path = _write_toml(
        tmp_path,
        _valid_rule_toml_block(
            rule_id="EX-03",
            family="EX",
            check="judgement",
            extra_line='library_tag = "CLASS"\n',
        ),
    )

    rule = load_rule_catalogue(path).get("EX-03")

    assert rule.library_tag == LibraryTag.CLASS


def test_exclusion_library_tags_and_class_conditions() -> None:
    library = [
        rule
        for rule in load_rule_catalogue().rules
        if rule.family == RuleFamily.EX
    ]
    tag_counts = {
        tag: sum(1 for rule in library if rule.library_tag == tag)
        for tag in LibraryTag
    }

    assert tag_counts == {
        LibraryTag.CORE: 27,
        LibraryTag.CLASS: 17,
        LibraryTag.BREADTH: 6,
    }
    for rule in library:
        if rule.library_tag == LibraryTag.CLASS:
            assert set(rule.applies_when) - {
                ApplicabilityCondition.DIABETES_TYPE_T2D
            }, rule.id
