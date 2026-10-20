"""Group C — Effective dates and temporal integrity rule specifications."""

from __future__ import annotations

from rosterops.models import InputMode, Severity
from rosterops.rules.base import register_rule

__all__ = [
    "DAT_001",
    "DAT_002",
    "DAT_003",
    "DAT_004",
    "DAT_005",
    "DAT_006",
    "DAT_007",
    "DAT_008",
]

_SP = frozenset({InputMode.SNAPSHOT, InputMode.PROCESS})
_P = frozenset({InputMode.PROCESS})
_GROUP = "temporal"

DAT_001 = register_rule(
    id="DAT-001",
    name="Effective start date is valid/parseable",
    description=(
        "An effective start date that cannot be parsed under configured formats "
        "flags the row and excludes it from unsafe temporal calculations."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

DAT_002 = register_rule(
    id="DAT-002",
    name="Interval bounds valid (end ≥ start)",
    description=(
        "Inverted intervals (effective_to before effective_from) are flagged as "
        "invalid; the engine never silently repairs the bounds."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

DAT_003 = register_rule(
    id="DAT-003",
    name="Interval overlap detection (incompatible assignments)",
    description=(
        "Incompatible assignment intervals for the same employee/territory overlap "
        "in time; the finding reports the intersecting interval and both sources. "
        "Adjacent half-open intervals do not overlap."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)

DAT_004 = register_rule(
    id="DAT-004",
    name="Temporal gap detection (coverage-required intervals)",
    description=(
        "A gap in role or assignment coverage during a period where coverage is "
        "required is reported; gaps are not automatically invalid (awaiting "
        "placement can be legitimate) so severity follows policy."
    ),
    default_severity=Severity.WARNING,
    modes=_SP,
    group=_GROUP,
)

DAT_005 = register_rule(
    id="DAT-005",
    name="Event occurs after termination",
    description=(
        "An event effective after the employee's termination is flagged unless an "
        "explicit rehire or correction workflow justifies it."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

DAT_006 = register_rule(
    id="DAT-006",
    name="Event already reflected in baseline (on/before baseline date)",
    description=(
        "Events dated on or before the baseline date are outside the reconstruction "
        "window (per policies.events.reject_events_on_or_before_baseline_date); "
        "they are flagged and never double-applied to the baseline state."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

DAT_007 = register_rule(
    id="DAT-007",
    name="Same-date conflicting events",
    description=(
        "Conflicting events for one employee on one effective date (double "
        "transfer, termination plus transfer, conflicting promotions) are flagged "
        "unless an explicit configured policy resolves them; row order never "
        "decides silently."
    ),
    default_severity=Severity.ERROR,
    modes=_P,
    group=_GROUP,
)

DAT_008 = register_rule(
    id="DAT-008",
    name="Source and canonical date semantics agree (termination conversion)",
    description=(
        "Source date conventions (inclusive interval ends, termination date "
        "meaning) must be configured and converted into the canonical half-open "
        "convention; conventions are never mixed silently."
    ),
    default_severity=Severity.ERROR,
    modes=_SP,
    group=_GROUP,
)
