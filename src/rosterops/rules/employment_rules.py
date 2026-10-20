"""Group D — Employment lifecycle, hiring and termination rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = [
    "EMP_001",
    "EMP_002",
    "EMP_003",
    "EMP_004",
    "EMP_005",
    "EMP_006",
    "EMP_007",
    "EMP_008",
]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_P = frozenset({InputMode.PROCESS})
_GROUP = "employment"

EMP_001 = register_rule(
    id="EMP-001",
    name="Hire/rehire has valid identity and effective date",
    description=(
        "A hire or rehire event without a usable employee ID or a parseable "
        "effective date is flagged and not applied."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

EMP_002 = register_rule(
    id="EMP-002",
    name="Hire does not conflict with an active employment episode",
    description=(
        "Hiring an employee whose first employment episode is still active is "
        "flagged as a duplicate episode unless an approved employment-model "
        "exception applies."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

EMP_003 = register_rule(
    id="EMP-003",
    name="Termination references a valid active episode",
    description=(
        "A termination for an employee absent from all known employment history "
        "(baseline episodes or hire events) is flagged."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

EMP_004 = register_rule(
    id="EMP-004",
    name="Termination events are not duplicated",
    description=(
        "The same termination present twice across the file collection is "
        "flagged once and applied at most once."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

EMP_005 = register_rule(
    id="EMP-005",
    name="Post-termination events are controlled",
    description=(
        "Transfers, promotions, or leaves effective after termination are flagged "
        "with the conflicting dates unless an explicit rehire or correction "
        "justifies them."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

EMP_006 = register_rule(
    id="EMP-006",
    name="Final status agrees with lifecycle events",
    description=(
        "The resulting roster must not show an employee as Active after their "
        "employment interval ended; status and lifecycle events must agree."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

EMP_007 = register_rule(
    id="EMP-007",
    name="Rehire creates a distinct episode; prior end date preserved",
    description=(
        "A rehire opens a new employment episode and must not overwrite the prior "
        "episode's end date; both episodes remain linked to their events."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

EMP_008 = register_rule(
    id="EMP-008",
    name="Headcount uses defined employment semantics (leave ≠ termination)",
    description=(
        "Employment and field-coverage status are counted separately: leave is not "
        "a termination, and headcount formulas follow the configured employment "
        "semantics."
    ),
    default_severity=Severity.INFO,
    modes=_SP,
    group=_GROUP,
)
