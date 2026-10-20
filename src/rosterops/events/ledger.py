"""Canonical event ledger.

All eight supported event types are normalized into :class:`Event` rows carried
by an :class:`EventLedger`. The ledger is the single input to reconstruction
(Phase 5): it records every event, its identity/fingerprint, dedupe diagnostics,
reconstruction-window decisions, and any findings raised while normalizing.

Nothing is ever silently dropped: excluded events remain in the ledger with a
status (``duplicate``/``out_of_window``) and a finding.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum

from rosterops.models import EventType, Lineage
from rosterops.rules.base import Finding

__all__ = [
    "Event",
    "EventLedger",
    "EventStatus",
    "ReconstructionWindow",
    "build_fingerprint",
    "empty_window",
]


class EventStatus(str, Enum):
    """Disposition of an event within the ledger."""

    ACTIVE = "active"
    DUPLICATE = "duplicate"
    OUT_OF_WINDOW = "out_of_window"
    INVALID = "invalid"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ReconstructionWindow:
    """The ``(baseline_date, as_of]`` window an event must fall within."""

    baseline_date: date
    as_of: date
    baseline_includes_effective_date: bool = True

    def contains(self, effective: date | None) -> bool:
        """True when an event effective on ``effective`` applies to the window."""
        if effective is None:
            return False
        if self.baseline_includes_effective_date:
            if effective <= self.baseline_date:
                return False
        elif effective < self.baseline_date:
            return False
        return effective <= self.as_of


def empty_window() -> ReconstructionWindow:
    """A window that accepts no events (used when dates are unset)."""
    return ReconstructionWindow(baseline_date=date.max, as_of=date.min)


@dataclass(frozen=True, slots=True)
class Event:
    """One normalized event with identity, lineage, and disposition (§4.4)."""

    event_type: EventType
    employee_id: str
    event_id: str | None = None
    effective_date: date | None = None
    recorded_date: date | None = None
    old_value: str | None = None
    new_value: str | None = None
    from_territory_id: str | None = None
    to_territory_id: str | None = None
    old_role_code: str | None = None
    new_role_code: str | None = None
    leave_start_date: date | None = None
    leave_end_date: date | None = None
    source_system: str | None = None
    #: Canonical exclusive employment end derived from termination semantics
    #: (``DAT-008``); set only on termination events.
    employment_end_exclusive: date | None = None
    #: Input role the event was loaded from (e.g. ``transfers``).
    role: str = ""
    #: Namespace for event-ID uniqueness (source system or role).
    namespace: str = ""
    lineage: Lineage = field(default_factory=Lineage)
    #: Deterministic cross-file identity fingerprint.
    fingerprint: str = ""
    status: EventStatus = EventStatus.ACTIVE
    #: Why the event was excluded, when status is not ACTIVE.
    exclusion_reason: str | None = None

    @property
    def namespaced_id(self) -> str | None:
        """``namespace:event_id`` when both are present, else the raw id."""
        if self.event_id is None:
            return None
        if not self.namespace:
            return self.event_id
        return f"{self.namespace}:{self.event_id}"

    def with_status(self, status: EventStatus, reason: str | None = None) -> Event:
        return replace(self, status=status, exclusion_reason=reason or self.exclusion_reason)

    def sort_key(self) -> tuple[date, str, str, int, str]:
        """Deterministic ordering: effective date, type, file, row, id."""
        return (
            self.effective_date or date.min,
            self.event_type.value,
            self.lineage.source_file or "",
            self.lineage.source_row or -1,
            self.event_id or "",
        )


@dataclass(slots=True)
class EventLedger:
    """All normalized events plus the findings raised while building them."""

    events: list[Event] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.events)

    def active_events(self) -> list[Event]:
        """Events that will be applied to reconstruction, in deterministic order."""
        active = [e for e in self.events if e.status is EventStatus.ACTIVE]
        return sorted(active, key=lambda e: e.sort_key())

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.status.value] = counts.get(event.status.value, 0) + 1
        return counts

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.event_type.value] = counts.get(event.event_type.value, 0) + 1
        return counts

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)


def build_fingerprint(
    event_type: EventType,
    employee_id: str,
    effective_date: date | None,
    *,
    from_territory_id: str | None = None,
    to_territory_id: str | None = None,
    old_role_code: str | None = None,
    new_role_code: str | None = None,
    leave_start_date: date | None = None,
) -> str:
    """Compute a deterministic cross-file fingerprint for an event.

    Identity is based on business content (type, employee, effective date, and
    the type-relevant payload), NOT on filename or row — so the same event
    appearing in two files yields the same fingerprint (``ID-007``).
    """
    parts = [
        event_type.value,
        employee_id,
        effective_date.isoformat() if effective_date else "",
        from_territory_id or "",
        to_territory_id or "",
        old_role_code or "",
        new_role_code or "",
        leave_start_date.isoformat() if leave_start_date else "",
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]
