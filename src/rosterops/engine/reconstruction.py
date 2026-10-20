"""Event-driven reconstruction (Mode A, REQUIREMENTS §6.3).

Applies active ledger events to the baseline state in deterministic order and
raises lifecycle/transition findings (Groups D/E/F/G/I + DAT-005, ID-006).
Reconstruction is the product's core: the resulting state is queried as of
``as_of`` to materialize roster, assignments, vacancies, and metrics.

Application rules (permitted state changes only):

- hire/rehire : open a new employment episode; rehire must not overwrite a
  prior episode end (EMP-007).
- termination : close employment at the exclusive end (DAT-008 conversion),
  close open assignments and roles; a double termination is flagged (EMP-004).
- transfer    : close the effective primary assignment at the event date and
  open a new primary assignment to the destination — half-open continuity, no
  1-day gap/overlap.
- promotion   : close the effective role at the event date and open the new
  role from it.
- leave_start : open a leave interval; return : close the matching open leave.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops.domain.intervals import intervals_overlap
from rosterops.engine.context import EngineContext
from rosterops.engine.state import (
    AssignmentInterval,
    CoverageRecord,
    EmployeeRecord,
    EmploymentEpisode,
    LeaveInterval,
    RoleInterval,
)
from rosterops.events.ledger import Event, EventLedger, EventStatus
from rosterops.models import EventType
from rosterops.rules import coverage_rules as C
from rosterops.rules import employment_rules as E
from rosterops.rules import identifier_rules as I
from rosterops.rules import leave_rules as L
from rosterops.rules import promotion_rules as P
from rosterops.rules import transfer_rules as TR

__all__ = ["apply_events", "materialize_assignments", "materialize_events_frame"]

#: Territory-master frame role name.
_TERRITORY_ROLE = "territories"


def apply_events(ctx: EngineContext, ledger: EventLedger) -> tuple[str, ...]:
    """Apply active events to ``ctx.state``; return the applied event order."""
    applied: list[str] = []
    terminated: set[str] = set()
    known = set(ctx.state.employees)
    territories = _known_territories(ctx)

    for event in ledger.active_events():
        if event.status is not EventStatus.ACTIVE:
            continue
        eid = event.employee_id
        effective = event.effective_date or event.leave_start_date

        if event.event_type is EventType.HIRE:
            _apply_hire(ctx, event, known)
        elif event.event_type is EventType.REHIRE:
            _apply_rehire(ctx, event, known)
        elif event.event_type is EventType.TERMINATION:
            _apply_termination(ctx, event, eid, known, terminated)
        elif event.event_type is EventType.TRANSFER:
            _apply_transfer(ctx, event, eid, known, territories, terminated)
        elif event.event_type is EventType.PROMOTION:
            _apply_promotion(ctx, event, eid, known, terminated)
        elif event.event_type is EventType.LEAVE_START:
            _apply_leave_start(ctx, event, eid, known)
        elif event.event_type is EventType.LEAVE_RETURN:
            _apply_leave_return(ctx, event, eid, known)
        elif event.event_type is EventType.TEMP_COVERAGE:
            _apply_coverage(ctx, event, known, territories)

        applied.append(event.namespaced_id or event.fingerprint)
        _ = effective
    return tuple(applied)


# --------------------------------------------------------------------------- #
# individual appliers
# --------------------------------------------------------------------------- #
def _apply_hire(ctx: EngineContext, event: Event, known: set[str]) -> None:
    eid = event.employee_id
    effective = event.effective_date
    if not eid or effective is None:
        ctx.emit(E.EMP_001, "hire event lacks identity or effective date", event_id=event.event_id)
        return
    if any(ep.end is None for ep in ctx.state.employment.get(eid, [])):
        ctx.emit(
            E.EMP_002,
            f"hire for {eid!r} conflicts with an active employment episode",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=effective,
        )
    ctx.state.add_employee(EmployeeRecord(employee_id=eid))
    ctx.state.add_employment(
        EmploymentEpisode(employee_id=eid, start=effective, source_event_id=event.event_id)
    )
    ctx.state.add_role(
        RoleInterval(employee_id=eid, role_code=event.new_role_code, start=effective)
    )
    known.add(eid)


def _apply_rehire(ctx: EngineContext, event: Event, known: set[str]) -> None:
    eid = event.employee_id
    effective = event.effective_date
    if not eid or effective is None:
        ctx.emit(
            E.EMP_001, "rehire event lacks identity or effective date", event_id=event.event_id
        )
        return
    # EMP-007: rehire opens a distinct episode; prior end preserved.
    episodes = ctx.state.employment.get(eid, [])
    if not episodes:
        ctx.emit(
            E.EMP_003,
            f"rehire for {eid!r} has no prior employment episode",
            employee_id=eid,
            event_id=event.event_id,
        )
    if any(ep.end is None for ep in episodes):
        ctx.emit(
            E.EMP_007,
            f"rehire for {eid!r} while a prior episode is still open",
            employee_id=eid,
            event_id=event.event_id,
        )
    ctx.state.add_employee(EmployeeRecord(employee_id=eid))
    ctx.state.add_employment(
        EmploymentEpisode(employee_id=eid, start=effective, source_event_id=event.event_id)
    )
    ctx.state.add_role(
        RoleInterval(employee_id=eid, role_code=event.new_role_code, start=effective)
    )
    known.add(eid)


def _apply_termination(
    ctx: EngineContext,
    event: Event,
    eid: str,
    known: set[str],
    terminated: set[str],
) -> None:
    effective = event.effective_date
    if not eid or effective is None:
        ctx.emit(E.EMP_001, "termination lacks identity or effective date", event_id=event.event_id)
        return
    if eid not in known and not ctx.state.employment.get(eid):
        ctx.emit(
            E.EMP_003,
            f"termination for {eid!r} references no known employment episode",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=effective,
        )
        return
    if eid in terminated:
        ctx.emit(
            E.EMP_004,
            f"duplicate termination for {eid!r}",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=effective,
        )
        return
    terminated.add(eid)
    end = event.employment_end_exclusive or effective
    ctx.state.close_employment(eid, end, event.event_id)
    ctx.state.close_open_assignments(eid, end, event.event_id)
    ctx.state.close_open_roles(eid, end, event.event_id)


def _apply_transfer(
    ctx: EngineContext,
    event: Event,
    eid: str,
    known: set[str],
    territories: set[str] | None,
    terminated: set[str],
) -> None:
    effective = event.effective_date
    if not eid or effective is None:
        return
    if eid not in known:
        ctx.emit(
            I.ID_006,
            f"transfer references unknown employee {eid!r}",
            employee_id=eid,
            event_id=event.event_id,
        )
        ctx.emit(
            TR.TRF_001,
            f"transfer references unknown employee {eid!r}",
            employee_id=eid,
            event_id=event.event_id,
        )
        return
    if eid in terminated:
        ctx.emit(
            E.EMP_005,
            f"transfer for {eid!r} occurs after termination",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=effective,
        )
        return
    if event.from_territory_id and event.to_territory_id == event.from_territory_id:
        ctx.emit(
            TR.TRF_003,
            f"transfer for {eid!r} has identical source and destination "
            f"{event.from_territory_id!r}",
            employee_id=eid,
            event_id=event.event_id,
        )
    if territories is not None and event.to_territory_id not in territories:
        ctx.emit(
            TR.TRF_004,
            f"transfer destination {event.to_territory_id!r} is absent from the master",
            employee_id=eid,
            event_id=event.event_id,
        )

    current = ctx.state.primary_territory(eid, _before(effective))
    expected = event.from_territory_id
    if expected is not None and current is not None and expected != current:
        ctx.emit(
            TR.TRF_002,
            f"transfer for {eid!r} states source {expected!r} but effective "
            f"assignment is {current!r}",
            employee_id=eid,
            event_id=event.event_id,
            actual_value=expected,
            expected_value=current,
        )
    # Close the open primary assignment; open the new one at effective date.
    ctx.state.close_open_assignments(eid, effective, event.event_id)
    ctx.state.add_assignment(
        AssignmentInterval(
            employee_id=eid,
            territory_id=event.to_territory_id,
            assignment_type="primary",
            is_primary=True,
            start=effective,
            source_event_id=event.event_id,
        )
    )


def _apply_promotion(
    ctx: EngineContext,
    event: Event,
    eid: str,
    known: set[str],
    terminated: set[str],
) -> None:
    effective = event.effective_date
    if not eid or effective is None:
        return
    if event.new_role_code is None and event.new_value is None:
        ctx.emit(
            P.PRO_001,
            f"promotion for {eid!r} has no destination role",
            employee_id=eid,
            event_id=event.event_id,
        )
        return
    if eid not in known:
        ctx.emit(
            I.ID_006,
            f"promotion references unknown employee {eid!r}",
            employee_id=eid,
            event_id=event.event_id,
        )
        return
    if eid in terminated:
        ctx.emit(
            E.EMP_005,
            f"promotion for {eid!r} occurs after termination",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=effective,
        )
        return
    ctx.state.close_open_roles(eid, effective, event.event_id)
    ctx.state.add_role(
        RoleInterval(
            employee_id=eid,
            role_code=event.new_role_code or event.new_value,
            start=effective,
            source_event_id=event.event_id,
        )
    )


def _apply_leave_start(ctx: EngineContext, event: Event, eid: str, known: set[str]) -> None:
    start = event.leave_start_date or event.effective_date
    if not eid or start is None:
        ctx.emit(L.LOA_001, "leave event lacks a valid start date", event_id=event.event_id)
        return
    if eid not in known and not ctx.state.employment.get(eid):
        ctx.emit(
            L.LOA_002,
            f"leave for {eid!r} references no known employment",
            employee_id=eid,
            event_id=event.event_id,
        )
        return
    end = event.leave_end_date
    end = event.leave_end_date
    employment_start = _employment_start(ctx, eid)
    if employment_start is not None and start < employment_start:
        ctx.emit(
            L.LOA_001,
            f"leave for {eid!r} starts {start} before employment start {employment_start}",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=start,
            actual_value=f"{start}",
            expected_value=f">={employment_start}",
        )
    if end is not None and end < start:
        ctx.emit(
            L.LOA_001,
            f"leave for {eid!r} ends {end} before it starts {start}",
            employee_id=eid,
            event_id=event.event_id,
            actual_value=f"{start}..{end}",
        )
    for existing in ctx.state.leaves.get(eid, []):
        if existing.start and intervals_overlap(start, end, existing.start, existing.end):
            if not ctx.config.policies.leave.allow_overlapping_leave_types:
                ctx.emit(
                    L.LOA_003,
                    f"overlapping leave for {eid!r}",
                    employee_id=eid,
                    event_id=event.event_id,
                    effective_date=start,
                )
                break
    ctx.state.add_leave(
        LeaveInterval(employee_id=eid, start=start, end=end, source_event_id=event.event_id)
    )


def _apply_leave_return(ctx: EngineContext, event: Event, eid: str, known: set[str]) -> None:
    day = event.effective_date or event.leave_start_date
    if not eid or day is None:
        ctx.emit(L.LOA_004, "return event lacks a valid date", event_id=event.event_id)
        return
    # Close the open leave interval at the return date.
    open_leaves = [
        (i, lv)
        for i, lv in enumerate(ctx.state.leaves.get(eid, []))
        if lv.end is None and lv.start is not None
    ]
    if not open_leaves:
        # A return whose leave already carries an explicit end date is redundant
        # (the bounded interval already closes it): benign. LOA-004 fires only
        # when the employee has no leave history at all.
        if ctx.state.leaves.get(eid):
            return
        ctx.emit(
            L.LOA_004,
            f"return for {eid!r} has no open leave to close",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
        )
        return
    index, leave = open_leaves[0]
    if day < (leave.start or day):
        ctx.emit(
            L.LOA_004,
            f"return for {eid!r} on {day} precedes leave start {leave.start}",
            employee_id=eid,
            event_id=event.event_id,
        )
        return
    ctx.state.leaves[eid][index] = LeaveInterval(
        employee_id=eid, start=leave.start, end=day, source_event_id=leave.source_event_id
    )


def _apply_coverage(
    ctx: EngineContext,
    event: Event,
    known: set[str],
    territories: set[str] | None,
) -> None:
    start = event.effective_date or event.leave_start_date
    covering = event.employee_id
    territory = event.to_territory_id or event.from_territory_id
    if not covering or start is None:
        ctx.emit(C.COV_002, "coverage record lacks a valid interval", event_id=event.event_id)
        return
    if covering not in known:
        ctx.emit(
            C.COV_001,
            f"coverage references unknown covering employee {covering!r}",
            employee_id=covering,
            event_id=event.event_id,
        )
    if territories is not None and territory is not None and territory not in territories:
        ctx.emit(
            C.COV_001,
            f"coverage references unknown territory {territory!r}",
            employee_id=covering,
            territory_id=territory,
            event_id=event.event_id,
        )
    end = event.leave_end_date
    if end is not None and end < start:
        ctx.emit(
            C.COV_002,
            f"coverage for {covering!r} ends before it starts",
            employee_id=covering,
            event_id=event.event_id,
        )
    ctx.state.add_coverage(
        CoverageRecord(
            covering_employee_id=covering,
            covered_territory_id=territory,
            covered_employee_id=event.old_value,
            start=start,
            end=end,
            source_event_id=event.event_id,
        )
    )


# --------------------------------------------------------------------------- #
# materialization
# --------------------------------------------------------------------------- #
def materialize_events_frame(ledger: EventLedger) -> pl.DataFrame:
    """Serialize the ledger to a Polars DataFrame with status + lineage."""
    rows = []
    for event in ledger.events:
        rows.append(
            {
                "event_id": event.event_id,
                "namespaced_id": event.namespaced_id,
                "event_type": event.event_type.value,
                "employee_id": event.employee_id,
                "effective_date": event.effective_date,
                "recorded_date": event.recorded_date,
                "from_territory_id": event.from_territory_id,
                "to_territory_id": event.to_territory_id,
                "old_role_code": event.old_role_code,
                "new_role_code": event.new_role_code,
                "leave_start_date": event.leave_start_date,
                "leave_end_date": event.leave_end_date,
                "status": event.status.value,
                "fingerprint": event.fingerprint,
                "source_file": event.lineage.source_file,
                "source_sheet": event.lineage.source_sheet,
                "source_row": event.lineage.source_row,
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def materialize_assignments(ctx: EngineContext) -> pl.DataFrame:
    """Materialize all assignment intervals as a Polars DataFrame."""
    rows = []
    for eid in ctx.state.employee_ids():
        for assignment in ctx.state.assignments.get(eid, []):
            rows.append(
                {
                    "employee_id": assignment.employee_id,
                    "territory_id": assignment.territory_id,
                    "assignment_type": assignment.assignment_type,
                    "is_primary": assignment.is_primary,
                    "effective_from": assignment.start,
                    "effective_to": assignment.end,
                    "assignment_status": assignment.assignment_status,
                    "source_event_id": assignment.source_event_id,
                }
            )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort(["employee_id", "effective_from"])


def _before(day: date) -> date:
    from datetime import timedelta

    return day - timedelta(days=1)


def _employment_start(ctx: EngineContext, eid: str) -> date | None:
    starts = [ep.start for ep in ctx.state.employment.get(eid, []) if ep.start is not None]
    return min(starts) if starts else None


def _known_territories(ctx: EngineContext) -> set[str] | None:
    frame = ctx.frame(_TERRITORY_ROLE)
    if frame is None:
        return None
    return {
        str(row["territory_id"]).strip()
        for row in frame.iter_rows(named=True)
        if row.get("territory_id") is not None
    }
