"""Registry of code checks, one per deterministic rule ID.

Each check reads the ProtocolDocument and the trial profile and returns a
CheckOutcome. A rule with no entry here is reported as cannot_assess.
"""

from collections.abc import Mapping

from backend.agents.completeness.logic import DeterministicCheck

DETERMINISTIC_CHECKS: Mapping[str, DeterministicCheck] = {}
