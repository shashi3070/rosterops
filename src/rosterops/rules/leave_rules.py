"""Group G — Leaves of absence and return-from-leave rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = [
    "LOA_001",
    "LOA_002",
    "LOA_003",
    "LOA_004",
    "LOA_005",
    "LOA_006",
    "LOA_007",
    "LOA_008",
    "LOA_009",
    "LOA_010",
]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_P = frozenset({InputMode.PROCESS})
_GROUP = "leave"

LOA_001 = register_rule(
    id="LOA-001",
    name="Leave start/end dates valid",
    description="Leave intervals ending before they start, or unparseable dates, are flagged.",
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

LOA_002 = register_rule(
    id="LOA-002",
    name="Leave references a valid employment episode",
    description="Leave for an employee whose employment cannot be established is flagged.",
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

LOA_003 = register_rule(
    id="LOA-003",
    name="Duplicate/overlapping incompatible leave detected",
    description=(
        "Two overlapping leave periods for the same employee are flagged when "
        "leave-type policy does not permit overlap; compatible overlaps pass."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

LOA_004 = register_rule(
    id="LOA-004",
    name="Return-from-leave event is valid",
    description=(
        "A return date before the related leave starts (or otherwise inconsistent "
        "with the leave period) is flagged as invalid linkage or sequence."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

LOA_005 = register_rule(
    id="LOA-005",
    name="Leave does not silently terminate employment",
    description=(
        "Employees on leave must remain in the employee master when policy retains "
        "employment; employment status is validated separately from availability."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

LOA_006 = register_rule(
    id="LOA-006",
    name="Leave after termination is controlled",
    description=(
        "Leave beginning after the termination date is flagged unless an explicit "
        "rehire or source-specific correction justifies it."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

LOA_007 = register_rule(
    id="LOA-007",
    name="Leave coverage requirements satisfied",
    description=(
        "Territories whose policy requires coverage during an owner's leave must "
        "have temporary coverage for the absence interval; missing coverage is "
        "reported per policy, overridable per rule."
    ),
    default_severity=Severity.WARNING,
    modes=_P,
    group=_GROUP,
    params={"coverage_required": bool},
)

LOA_008 = register_rule(
    id="LOA-008",
    name="Coverage does not create permanent assignment changes",
    description=(
        "Temporary coverage during a leave must not alter the covering employee's "
        "home assignment; only an explicit transfer event may do so."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

LOA_009 = register_rule(
    id="LOA-009",
    name="Leave metrics distinguish starts / returns / currently absent",
    description=(
        "Leave-start events, return transitions, and employees currently on leave "
        "are counted separately; an employee who started and returned within the "
        "window counts in the first two, not the third."
    ),
    default_severity=Severity.INFO,
    modes=_P,
    group=_GROUP,
)

LOA_010 = register_rule(
    id="LOA-010",
    name="Open leaves handled without false invalidity",
    description=(
        "A leave with no return date by the reporting cutoff counts as one leave "
        "start and one currently-on-leave employee; the missing return is not "
        "treated as invalid when the leave is legitimately open."
    ),
    default_severity=Severity.INFO,
    modes=_P,
    group=_GROUP,
)
