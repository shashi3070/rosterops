"""Group K — Reconciliation and operational metrics rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = [
    "REC_001",
    "REC_002",
    "REC_003",
    "REC_004",
    "REC_005",
    "REC_006",
    "REC_007",
    "REC_008",
]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_P = frozenset({InputMode.PROCESS})
_GROUP = "reconciliation"

REC_001 = register_rule(
    id="REC-001",
    name=(
        "Headcount reconciliation: "
        "`ending_active = starting_active + hires + rehires − terminations`"  # noqa: RUF001
    ),
    description=(
        "For a simplified employee model with non-overlapping employment episodes, "
        "ending active headcount must equal starting active headcount plus hires "
        "plus rehires minus terminations. When the source model violates these "
        "assumptions the rule reports why the formula is not applicable instead of "
        "producing a misleading number. In snapshot mode the metric is "
        "not_available, never fabricated."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

REC_002 = register_rule(
    id="REC-002",
    name="Transfer reconciliation (ins/outs by territory)",
    description=(
        "Internal transfer events must reconcile between per-territory ins and "
        "outs; external hires, terminations, and cross-company moves are separated "
        "when configured."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

REC_003 = register_rule(
    id="REC-003",
    name="Leave reconciliation (starts, returns, open)",
    description=(
        "Leave starts, returns, and open leaves are counted separately and must "
        "agree with the leave ledger; an open leave is not an error."
    ),
    default_severity=Severity.WARNING,
    modes=_P,
    group=_GROUP,
)

REC_004 = register_rule(
    id="REC-004",
    name="Assignment reconciliation vs event ledger",
    description=(
        "The effective assignment intervals and final roster must be explainable "
        "by the normalized event ledger; unexplained divergences are flagged."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

REC_005 = register_rule(
    id="REC-005",
    name="Vacancy/active-primary reconciliation",
    description=(
        "Vacancies derive only from territories requiring a primary owner after "
        "permitted-role and effective-date policies; vacancy and active-primary "
        "totals must be mutually consistent."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
)

REC_006 = register_rule(
    id="REC-006",
    name="Duplicate movement detection across inputs",
    description=(
        "Duplicate movement events across files are detected by stable event keys "
        "and configured deduplication rules; duplicate-looking rows are never "
        "silently dropped without a finding."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

REC_007 = register_rule(
    id="REC-007",
    name="Movement summary consistency (and `not_available` explanations in S)",
    description=(
        "Summary counts must agree with normalized events, final-state "
        "differences, and validation rules where comparable; metrics unavailable "
        "in snapshot mode carry an explicit not_available reason."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

REC_008 = register_rule(
    id="REC-008",
    name="Snapshot comparison consistency (two-snapshot mode)",
    description=(
        "When comparing two snapshots, added/removed/changed records are detected "
        "by configured keys; changed assignments are not labeled transfers unless "
        "inference is enabled and the result is marked inferred."
    ),
    default_severity=Severity.WARNING,
    modes=frozenset({InputMode.SNAPSHOT}),
    group=_GROUP,
)
