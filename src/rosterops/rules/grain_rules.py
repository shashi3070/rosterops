"""Group L — Data-grain integrity rule specifications (decision D1)."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = ["GRN_001", "GRN_002", "GRN_003"]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_GROUP = "grain"

GRN_001 = register_rule(
    id="GRN-001",
    name="Baseline cardinality conforms to declared grain",
    description=(
        "Loaded baseline rows must match data.grain: e.g., grain 'employee' "
        "rejects multiple rows per employee, while 'employee_territory' permits "
        "one row per employee-territory pair. Mismatches are flagged with both "
        "row numbers; headcount never counts raw rows."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

GRN_002 = register_rule(
    id="GRN-002",
    name="Declared grain keys are mapped and populated",
    description=(
        "Every declared grain key column must resolve through the input mapping "
        "and be populated; grain keys with unmapped or empty values make duplicate "
        "detection undefined and are flagged."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

GRN_003 = register_rule(
    id="GRN-003",
    name="Interval-bearing grains have required date columns",
    description=(
        "Grains that include assignment intervals (employee_territory_assignment "
        "or custom keys containing effective_from) require mapped effective-date "
        "columns; requesting interval rules without them fails loudly instead of "
        "silently downgrading."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)
