"""Typed rule catalogue models and validating TOML loader for completeness."""

import tomllib
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    model_validator,
)

from backend.shared.messages import (
    CheckMethod,
    M11Heading,
    RuleFamily,
    RuleSeverity,
    SourceTier,
)

DEFAULT_RULES_PATH = Path(__file__).with_name("rules.toml")
MAX_RULE_TITLE_LENGTH = 60


class DetectionCode(StrEnum):
    """How a protocol exclusion rule is detected."""

    F = "F"
    P = "P"
    X = "X"
    J = "J"
    C = "C"


class RequiredInput(StrEnum):
    """External document or corpus required to evaluate a rule."""

    INVESTIGATORS_BROCHURE = "investigators_brochure"
    REGISTRY_RECORD = "registry_record"
    COMPARATOR_CORPUS = "comparator_corpus"


class ApplicabilityCondition(StrEnum):
    """Trial-profile condition that must hold for a rule to apply."""

    INTERVENTION_IS_DRUG = "INTERVENTION_IS_DRUG"
    DIABETES_TYPE_T1D = "DIABETES_TYPE_T1D"
    DIABETES_TYPE_T2D = "DIABETES_TYPE_T2D"
    CONTROL_IS_PLACEBO = "CONTROL_IS_PLACEBO"
    CONTROL_IS_ACTIVE = "CONTROL_IS_ACTIVE"
    IS_NON_INFERIORITY = "IS_NON_INFERIORITY"
    IS_ADD_ON = "IS_ADD_ON"
    DRUG_CLASS_IS_INSULIN = "DRUG_CLASS_IS_INSULIN"
    IS_RANDOMIZED = "IS_RANDOMIZED"
    IS_BLINDED = "IS_BLINDED"
    DRUG_CLASS_IS_SGLT2 = "DRUG_CLASS_IS_SGLT2"
    DRUG_CLASS_IS_INCRETIN = "DRUG_CLASS_IS_INCRETIN"
    DRUG_CLASS_IS_GLP1_RA = "DRUG_CLASS_IS_GLP1_RA"
    IS_AMENDED = "IS_AMENDED"
    IS_PHASE_3 = "IS_PHASE_3"
    IS_SINGLE_ARM = "IS_SINGLE_ARM"


class LibraryTag(StrEnum):
    """How an exclusion-library item fires (guidelines Part G).

    CORE fires when absent; CLASS fires when absent and the drug class
    matches; BREADTH fires when present without a stated rationale.
    """

    CORE = "CORE"
    CLASS = "CLASS"
    BREADTH = "BREADTH"


class RuleDefinition(BaseModel):
    """Immutable specification of one completeness or consistency rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    family: RuleFamily
    severity: RuleSeverity
    detection: tuple[DetectionCode, ...] = Field(min_length=1)
    applies_when: tuple[ApplicabilityCondition, ...] = ()
    needs_inputs: tuple[RequiredInput, ...] = ()
    sections: tuple[M11Heading, ...] = Field(min_length=1)
    check: CheckMethod
    title: str = Field(min_length=1, max_length=MAX_RULE_TITLE_LENGTH)
    flag_if: str = Field(min_length=1)
    fix: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_tier: SourceTier
    library_tag: LibraryTag | None = None

    @model_validator(mode="after")
    def _validate_rule_invariants(self) -> Self:
        for field_name in ("id", "title", "flag_if", "fix", "source"):
            value = getattr(self, field_name)
            if not value.strip():
                raise ValueError(
                    f"rule '{self.id}' field '{field_name}' must be "
                    f"non-blank, got {value!r}"
                )
        expected_prefix = f"{self.family}-"
        if not self.id.startswith(expected_prefix):
            raise ValueError(
                f"rule '{self.id}' prefix must match family "
                f"'{self.family}' (expected '{expected_prefix}...')"
            )
        if (
            set(self.detection) == {DetectionCode.J}
            and self.check == CheckMethod.DETERMINISTIC
        ):
            raise ValueError(
                f"rule '{self.id}' has detection=['J'] only and must use "
                "check='judgement', got 'deterministic'"
            )
        is_library_rule = self.family == RuleFamily.EX
        if is_library_rule != (self.library_tag is not None):
            raise ValueError(
                f"rule '{self.id}' library_tag must be set exactly when "
                f"family is EX, got family={self.family} "
                f"library_tag={self.library_tag}"
            )
        return self


class RuleCatalogue(BaseModel):
    """Immutable collection of validated completeness rules indexed by ID."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: tuple[RuleDefinition, ...] = Field(min_length=1)
    _by_id: dict[str, RuleDefinition] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _build_index_and_check_unique_ids(self) -> Self:
        index: dict[str, RuleDefinition] = {}
        duplicates: list[str] = []
        for rule in self.rules:
            if rule.id in index and rule.id not in duplicates:
                duplicates.append(rule.id)
            index[rule.id] = rule
        if duplicates:
            raise ValueError(
                f"duplicate rule id(s) in catalogue: {duplicates}"
            )
        self._by_id = index
        return self

    def get(self, rule_id: str) -> RuleDefinition:
        """Return the rule for rule_id, or raise KeyError if not found."""
        try:
            return self._by_id[rule_id]
        except KeyError as error:
            raise KeyError(
                f"rule_id {rule_id!r} not found in RuleCatalogue"
            ) from error


def _parse_rule_catalogue_file(path: Path) -> RuleCatalogue:
    raw_data = tomllib.loads(path.read_text(encoding="utf-8"))
    extra_top_keys = set(raw_data) - {"rule"}
    if extra_top_keys:
        raise ValueError(
            f"expected only [[rule]] entries in {path}, got top-level "
            f"keys {sorted(extra_top_keys)}"
        )
    raw_rules = raw_data.get("rule")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError(
            f"expected a non-empty list of [[rule]] entries in {path}"
        )

    parsed_rules: list[RuleDefinition] = []
    for index, entry in enumerate(raw_rules):
        rule_label = (
            entry.get("id", f"<entry #{index + 1}>")
            if isinstance(entry, dict)
            else f"<entry #{index + 1}>"
        )
        try:
            parsed_rules.append(RuleDefinition.model_validate(entry))
        except ValidationError as error:
            raise ValueError(
                f"invalid rule {rule_label!r} in {path}: {error}"
            ) from error

    try:
        return RuleCatalogue(rules=tuple(parsed_rules))
    except ValidationError as error:
        raise ValueError(
            f"invalid rule catalogue in {path}: {error}"
        ) from error


@cache
def _load_default_catalogue() -> RuleCatalogue:
    return _parse_rule_catalogue_file(DEFAULT_RULES_PATH)


def load_rule_catalogue(path: Path = DEFAULT_RULES_PATH) -> RuleCatalogue:
    """Load and validate the completeness rule catalogue from a TOML file."""
    if path.resolve() == DEFAULT_RULES_PATH.resolve():
        return _load_default_catalogue()
    return _parse_rule_catalogue_file(path)
