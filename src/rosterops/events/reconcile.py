"""Ledger post-processing: dedupe, window filtering, and same-date conflicts.

Applied after normalization, in the order required by REQUIREMENTS §6.3:

1. Dedupe identical business events across files by fingerprint (``ID-007``).
2. Filter events outside ``(baseline_date, as_of]`` (``DAT-006``).
3. Detect same-date conflicting events (``DAT-007``), resolving only when an
   explicit configured policy allows it.

No event is ever removed from the ledger: excluded events keep their row with a
non-``active`` status and a finding explaining the exclusion.
"""

from __future__ import annotations

from datetime import date

from rosterops.events.ledger import (
    Event,
    EventLedger,
    EventStatus,
    ReconstructionWindow,
)
from rosterops.models import EventType
from rosterops.rules.base import Finding
from rosterops.rules.identifier_rules import ID_007
from rosterops.rules.promotion_rules import PRO_003
from rosterops.rules.reconciliation_rules import REC_006
from rosterops.rules.temporal_rules import DAT_006, DAT_007
from rosterops.rules.transfer_rules import TRF_006

__all__ = [
    "CONFLICT_RULES",
    "dedupe_events",
    "detect_same_date_conflicts",
    "event_conflicts",
    "filter_to_window",
]

#: Event-type pairs whose co-occurrence on one date is a conflict, per §6.4.
#: Symmetric pairs with the same type on both sides are handled separately.
CONFLICT_RULES: tuple[frozenset[EventType], ...] = (
    frozenset({EventType.TRANSFER}),
    frozenset({EventType.TERMINATION, EventType.TRANSFER}),
    frozenset({EventType.PROMOTION, EventType.PROMOTION}),
    frozenset({EventType.TERMINATION, EventType.REHIRE}),
)


def dedupe_events(ledger: EventLedger) -> None:
    """Mark all but the first occurrence of each fingerprint as duplicates.

    Identity is the deterministic content fingerprint (never the filename), so a
    transfer present in both ``transfers_week1.csv`` and ``transfers_week2.csv``
    is detected regardless of source. The first occurrence (in deterministic
    ledger order) is retained; every later occurrence is flagged ``ID-007``.
    """
    first_seen: dict[str, Event] = {}
    for index, event in enumerate(ledger.events):
        if event.status is EventStatus.INVALID:
            continue
        prior = first_seen.get(event.fingerprint)
        if prior is None:
            first_seen[event.fingerprint] = event
            continue
        ledger.events[index] = event.with_status(
            EventStatus.DUPLICATE, f"duplicate of event in {prior.lineage.source_file}"
        )
        ledger.add_finding(
            Finding.from_spec(
                ID_007,
                f"duplicate {event.event_type.value} event for employee "
                f"{event.employee_id!r} on {_iso(event.effective_date)} "
                f"(same event also in {prior.lineage.source_file})",
                employee_id=event.employee_id,
                event_id=event.event_id,
                effective_date=event.effective_date,
                source_file=event.lineage.source_file,
                source_sheet=event.lineage.source_sheet,
                source_row=event.lineage.source_row,
                actual_value=event.fingerprint,
                expected_value=prior.fingerprint,
            )
        )
        if event.event_type is EventType.PROMOTION:
            ledger.add_finding(
                Finding.from_spec(
                    PRO_003,
                    f"promotion for employee {event.employee_id!r} on "
                    f"{_iso(event.effective_date)} is loaded more than once "
                    f"(also in {prior.lineage.source_file}); duplicate is retained with a "
                    f"finding, never silently dropped",
                    employee_id=event.employee_id,
                    event_id=event.event_id,
                    effective_date=event.effective_date,
                    source_file=event.lineage.source_file,
                    source_row=event.lineage.source_row,
                )
            )
        if event.event_type in {
            EventType.TRANSFER,
            EventType.PROMOTION,
            EventType.TERMINATION,
            EventType.HIRE,
            EventType.REHIRE,
        }:
            ledger.add_finding(
                Finding.from_spec(
                    REC_006,
                    f"duplicate {event.event_type.value} movement for employee "
                    f"{event.employee_id!r} on {_iso(event.effective_date)} "
                    f"(also in {prior.lineage.source_file}); duplicate is retained with a "
                    f"finding, never silently dropped",
                    employee_id=event.employee_id,
                    event_id=event.event_id,
                    effective_date=event.effective_date,
                    source_file=event.lineage.source_file,
                    source_row=event.lineage.source_row,
                )
            )


def filter_to_window(ledger: EventLedger, window: ReconstructionWindow) -> None:
    """Mark events outside ``(baseline_date, as_of]`` as out-of-window (DAT-006)."""
    for index, event in enumerate(ledger.events):
        if event.status is not EventStatus.ACTIVE:
            continue
        reference = event.effective_date or event.leave_start_date
        if window.contains(reference):
            continue
        ledger.events[index] = event.with_status(
            EventStatus.OUT_OF_WINDOW,
            f"event date {_iso(reference)} outside ({_iso(window.baseline_date)}, "
            f"{_iso(window.as_of)}]",
        )
        ledger.add_finding(
            Finding.from_spec(
                DAT_006,
                f"{event.event_type.value} event for employee {event.employee_id!r} dated "
                f"{_iso(reference)} is on/before the baseline date or after as-of and is "
                f"not applied",
                employee_id=event.employee_id,
                event_id=event.event_id,
                effective_date=reference,
                source_file=event.lineage.source_file,
                source_sheet=event.lineage.source_sheet,
                source_row=event.lineage.source_row,
            )
        )


def event_conflicts(a: Event, b: Event) -> bool:
    """True when two same-employee, same-date events conflict per §6.4.

    Two transfers to *different* destinations conflict; two promotions with
    *different* new roles conflict. Cross-type pairs listed in
    :data:`CONFLICT_RULES` always conflict.
    """
    if a.event_type is EventType.TRANSFER and b.event_type is EventType.TRANSFER:
        return a.to_territory_id != b.to_territory_id
    if a.event_type is EventType.PROMOTION and b.event_type is EventType.PROMOTION:
        return a.new_role_code != b.new_role_code
    types = frozenset({a.event_type, b.event_type})
    return any(types == rule for rule in CONFLICT_RULES)


def detect_same_date_conflicts(
    ledger: EventLedger,
    *,
    resolution_policy: str | None,
) -> None:
    """Flag conflicting same-date events for the same employee (``DAT-007``).

    Without an explicit policy, conflicting events are flagged and left
    ``ACTIVE`` for reconstruction to handle conservatively; row order never
    silently decides. When a policy is configured it is recorded in the finding
    message so the applied order is auditable.
    """
    buckets: dict[tuple[str, date], list[int]] = {}
    for index, event in enumerate(ledger.events):
        if event.status is not EventStatus.ACTIVE:
            continue
        reference = event.effective_date
        if reference is None or not event.employee_id:
            continue
        buckets.setdefault((event.employee_id, reference), []).append(index)

    for (employee_id, reference), indices in buckets.items():
        if len(indices) < 2:
            continue
        conflicting = _conflicting_pairs(ledger, indices)
        if not conflicting:
            continue
        involved = sorted({i for pair in conflicting for i in pair})
        types = sorted({ledger.events[i].event_type.value for i in involved})
        policy_note = (
            f"; an explicit resolution policy {resolution_policy!r} is configured and "
            f"the applied order is recorded"
            if resolution_policy
            else "; no resolution policy configured, order is not decided by row order"
        )
        ledger.add_finding(
            Finding.from_spec(
                DAT_007,
                f"conflicting same-date events for employee {employee_id!r} on "
                f"{_iso(reference)}: {', '.join(types)}{policy_note}",
                employee_id=employee_id,
                effective_date=reference,
                source_file=ledger.events[involved[0]].lineage.source_file,
                source_row=ledger.events[involved[0]].lineage.source_row,
                actual_value=",".join(types),
            )
        )
        if any(ledger.events[i].event_type is EventType.TRANSFER for i in involved):
            ledger.add_finding(
                Finding.from_spec(
                    TRF_006,
                    f"conflicting transfers for employee {employee_id!r} on "
                    f"{_iso(reference)}{policy_note}",
                    employee_id=employee_id,
                    effective_date=reference,
                    source_file=ledger.events[involved[0]].lineage.source_file,
                    source_row=ledger.events[involved[0]].lineage.source_row,
                )
            )


def _conflicting_pairs(ledger: EventLedger, indices: list[int]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for a in range(len(indices)):
        for b in range(a + 1, len(indices)):
            left = ledger.events[indices[a]]
            right = ledger.events[indices[b]]
            if event_conflicts(left, right):
                pairs.append((indices[a], indices[b]))
    return pairs


def _iso(value: date | None) -> str:
    return value.isoformat() if value else "?"
