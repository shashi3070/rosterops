"""Reconstructed roster state: employment, role, assignment, leave, coverage.

The state is built from the baseline snapshot (Mode A phase 1) and then mutated
by applying in-window events. All intervals are half-open ``[start, end)`` with
nullable ends (open-ended), consistent with :mod:`rosterops.domain.intervals`.

Determinism: every collection is kept in a deterministic order and events are
applied in the ledger's deterministic order, so re-runs are logically identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from rosterops.domain.intervals import interval_contains

__all__ = [
    "AssignmentInterval",
    "BaselineState",
    "CoverageRecord",
    "EmployeeRecord",
    "EmploymentEpisode",
    "LeaveInterval",
    "RoleInterval",
]


@dataclass(frozen=True, slots=True)
class EmployeeRecord:
    """Static-ish employee attributes from the baseline/master."""

    employee_id: str
    employee_status: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    role_code: str | None = None
    grade_code: str | None = None
    manager_id: str | None = None
    business_unit: str | None = None
    country: str | None = None
    region_id: str | None = None
    district_id: str | None = None


@dataclass(frozen=True, slots=True)
class EmploymentEpisode:
    """A continuous employment interval ``[start, end)``; ``end=None`` = active."""

    employee_id: str
    start: date | None
    end: date | None = None
    source_event_id: str | None = None

    def active_on(self, day: date) -> bool:
        if self.start is None:
            return False
        return interval_contains(self.start, self.end, day)


@dataclass(frozen=True, slots=True)
class RoleInterval:
    """A role held over ``[start, end)``."""

    employee_id: str
    role_code: str | None
    start: date | None
    end: date | None = None
    source_event_id: str | None = None

    def active_on(self, day: date) -> bool:
        if self.start is None:
            return False
        return interval_contains(self.start, self.end, day)


@dataclass(frozen=True, slots=True)
class AssignmentInterval:
    """A territory assignment over ``[start, end)``."""

    employee_id: str
    territory_id: str | None
    assignment_type: str | None = None
    is_primary: bool = False
    start: date | None = None
    end: date | None = None
    assignment_status: str | None = None
    source_event_id: str | None = None

    def active_on(self, day: date) -> bool:
        if self.start is None:
            return False
        return interval_contains(self.start, self.end, day)


@dataclass(frozen=True, slots=True)
class LeaveInterval:
    """A leave-of-absence over ``[start, end)``; ``end=None`` = open."""

    employee_id: str
    start: date | None
    end: date | None = None
    source_event_id: str | None = None

    def active_on(self, day: date) -> bool:
        if self.start is None:
            return False
        return interval_contains(self.start, self.end, day)


@dataclass(frozen=True, slots=True)
class CoverageRecord:
    """A temporary coverage relationship over ``[start, end)``."""

    covering_employee_id: str
    covered_territory_id: str | None
    covered_employee_id: str | None = None
    coverage_type: str | None = None
    is_primary_coverage: bool = False
    start: date | None = None
    end: date | None = None
    source_event_id: str | None = None

    def active_on(self, day: date) -> bool:
        if self.start is None:
            return False
        return interval_contains(self.start, self.end, day)


@dataclass(slots=True)
class BaselineState:
    """Mutable reconstructed state: employees plus their temporal intervals."""

    employees: dict[str, EmployeeRecord] = field(default_factory=dict)
    employment: dict[str, list[EmploymentEpisode]] = field(default_factory=dict)
    roles: dict[str, list[RoleInterval]] = field(default_factory=dict)
    assignments: dict[str, list[AssignmentInterval]] = field(default_factory=dict)
    leaves: dict[str, list[LeaveInterval]] = field(default_factory=dict)
    coverage: list[CoverageRecord] = field(default_factory=list)

    def add_employee(self, record: EmployeeRecord) -> None:
        self.employees.setdefault(record.employee_id, record)

    def add_employment(self, episode: EmploymentEpisode) -> None:
        self.employment.setdefault(episode.employee_id, []).append(episode)

    def add_role(self, interval: RoleInterval) -> None:
        self.roles.setdefault(interval.employee_id, []).append(interval)

    def add_assignment(self, interval: AssignmentInterval) -> None:
        self.assignments.setdefault(interval.employee_id, []).append(interval)

    def add_leave(self, interval: LeaveInterval) -> None:
        self.leaves.setdefault(interval.employee_id, []).append(interval)

    def add_coverage(self, record: CoverageRecord) -> None:
        self.coverage.append(record)

    def employee_ids(self) -> list[str]:
        return sorted(self.employees)

    def active_employee_ids(self, day: date) -> list[str]:
        """Distinct employees with an active employment episode on ``day``."""
        return sorted(
            eid
            for eid, episodes in self.employment.items()
            if any(ep.active_on(day) for ep in episodes)
        )

    def role_on(self, employee_id: str, day: date) -> str | None:
        """Latest-starting role interval active on ``day`` (deterministic)."""
        candidates = [r for r in self.roles.get(employee_id, []) if r.active_on(day)]
        if not candidates:
            return None
        latest = max(candidates, key=lambda r: (r.start or date.min, r.role_code or ""))
        return latest.role_code

    def active_assignments(self, employee_id: str, day: date) -> list[AssignmentInterval]:
        """Assignment intervals for an employee active on ``day``."""
        return [a for a in self.assignments.get(employee_id, []) if a.active_on(day)]

    def primary_territory(self, employee_id: str, day: date) -> str | None:
        """The primary territory an employee holds on ``day`` (if any)."""
        primaries = [a for a in self.active_assignments(employee_id, day) if a.is_primary]
        if not primaries:
            return None
        return max(primaries, key=lambda a: a.start or date.min).territory_id

    def on_leave(self, employee_id: str, day: date) -> bool:
        return any(lv.active_on(day) for lv in self.leaves.get(employee_id, []))

    def close_employment(self, employee_id: str, end: date, source_event_id: str | None) -> None:
        """Close the open-ended employment episode at ``end`` (exclusive)."""
        episodes = self.employment.get(employee_id, [])
        for index, episode in enumerate(episodes):
            if episode.end is None:
                episodes[index] = EmploymentEpisode(
                    employee_id=episode.employee_id,
                    start=episode.start,
                    end=end,
                    source_event_id=source_event_id,
                )
                return

    def close_open_assignments(
        self, employee_id: str, end: date, source_event_id: str | None
    ) -> None:
        """Close all open-ended assignment intervals at ``end`` (exclusive)."""
        intervals = self.assignments.get(employee_id, [])
        for index, interval in enumerate(intervals):
            if interval.end is None:
                intervals[index] = AssignmentInterval(
                    employee_id=interval.employee_id,
                    territory_id=interval.territory_id,
                    assignment_type=interval.assignment_type,
                    is_primary=interval.is_primary,
                    start=interval.start,
                    end=end,
                    assignment_status=interval.assignment_status,
                    source_event_id=source_event_id or interval.source_event_id,
                )

    def close_open_roles(self, employee_id: str, end: date, source_event_id: str | None) -> None:
        """Close all open-ended role intervals at ``end`` (exclusive)."""
        intervals = self.roles.get(employee_id, [])
        for index, interval in enumerate(intervals):
            if interval.end is None:
                intervals[index] = RoleInterval(
                    employee_id=interval.employee_id,
                    role_code=interval.role_code,
                    start=interval.start,
                    end=end,
                    source_event_id=source_event_id or interval.source_event_id,
                )
