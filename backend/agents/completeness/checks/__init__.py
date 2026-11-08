"""Registry of code checks, one per deterministic rule ID.

Each check reads the ProtocolDocument and the trial profile and returns a
CheckOutcome. A rule with no entry here is reported as cannot_assess.
"""

from collections.abc import Mapping

from backend.agents.completeness.checks.consistency import CONSISTENCY_CHECKS
from backend.agents.completeness.checks.diabetes import DIABETES_CHECKS
from backend.agents.completeness.checks.eligibility import (
    ELIGIBILITY_CHECKS,
)
from backend.agents.completeness.checks.estimands import ESTIMAND_CHECKS
from backend.agents.completeness.checks.prechecks import (
    JUDGEMENT_PRECHECKS,
    JudgementPrecheck,
)
from backend.agents.completeness.checks.registration import REGISTRATION_CHECKS
from backend.agents.completeness.checks.structure import STRUCTURE_CHECKS
from backend.agents.completeness.logic import DeterministicCheck

__all__ = [
    "DETERMINISTIC_CHECKS",
    "JUDGEMENT_PRECHECKS",
    "JudgementPrecheck",
]

DETERMINISTIC_CHECKS: Mapping[str, DeterministicCheck] = {
    **REGISTRATION_CHECKS,
    **ESTIMAND_CHECKS,
    **CONSISTENCY_CHECKS,
    **DIABETES_CHECKS,
    **ELIGIBILITY_CHECKS,
    **STRUCTURE_CHECKS,
}
