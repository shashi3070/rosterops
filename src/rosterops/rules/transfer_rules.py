"""Group E — Transfers and assignments rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = [
    "TRF_001",
    "TRF_002",
    "TRF_003",
    "TRF_004",
    "TRF_005",
    "TRF_006",
    "TRF_007",
    "TRF_008",
    "TRF_009",
]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_P = frozenset({InputMode.PROCESS})
_GROUP = "transfer"

TRF_001 = register_rule(
    id="TRF-001",
    name="Transfer references a valid employee",
    description="A transfer naming an unknown employee is flagged as an unresolved identity.",
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

TRF_002 = register_rule(
    id="TRF-002",
    name="Transfer source matches the effective assignment",
    description=(
        "The transfer's stated from-territory must match the employee's effective "
        "assignment immediately before the event date; mismatches are flagged."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

TRF_003 = register_rule(
    id="TRF-003",
    name="Transfer source and destination differ",
    description=(
        "A transfer whose source and destination territories are identical is a "
        "potential no-op or invalid transfer; configurable severity per policy."
    ),
    default_severity=Severity.WARNING,
    modes=_P,
    group=_GROUP,
)

TRF_004 = register_rule(
    id="TRF-004",
    name="Destination territory exists",
    description="The transfer destination must exist in the territory master when one is loaded.",
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

TRF_005 = register_rule(
    id="TRF-005",
    name="Transfer date is valid for the employee",
    description=(
        "A transfer effective before employment begins or after termination is "
        "flagged with both dates."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

TRF_006 = register_rule(
    id="TRF-006",
    name="Conflicting transfers are detected",
    description=(
        "Overlapping or same-date permanent transfers without an unambiguous order "
        "are flagged rather than resolved by row order."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

TRF_007 = register_rule(
    id="TRF-007",
    name="Assignment state after transfer is consistent",
    description=(
        "After applying a permanent transfer, the resulting assignment state must "
        "not contain incompatible primaries or contradictory intervals."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

TRF_008 = register_rule(
    id="TRF-008",
    name="Transfer counts reconcile (1 event = 1 out + 1 in)",
    description=(
        "Each internal transfer counts as one transfer event, one transfer-out "
        "from the source territory, and one transfer-in to the destination — never "
        "two transfer events."
    ),
    default_severity=Severity.INFO,
    modes=_P,
    group=_GROUP,
)

TRF_009 = register_rule(
    id="TRF-009",
    name="Multiple-territory assignments respect policy",
    description=(
        "Employees holding several territories are validated against configured "
        "multi-territory and primary-territory policy, not against a global "
        "one-territory assumption."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
    params={"max_territories_per_employee": int},
)
