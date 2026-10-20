"""Rule specifications, findings, and the global rule registry.

Rule IDs are a stable public contract (REQUIREMENTS §8): once released they
do not change. Specifications carry metadata only — implementations live with
their group modules and register findings through :class:`Finding`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date

from rosterops.exceptions import RosterOpsError
from rosterops.models import InputMode, Severity

__all__ = [
    "Finding",
    "RuleSpec",
    "all_rule_ids",
    "all_rules",
    "get_rule",
    "has_rule",
    "register_rule",
    "severity_rank",
    "sort_and_number",
    "sort_findings",
]

_REGISTRY: dict[str, RuleSpec] = {}

_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.ERROR: 0,
    Severity.WARNING: 1,
    Severity.INFO: 2,
}


def severity_rank(severity: Severity) -> int:
    """Sort rank for severities (errors first)."""
    return _SEVERITY_ORDER[severity]


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """Immutable metadata for one validation rule."""

    id: str
    name: str
    description: str
    default_severity: Severity
    modes: frozenset[InputMode]
    group: str
    params: Mapping[str, type] = field(default_factory=dict)

    @property
    def mode_labels(self) -> tuple[str, ...]:
        """Applicable modes as sorted short labels (``snapshot``/``process``)."""
        return tuple(sorted(m.value for m in self.modes))


def register_rule(
    *,
    id: str,
    name: str,
    description: str,
    default_severity: Severity,
    modes: frozenset[InputMode],
    group: str,
    params: Mapping[str, type] | None = None,
) -> RuleSpec:
    """Create and register a rule specification.

    Raises ``RosterOpsError`` on duplicate or malformed registration — this is
    a code defect, not user-facing validation.
    """
    if id in _REGISTRY:
        raise RosterOpsError(f"duplicate rule registration: {id!r}")
    spec = RuleSpec(
        id=id,
        name=name,
        description=description,
        default_severity=default_severity,
        modes=modes,
        group=group,
        params=dict(params or {}),
    )
    _validate_spec(spec)
    _REGISTRY[id] = spec
    return spec


def _validate_spec(spec: RuleSpec) -> None:
    if not re.fullmatch(r"[A-Z]{2,3}-\d{3}", spec.id):
        raise RosterOpsError(f"malformed rule id: {spec.id!r} (expected XXX-000)")
    if not spec.name.strip() or not spec.description.strip():
        raise RosterOpsError(f"rule {spec.id}: name and description are required")
    if not spec.modes:
        raise RosterOpsError(f"rule {spec.id}: at least one mode is required")
    if spec.group not in {
        "input",
        "identifier",
        "temporal",
        "employment",
        "transfer",
        "promotion",
        "leave",
        "territory",
        "coverage",
        "hierarchy",
        "reconciliation",
        "grain",
    }:
        raise RosterOpsError(f"rule {spec.id}: unknown group {spec.group!r}")


def get_rule(rule_id: str) -> RuleSpec:
    """Look up a rule specification; raises ``KeyError`` when unknown."""
    try:
        return _REGISTRY[rule_id]
    except KeyError:
        raise KeyError(f"unknown rule id: {rule_id!r}") from None


def has_rule(rule_id: str) -> bool:
    """True when ``rule_id`` is registered."""
    return rule_id in _REGISTRY


def all_rule_ids() -> frozenset[str]:
    """All registered rule IDs."""
    return frozenset(_REGISTRY)


def all_rules() -> tuple[RuleSpec, ...]:
    """All registered specifications, sorted by rule ID (deterministic)."""
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


@dataclass(frozen=True, slots=True)
class Finding:
    """A single validation finding with source lineage (REQUIREMENTS §11.1).

    ``issue_key`` is a deterministic content hash so downstream systems can
    group the same finding across runs. ``issue_id`` is assigned by
    :func:`sort_and_number` once the finding set is complete.
    """

    rule_id: str
    severity: Severity
    message: str
    category: str
    employee_id: str | None = None
    territory_id: str | None = None
    event_id: str | None = None
    effective_date: date | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_column: str | None = None
    actual_value: str | None = None
    expected_value: str | None = None
    suggested_action: str | None = None
    issue_key: str = field(default="")
    issue_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.issue_key:
            object.__setattr__(self, "issue_key", self._compute_key())

    @classmethod
    def from_spec(
        cls,
        spec: RuleSpec,
        message: str,
        *,
        severity: Severity | None = None,
        **fields: object,
    ) -> Finding:
        """Build a finding using the rule's default severity and group."""
        return cls(
            rule_id=spec.id,
            severity=severity or spec.default_severity,
            message=message,
            category=spec.group,
            **fields,  # type: ignore[arg-type]
        )

    def _compute_key(self) -> str:
        parts = [
            self.rule_id,
            self.employee_id or "",
            self.territory_id or "",
            self.event_id or "",
            self.effective_date.isoformat() if self.effective_date else "",
            self.source_file or "",
            self.source_sheet or "",
            str(self.source_row) if self.source_row is not None else "",
            self.source_column or "",
            self.message,
        ]
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return digest[:16]

    def sort_key(self) -> tuple[int, str, str, int, str]:
        """Deterministic ordering: severity, rule, file, row, entity."""
        entity = self.employee_id or self.territory_id or self.event_id or ""
        return (
            severity_rank(self.severity),
            self.rule_id,
            self.source_file or "",
            self.source_row if self.source_row is not None else -1,
            entity,
        )

    def to_row(self) -> dict[str, object]:
        """Flat dictionary matching the ``result.issues`` column contract."""
        return {
            "issue_id": self.issue_id,
            "issue_key": self.issue_key,
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
            "employee_id": self.employee_id,
            "territory_id": self.territory_id,
            "event_id": self.event_id,
            "effective_date": self.effective_date,
            "source_file": self.source_file,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
            "source_column": self.source_column,
            "actual_value": self.actual_value,
            "expected_value": self.expected_value,
            "suggested_action": self.suggested_action,
        }


def sort_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Deterministically order findings by :meth:`Finding.sort_key`."""
    return sorted(findings, key=lambda f: f.sort_key())


def sort_and_number(findings: Iterable[Finding]) -> list[Finding]:
    """Sort findings and assign stable sequential ``issue_id`` values."""
    ordered = sort_findings(findings)
    return [replace(f, issue_id=f"ISS-{i:06d}") for i, f in enumerate(ordered, start=1)]
