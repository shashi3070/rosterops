"""Typed result object returned by engine runs (REQUIREMENTS §11.1).

All tabular fields are Polars DataFrames. ``summary`` and ``reconciliation``
are plain mapping structures so they serialize cleanly to JSON. Metrics that
cannot be derived in a given mode carry ``status == "not_available"`` and a
reason rather than a fabricated number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from rosterops.rules.base import Finding

__all__ = [
    "MetricValue",
    "ReconciliationResult",
    "RosterResult",
    "RunMetadata",
]


@dataclass(frozen=True, slots=True)
class MetricValue:
    """A metric that is either a concrete number or honestly unavailable."""

    value: int | float | None
    status: str = "available"
    reason: str | None = None

    @classmethod
    def available(cls, value: int | float) -> MetricValue:
        return cls(value=value, status="available")

    @classmethod
    def not_available(cls, reason: str) -> MetricValue:
        return cls(value=None, status="not_available", reason=reason)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"value": self.value, "status": self.status}
        if self.reason is not None:
            out["reason"] = self.reason
        return out


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Expected-vs-actual reconciliation outcome (REQUIREMENTS §11.1)."""

    rule_id: str
    status: str  # "pass" | "fail" | "not_applicable"
    formula: str | None = None
    expected: int | float | None = None
    actual: int | float | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "status": self.status,
            "formula": self.formula,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class RunMetadata:
    """Tool/version/config/input provenance (REQUIREMENTS §11.1)."""

    tool_version: str
    mode: str
    grain: str
    as_of: str | None = None
    baseline_date: str | None = None
    config_hash: str | None = None
    input_files: tuple[dict[str, Any], ...] = ()
    generated_at: str | None = None
    applied_event_order: tuple[str, ...] = ()
    conflict_policy: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "mode": self.mode,
            "grain": self.grain,
            "as_of": self.as_of,
            "baseline_date": self.baseline_date,
            "config_hash": self.config_hash,
            "input_files": [dict(item) for item in self.input_files],
            "generated_at": self.generated_at,
            "applied_event_order": list(self.applied_event_order),
            "conflict_policy": self.conflict_policy,
        }


@dataclass(slots=True)
class RosterResult:
    """Full typed result of a process/validate run."""

    mode: str
    as_of: str | None = None
    baseline_date: str | None = None
    roster: pl.DataFrame = field(default_factory=pl.DataFrame)
    assignments: pl.DataFrame = field(default_factory=pl.DataFrame)
    events: pl.DataFrame = field(default_factory=pl.DataFrame)
    issues: pl.DataFrame = field(default_factory=pl.DataFrame)
    vacancies: pl.DataFrame = field(default_factory=pl.DataFrame)
    summary: dict[str, Any] = field(default_factory=dict)
    reconciliation: tuple[ReconciliationResult, ...] = ()
    metadata: RunMetadata | None = None
    findings: tuple[Finding, ...] = ()

    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity.value == "error")

    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity.value == "warning")

    def exit_code(self, *, fail_on_warning: bool = False) -> int:
        """Documented process exit code (REQUIREMENTS §13)."""
        if self.error_count() > 0:
            return 1
        if any(r.status == "fail" for r in self.reconciliation):
            return 1
        if fail_on_warning and self.warning_count() > 0:
            return 1
        return 0

    def issues_frame(self, findings: tuple[Finding, ...]) -> pl.DataFrame:
        """Build the ``issues`` DataFrame from findings in deterministic order."""
        rows = [f.to_row() for f in findings]
        if not rows:
            return pl.DataFrame()
        frame = pl.DataFrame(rows)
        order = [
            "issue_id",
            "issue_key",
            "rule_id",
            "category",
            "severity",
            "message",
            "employee_id",
            "territory_id",
            "event_id",
            "effective_date",
            "source_file",
            "source_sheet",
            "source_row",
            "source_column",
            "actual_value",
            "expected_value",
            "suggested_action",
        ]
        return frame.select([c for c in order if c in frame.columns])
