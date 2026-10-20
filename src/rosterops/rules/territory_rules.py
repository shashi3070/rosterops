"""Group H — Territory integrity, primary assignments, and vacancies."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = [
    "TER_001",
    "TER_002",
    "TER_003",
    "TER_004",
    "TER_005",
    "TER_006",
    "TER_007",
    "TER_008",
    "TER_009",
]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_P = frozenset({InputMode.PROCESS})
_GROUP = "territory"

TER_001 = register_rule(
    id="TER-001",
    name="Assigned territory exists in master",
    description="Assignments referencing territories absent from the territory master are flagged.",
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

TER_002 = register_rule(
    id="TER-002",
    name="Primary assignment constraints (max primaries/employee)",
    description=(
        "An employee holding more simultaneous primary territories than "
        "policies.max_primary_territories_per_employee allows is flagged with the "
        "overlapping interval."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

TER_003 = register_rule(
    id="TER-003",
    name="Territory occupancy is valid (no incompatible overlap)",
    description=(
        "A territory's concurrent assignments must respect its occupancy model; "
        "incompatible simultaneous occupants are flagged."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

TER_004 = register_rule(
    id="TER-004",
    name="Territory role eligibility",
    description=(
        "When a territory declares allowed roles, its primary assignee's role class "
        "must be eligible; incompatibility is flagged if the rule is configured."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
)

TER_005 = register_rule(
    id="TER-005",
    name="Required-owner vacancies identified (with interval)",
    description=(
        "Territories marked requires_primary_owner with no active primary assignment "
        "are reported as vacancies with the unfilled interval."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
    params={"grace_days": int},
)

TER_006 = register_rule(
    id="TER-006",
    name="Unrequired/unassigned-by-design territories not counted as vacancies",
    description=(
        "Inactive territories or territories that do not require a primary owner "
        "are excluded from vacancy counts unless configuration says otherwise."
    ),
    default_severity=Severity.INFO,
    modes=_SP,
    group=_GROUP,
)

TER_007 = register_rule(
    id="TER-007",
    name="Vacancy intervals correct",
    description=(
        "Vacancy runs from the end of the prior qualifying assignment until a new "
        "eligible assignment begins; boundaries follow the half-open convention."
    ),
    default_severity=Severity.WARNING,
    modes=_P,
    group=_GROUP,
)

TER_008 = register_rule(
    id="TER-008",
    name="Territory capacity (max assignees) enforced",
    description=(
        "Simultaneous assignments beyond a territory's max_assignees capacity are "
        "flagged with the excess count."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

TER_009 = register_rule(
    id="TER-009",
    name="Assignment overlaps follow role/territory policy",
    description=(
        "Overlap findings apply configured eligibility and primary/secondary rules "
        "(e.g., specialists covering several territories) instead of one global "
        "overlap prohibition."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)
