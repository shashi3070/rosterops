"""Public API surface: :class:`RosterEngine` (REQUIREMENTS §12).

Accepts file paths and (schema-valid) Polars or pandas DataFrames. Returns a
typed :class:`~rosterops.engine.result.RosterResult` whose DataFrames are Polars
by default; ``to_pandas=True`` converts them at the boundary. Caller frames are
never mutated.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from rosterops.config import RosterConfig
from rosterops.engine.load import SourceSpec
from rosterops.engine.orchestrator import process_run, validate_run
from rosterops.engine.result import RosterResult
from rosterops.interop import to_pandas as _to_pandas_frame

__all__ = ["RosterEngine"]

_FRAME_FIELDS = ("roster", "assignments", "events", "issues", "vacancies")


class RosterEngine:
    """Synchronous processing engine bound to a resolved configuration."""

    def __init__(self, config: RosterConfig) -> None:
        self.config = config

    @classmethod
    def from_file(cls, path: str | Path) -> RosterEngine:
        """Build an engine from a YAML configuration file."""
        return cls(RosterConfig.from_file(path))

    def process(
        self,
        *,
        baseline: SourceSpec,
        baseline_date: str | date,
        as_of: str | date,
        transfers: SourceSpec | None = None,
        promotions: SourceSpec | None = None,
        terminations: SourceSpec | None = None,
        leaves: SourceSpec | None = None,
        returns: SourceSpec | None = None,
        hires: SourceSpec | None = None,
        rehires: SourceSpec | None = None,
        coverage: SourceSpec | None = None,
        territories: SourceSpec | None = None,
        managers: SourceSpec | None = None,
        organizations: SourceSpec | None = None,
        roles: SourceSpec | None = None,
        to_pandas: bool = False,
    ) -> RosterResult:
        """Run Mode A: reconstruct the roster from a baseline and event files."""
        sources: dict[str, SourceSpec] = {"baseline": baseline}
        for role, value in (
            ("transfers", transfers),
            ("promotions", promotions),
            ("terminations", terminations),
            ("leaves", leaves),
            ("returns", returns),
            ("hires", hires),
            ("rehires", rehires),
            ("coverage", coverage),
            ("territories", territories),
            ("managers", managers),
            ("organizations", organizations),
            ("roles", roles),
        ):
            if value is not None:
                sources[role] = value
        result = process_run(self.config, sources, baseline_date=baseline_date, as_of=as_of)
        return self._convert(result, to_pandas)

    def validate_snapshot(
        self,
        snapshot: SourceSpec,
        *,
        as_of: str | date,
        territories: SourceSpec | None = None,
        to_pandas: bool = False,
    ) -> RosterResult:
        """Run Mode B: validate a single consolidated snapshot."""
        sources: dict[str, SourceSpec] = {"snapshot": snapshot}
        if territories is not None:
            sources["territories"] = territories
        result = validate_run(self.config, sources, as_of=as_of)
        return self._convert(result, to_pandas)

    @staticmethod
    def _convert(result: RosterResult, to_pandas: bool) -> RosterResult:
        if not to_pandas:
            return result
        frames = {field: _to_pandas_frame(getattr(result, field)) for field in _FRAME_FIELDS}
        return replace(result, **frames)
