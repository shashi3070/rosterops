"""Group B — Identifier and record integrity rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = [
    "ID_001",
    "ID_002",
    "ID_003",
    "ID_004",
    "ID_005",
    "ID_006",
    "ID_007",
]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_P = frozenset({InputMode.PROCESS})
_GROUP = "identifier"

ID_001 = register_rule(
    id="ID-001",
    name="Employee ID is non-null and non-empty",
    description=(
        "A record without a usable employee identifier cannot be attributed to an "
        "identity and is flagged even when other fields are populated."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

ID_002 = register_rule(
    id="ID-002",
    name="Event IDs unique within their namespace",
    description=(
        "Event IDs must be unique within their declared namespace (source system "
        "or file role); duplicates are flagged and namespaced explicitly when IDs "
        "are only unique per source system."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

ID_003 = register_rule(
    id="ID-003",
    name="Duplicate baseline records at the declared grain",
    description=(
        "Rows identical at the configured grain (data.grain) are duplicates; rows "
        "that differ only by grain key columns are legitimate and not flagged."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

ID_004 = register_rule(
    id="ID-004",
    name="Duplicate assignment key",
    description=(
        "Two rows sharing the same employee, territory, assignment type, and start "
        "date are a duplicate assignment unless the source model explicitly permits "
        "distinguishable records at that grain."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

ID_005 = register_rule(
    id="ID-005",
    name="Whitespace/normalization collisions",
    description=(
        'Identifiers that become equal only after trimming ("E001" vs " E001 ") '
        "are reported as a collision; conflicting employees are never auto-merged."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
)

ID_006 = register_rule(
    id="ID-006",
    name="Identifier references resolve (employee known)",
    description=(
        "Events referencing an employee absent from the baseline and from any "
        "loaded hire/rehire event are flagged as unresolved identity references."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

ID_007 = register_rule(
    id="ID-007",
    name="Event duplication across files (fingerprint-based)",
    description=(
        "The same business event appearing in multiple loaded inputs is detected "
        "by stable event keys and deterministic fingerprints, never by filename "
        "alone, and duplicates are excluded from application with a finding."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)
