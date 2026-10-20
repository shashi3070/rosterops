"""Group J — Manager hierarchy and organizational structure rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = ["ORG_001", "ORG_002", "ORG_003", "ORG_004", "ORG_005"]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_GROUP = "hierarchy"

ORG_001 = register_rule(
    id="ORG-001",
    name="Manager exists",
    description=(
        "A manager_id referencing an employee absent from the employee or manager "
        "master is flagged."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

ORG_002 = register_rule(
    id="ORG-002",
    name="No self-management",
    description="An employee whose manager_id equals their own employee_id is flagged.",
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

ORG_003 = register_rule(
    id="ORG-003",
    name="No reporting cycles",
    description=(
        "Reporting cycles (including two-node cycles) are flagged and the cycle "
        "members are named in the finding."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

ORG_004 = register_rule(
    id="ORG-004",
    name="Manager effective for the relevant date",
    description=(
        "When policy requires an active manager, a manager whose employment ended "
        "before the reporting relationship is flagged."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
)

ORG_005 = register_rule(
    id="ORG-005",
    name="Org relationships agree with territory hierarchy",
    description=(
        "Assignments whose region/district do not match their territory's region/"
        "district are flagged where the configured hierarchy requires a match."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
)
