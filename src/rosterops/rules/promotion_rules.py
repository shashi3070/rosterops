"""Group F — Promotions and role changes rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = ["PRO_001", "PRO_002", "PRO_003", "PRO_004", "PRO_005", "PRO_006"]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_P = frozenset({InputMode.PROCESS})
_GROUP = "promotion"

PRO_001 = register_rule(
    id="PRO-001",
    name="Promotion has valid current and new role values",
    description="A promotion without a destination role (or grade) is incomplete and flagged.",
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

PRO_002 = register_rule(
    id="PRO-002",
    name="Role transition permitted (role-transition matrix)",
    description=(
        "Transitions outside the configured role-transition matrix (role master "
        "successors) are flagged according to configuration."
    ),
    default_severity=Severity.WARNING,
    modes=_P,
    group=_GROUP,
)

PRO_003 = register_rule(
    id="PRO-003",
    name="Promotion event is unique",
    description="The same promotion loaded twice (across files or within a file) is flagged.",
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

PRO_004 = register_rule(
    id="PRO-004",
    name="Promotion effective date valid for employment",
    description=(
        "A promotion effective after termination or during an invalid employment "
        "interval is flagged with the conflicting dates."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

PRO_005 = register_rule(
    id="PRO-005",
    name="Promotion state correctly reconstructed",
    description=(
        "Role intervals must reflect the configured date convention: the prior "
        "role applies before the effective date, the new role from it."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

PRO_006 = register_rule(
    id="PRO-006",
    name="Promotion counts are event-based; no inference from snapshots",
    description=(
        "Snapshot role differences are reported as observed changes (or inferred "
        "when explicitly enabled), never counted as historical promotion events."
    ),
    default_severity=Severity.INFO,
    modes=frozenset({InputMode.SNAPSHOT}),
    group=_GROUP,
)
