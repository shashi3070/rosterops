"""Normalize an ingested event role into canonical :class:`Event` rows.

Each supported event role maps onto one :class:`~rosterops.models.EventType`:
transfers -> transfer, promotions -> promotion, terminations -> termination,
leaves -> leave_start, returns -> leave_return, hires -> hire, rehires ->
rehire, coverage -> temp_coverage.

Termination dates are converted to the canonical half-open convention here
using the configured ``dates.termination_date_semantics`` (``DAT-008``): the
stated date is preserved on ``effective_date`` and the derived exclusive end is
recorded on ``employment_end_exclusive`` so the conversion is auditable.

Rows are never dropped. A row without a usable employee id or effective date is
emitted with ``status=INVALID`` and a finding rather than silently discarded.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from rosterops.domain.dates import employment_exclusive_end
from rosterops.events.ledger import Event, EventLedger, EventStatus, build_fingerprint
from rosterops.io.ingest import IngestedInput
from rosterops.models import EventType, Lineage, TerminationDateSemantics
from rosterops.rules.base import Finding
from rosterops.rules.identifier_rules import ID_002
from rosterops.rules.temporal_rules import DAT_001

__all__ = ["EVENT_ROLE_TYPES", "normalize_events", "segment_normalizers"]

#: Event input role -> canonical event type.
EVENT_ROLE_TYPES: dict[str, EventType] = {
    "transfers": EventType.TRANSFER,
    "promotions": EventType.PROMOTION,
    "terminations": EventType.TERMINATION,
    "leaves": EventType.LEAVE_START,
    "returns": EventType.LEAVE_RETURN,
    "hires": EventType.HIRE,
    "rehires": EventType.REHIRE,
    "coverage": EventType.TEMP_COVERAGE,
}

#: Roles handled generically (single effective dated record) and their date field.
_DEFAULT_DATE_FIELD: dict[str, str] = {
    "transfers": "effective_date",
    "promotions": "effective_date",
    "terminations": "effective_date",
    "returns": "effective_date",
    "hires": "effective_date",
    "rehires": "effective_date",
    "leaves": "leave_start_date",
    "coverage": "coverage_start_date",
}

#: Field names lifted straight onto the canonical event, per role.
_PASSTHROUGH_STRINGS = (
    "event_id",
    "old_value",
    "new_value",
    "from_territory_id",
    "to_territory_id",
    "old_role_code",
    "new_role_code",
    "source_system",
)


def _as_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    return None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_events(
    ingested: IngestedInput,
    *,
    termination_semantics: TerminationDateSemantics,
) -> EventLedger:
    """Normalize one ingested event role into a ledger of :class:`Event` rows."""
    ledger = EventLedger()
    role = ingested.role
    event_type = EVENT_ROLE_TYPES.get(role)
    if event_type is None or ingested.skipped or ingested.frame.height == 0:
        return ledger

    namespace = _namespace_for(role)
    date_field = _DEFAULT_DATE_FIELD[role]
    seen_ids: dict[str, int] = {}

    for row in ingested.frame.iter_rows(named=True):
        lineage = Lineage.from_mapping(row)
        employee_id = _as_str(row.get("employee_id") or row.get("covering_employee_id")) or ""
        event_id = _as_str(row.get("event_id") or row.get("coverage_id"))
        effective = _as_date(row.get(date_field))
        leave_start = _as_date(row.get("leave_start_date"))
        leave_end = _as_date(row.get("leave_end_date"))
        if role == "coverage":
            # Coverage start is the effective date; record the covered territory.
            effective = _as_date(row.get("coverage_start_date"))
            leave_end = _as_date(row.get("coverage_end_date"))

        end_exclusive: date | None = None
        if event_type is EventType.TERMINATION:
            end_exclusive = employment_exclusive_end(effective, termination_semantics)

        event = Event(
            event_type=event_type,
            employee_id=employee_id,
            event_id=event_id,
            effective_date=effective,
            recorded_date=_as_date(row.get("recorded_date")),
            old_value=_as_str(row.get("old_value")),
            new_value=_as_str(row.get("new_value")),
            from_territory_id=_as_str(row.get("from_territory_id")),
            to_territory_id=_as_str(row.get("to_territory_id") or row.get("covered_territory_id")),
            old_role_code=_as_str(row.get("old_role_code")),
            new_role_code=_as_str(row.get("new_role_code")),
            leave_start_date=leave_start,
            leave_end_date=leave_end,
            source_system=_as_str(row.get("source_system")),
            employment_end_exclusive=end_exclusive,
            role=role,
            namespace=namespace,
            lineage=lineage,
        )
        event = _attach_fingerprint(event)
        event = _validate_identity(event, ledger, role, namespace, seen_ids)
        ledger.events.append(event)

    return ledger


def _attach_fingerprint(event: Event) -> Event:
    return replace(
        event,
        fingerprint=build_fingerprint(
            event.event_type,
            event.employee_id,
            event.effective_date,
            from_territory_id=event.from_territory_id,
            to_territory_id=event.to_territory_id,
            old_role_code=event.old_role_code,
            new_role_code=event.new_role_code,
            leave_start_date=event.leave_start_date,
        ),
    )


def _validate_identity(
    event: Event,
    ledger: EventLedger,
    role: str,
    namespace: str,
    seen_ids: dict[str, int],
) -> Event:
    """Emit DAT-001 / ID-002 findings and mark unresolvable rows invalid."""
    if not event.employee_id:
        ledger.add_finding(
            Finding.from_spec(
                DAT_001,
                f"{role} event is missing a usable employee id",
                source_file=event.lineage.source_file,
                source_sheet=event.lineage.source_sheet,
                source_row=event.lineage.source_row,
                event_id=event.event_id,
                actual_value=event.event_id,
            )
        )
        return event.with_status(EventStatus.INVALID, "missing employee id")

    if event.effective_date is None and event.leave_start_date is None:
        ledger.add_finding(
            Finding.from_spec(
                DAT_001,
                f"{role} event has no usable effective/start date",
                employee_id=event.employee_id,
                source_file=event.lineage.source_file,
                source_sheet=event.lineage.source_sheet,
                source_row=event.lineage.source_row,
                event_id=event.event_id,
            )
        )
        return event.with_status(EventStatus.INVALID, "missing effective date")

    if event.event_id is not None:
        seen_ids.setdefault(event.event_id, 0)
        seen_ids[event.event_id] += 1
        if seen_ids[event.event_id] > 1:
            ledger.add_finding(
                Finding.from_spec(
                    ID_002,
                    f"event id {event.event_id!r} is duplicated within namespace {namespace!r}",
                    employee_id=event.employee_id,
                    source_file=event.lineage.source_file,
                    source_sheet=event.lineage.source_sheet,
                    source_row=event.lineage.source_row,
                    event_id=event.event_id,
                    actual_value=event.event_id,
                )
            )
    return event


def _namespace_for(role: str) -> str:
    """Event-ID namespace for a role: the role name itself."""
    return role


def segment_normalizers() -> tuple[str, ...]:
    """Return the event roles the normalizer understands (for discovery)."""
    return tuple(EVENT_ROLE_TYPES)
