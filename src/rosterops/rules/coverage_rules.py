"""Group I — Temporary coverage rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = ["COV_001", "COV_002", "COV_003", "COV_004", "COV_005"]

_P = frozenset({InputMode.PROCESS})
_GROUP = "coverage"

COV_001 = register_rule(
    id="COV-001",
    name="Coverage references valid employees and territories",
    description=(
        "A coverage record referencing an unknown covering employee, covered "
        "employee, or territory is flagged."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

COV_002 = register_rule(
    id="COV-002",
    name="Coverage interval valid",
    description="Temporary coverage ending before it starts, or unparseable, is flagged.",
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

COV_003 = register_rule(
    id="COV-003",
    name="Coverage linked to a valid absence when required",
    description=(
        "When the organization requires formal linkage, coverage claiming to cover "
        "a leave must reference a leave present in the loaded history; otherwise "
        "flagged or warned per configuration."
    ),
    default_severity=Severity.WARNING,
    modes=_P,
    group=_GROUP,
)

COV_004 = register_rule(
    id="COV-004",
    name="Concurrent coverage within configured capacity",
    description=(
        "A covering employee holding overlapping temporary coverages beyond the "
        "configured capacity is flagged with the intersecting interval."
    ),
    default_severity=Severity.WARNING,
    modes=_P,
    group=_GROUP,
)

COV_005 = register_rule(
    id="COV-005",
    name="Coverage does not overwrite the home roster",
    description=(
        "Applying temporary coverage must leave the covering employee's home "
        "assignment intact; permanent changes require an explicit transfer event."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)
