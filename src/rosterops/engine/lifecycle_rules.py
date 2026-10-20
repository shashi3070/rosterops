"""Post-reconstruction lifecycle rules (Groups C/E/F/G/I) for Mode A.

Runs after :func:`rosterops.engine.reconstruction.apply_events`, over the applied
ledger and the reconstructed ``ctx.state``. Every finding cites the offending
event; nothing here mutates state. Invariants that should hold by construction
(``COV-005``, ``LOA-008``) are still evaluated as guards, so a regression that
breaks the invariant surfaces as a finding rather than silently. ``DAT-008`` is
emitted during normalization where termination semantics are applied.

Deferred (see ``IMPLEMENTATION_PHASES.md`` §5): ``REC-008`` two-snapshot
comparison depends on the deferred two-snapshot mode (DEF-001).
"""

from __future__ import annotations

from datetime import date

from rosterops.engine.context import EngineContext
from rosterops.events.ledger import Event, EventLedger, EventStatus
from rosterops.models import EventType
from rosterops.rules import coverage_rules as C
from rosterops.rules import leave_rules as L
from rosterops.rules import promotion_rules as P
from rosterops.rules import reconciliation_rules as R
from rosterops.rules import temporal_rules as T
from rosterops.rules import territory_rules as TE
from rosterops.rules import transfer_rules as TR

__all__ = ["run_lifecycle_rules"]

#: Default maximum concurrent coverage records per covering employee.
_DEFAULT_COVERAGE_CAPACITY = 1


def run_lifecycle_rules(ctx: EngineContext, ledger: EventLedger) -> None:
    """Emit lifecycle findings from the applied ledger + reconstructed state."""
    active = [e for e in ledger.events if e.status is EventStatus.ACTIVE]
    termination_end = _termination_ends(active)
    role_successors = _role_successors(ctx)

    for event in active:
        eid = event.employee_id
        day = event.effective_date or event.leave_start_date
        end = termination_end.get(eid)
        if event.event_type is EventType.TRANSFER:
            _transfer_rules(ctx, event, eid, day, end)
        elif event.event_type is EventType.PROMOTION:
            _promotion_rules(ctx, event, eid, day, end, role_successors)
        elif event.event_type is EventType.LEAVE_START:
            _leave_rules(ctx, event, eid, day, end)
        elif event.event_type is EventType.TEMP_COVERAGE:
            _coverage_rules(ctx, event, eid, day)
        if day is not None and end is not None and day > end:
            ctx.emit(
                T.DAT_005,
                f"{event.event_type.value} for {eid!r} on {day} occurs after termination ({end})",
                employee_id=eid,
                event_id=event.event_id,
                effective_date=day,
            )

    _leave_metrics(ctx, active)
    _assignment_reconciliation(ctx, ledger)
    _vacancy_intervals(ctx)


def _vacancy_intervals(ctx: EngineContext) -> None:
    """TER-007: vacancy runs from the prior assignment's end to the next start."""
    territories = ctx.frame("territories")
    if territories is None:
        return
    day = ctx.as_of or date.max
    for row in territories.iter_rows(named=True):
        tid = row.get("territory_id")
        requires = row.get("requires_primary_owner")
        if tid is None or not _truthy(requires):
            continue
        tid = str(tid)
        occupied = any(
            a.territory_id == tid and a.is_primary
            for eid in ctx.state.employee_ids()
            for a in ctx.state.active_assignments(eid, day)
        )
        if occupied:
            continue
        prior_ends = [
            a.end
            for eid in ctx.state.employee_ids()
            for a in ctx.state.assignments.get(eid, [])
            if a.territory_id == tid and a.is_primary and a.end is not None
        ]
        start = max(prior_ends) if prior_ends else None
        if start is None:
            continue
        ctx.emit(
            TE.TER_007,
            f"territory {tid!r} is vacant in [{start.isoformat()}, {day.isoformat()}] "
            f"(half-open; ends when a new eligible primary begins)",
            territory_id=tid,
            severity_override=False,
        )


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "yes", "y", "1"}
    return False


# --------------------------------------------------------------------------- #
# transfer (Group E)
# --------------------------------------------------------------------------- #
def _transfer_rules(
    ctx: EngineContext, event: Event, eid: str, day: date | None, end: date | None
) -> None:
    if day is None:
        return
    start = _employment_start(ctx, eid)
    if start is not None and day < start:
        ctx.emit(
            TR.TRF_005,
            f"transfer for {eid!r} on {day} precedes employment start {start}",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
        )
    if end is not None and day > end:
        ctx.emit(
            TR.TRF_005,
            f"transfer for {eid!r} on {day} occurs after termination ({end})",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
        )
    # TRF-007: after the transfer the employee must hold exactly one primary.
    primaries = {
        a.territory_id
        for a in ctx.state.active_assignments(eid, day)
        if a.is_primary and a.territory_id
    }
    if len(primaries) > 1:
        ctx.emit(
            TR.TRF_007,
            f"post-transfer state for {eid!r} has multiple active primaries: "
            f"{', '.join(sorted(primaries))}",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
        )
    # TRF-008: informational — one event accounts for one out and one in.
    ctx.emit(
        TR.TRF_008,
        f"transfer {event.event_id!r} counts as 1 event, 1 out of "
        f"{event.from_territory_id!r}, 1 in to {event.to_territory_id!r}",
        employee_id=eid,
        event_id=event.event_id,
        effective_date=day,
        severity_override=False,
    )


# --------------------------------------------------------------------------- #
# promotion (Group F)
# --------------------------------------------------------------------------- #
def _promotion_rules(
    ctx: EngineContext,
    event: Event,
    eid: str,
    day: date | None,
    end: date | None,
    role_successors: dict[str, list[str]],
) -> None:
    if day is None:
        return
    new_role = event.new_role_code or event.new_value
    old_role = event.old_role_code or ctx.state.role_on(eid, _before(day))
    if end is not None and day > end:
        ctx.emit(
            P.PRO_004,
            f"promotion for {eid!r} on {day} occurs after termination ({end})",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
        )
    if old_role and new_role and role_successors:
        allowed = role_successors.get(old_role)
        if allowed is not None and allowed and new_role not in allowed:
            ctx.emit(
                P.PRO_002,
                f"role transition {old_role!r} -> {new_role!r} for {eid!r} is not "
                f"permitted (allowed: {', '.join(allowed)})",
                employee_id=eid,
                event_id=event.event_id,
                effective_date=day,
                severity_override=False,
            )
    if old_role and new_role and old_role == new_role:
        ctx.emit(
            P.PRO_005,
            f"promotion for {eid!r} leaves the role unchanged ({old_role!r})",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
        )


# --------------------------------------------------------------------------- #
# leave (Group G)
# --------------------------------------------------------------------------- #
def _leave_rules(
    ctx: EngineContext, event: Event, eid: str, day: date | None, end: date | None
) -> None:
    if day is None:
        return
    if end is not None and day > end:
        ctx.emit(
            L.LOA_006,
            f"leave for {eid!r} starts {day} after termination ({end})",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
        )
    # LOA-007: required coverage during leave (policy-gated).
    if not ctx.config.policies.leave.coverage_required_by_default:
        return
    territory = ctx.state.primary_territory(eid, day)
    if territory is None:
        return
    has_coverage = any(
        c.covered_territory_id == territory and c.covering_employee_id != eid
        for c in ctx.state.coverage
    )
    if not has_coverage:
        ctx.emit(
            L.LOA_007,
            f"no temporary coverage arranged for territory {territory!r} during "
            f"{eid!r}'s leave starting {day}",
            employee_id=eid,
            territory_id=territory,
            event_id=event.event_id,
            effective_date=day,
            severity_override=False,
        )


def _leave_metrics(ctx: EngineContext, active: list[Event]) -> None:
    starts = sum(1 for e in active if e.event_type is EventType.LEAVE_START)
    returns = sum(1 for e in active if e.event_type is EventType.LEAVE_RETURN)
    cutoff = ctx.as_of or date.max
    currently = sum(1 for eid in ctx.state.employee_ids() if ctx.state.on_leave(eid, cutoff))
    ctx.emit(
        L.LOA_009,
        f"leave metrics: {starts} start(s), {returns} return(s), {currently} "
        f"currently absent at {cutoff}",
        severity_override=False,
    )
    open_leaves = [
        lv
        for records in ctx.state.leaves.values()
        for lv in records
        if lv.end is None and lv.start is not None and lv.start <= cutoff
    ]
    if open_leaves:
        ctx.emit(
            L.LOA_010,
            f"{len(open_leaves)} leave(s) still open at {cutoff} (counted as starts / "
            f"currently absent, not invalid)",
            actual_value=str(len(open_leaves)),
            severity_override=False,
        )


# --------------------------------------------------------------------------- #
# coverage (Group I)
# --------------------------------------------------------------------------- #
def _coverage_rules(ctx: EngineContext, event: Event, eid: str, day: date | None) -> None:
    if day is None:
        return
    covered = event.old_value
    if covered and not _has_leave(ctx, covered):
        ctx.emit(
            C.COV_003,
            f"coverage by {eid!r} references absence of {covered!r} but no leave record exists",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
            severity_override=False,
        )
    # COV-004: concurrent coverage beyond capacity.
    capacity = ctx.param("COV-004", "max_concurrent_coverages")
    cap = capacity if isinstance(capacity, int) else _DEFAULT_COVERAGE_CAPACITY
    concurrent = sum(
        1
        for c in ctx.state.coverage
        if c.covering_employee_id == eid
        and c.start is not None
        and c.start <= day
        and (c.end is None or day < c.end)
    )
    if concurrent > cap:
        ctx.emit(
            C.COV_004,
            f"covering employee {eid!r} holds {concurrent} concurrent coverages "
            f"(capacity {cap}) on {day}",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
            severity_override=False,
        )
    # COV-005: temporary coverage must not remove the covering employee's home
    # assignment. Guard: the covering employee must retain a home assignment.
    if not ctx.state.active_assignments(eid, day) and not ctx.state.assignments.get(eid):
        ctx.emit(
            C.COV_005,
            f"covering employee {eid!r} has no home assignment; coverage must not "
            f"replace the home roster",
            employee_id=eid,
            event_id=event.event_id,
            effective_date=day,
        )


# --------------------------------------------------------------------------- #
# reconciliation (Group K)
# --------------------------------------------------------------------------- #
def _assignment_reconciliation(ctx: EngineContext, ledger: EventLedger) -> None:
    event_ids = {e.event_id for e in ledger.events}
    unexplained = [
        a
        for records in ctx.state.assignments.values()
        for a in records
        if a.source_event_id is not None and a.source_event_id not in event_ids
    ]
    if unexplained:
        first = unexplained[0]
        ctx.emit(
            R.REC_004,
            f"{len(unexplained)} assignment interval(s) not explained by the ledger "
            f"(e.g. employee {first.employee_id!r}, source {first.source_event_id!r})",
            actual_value=str(len(unexplained)),
        )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _termination_ends(active: list[Event]) -> dict[str, date]:
    ends: dict[str, date] = {}
    for event in active:
        if event.event_type is not EventType.TERMINATION:
            continue
        end = event.employment_end_exclusive or event.effective_date
        if end is not None:
            ends[event.employee_id] = end
    return ends


def _employment_start(ctx: EngineContext, eid: str) -> date | None:
    episodes = ctx.state.employment.get(eid, [])
    starts = [ep.start for ep in episodes if ep.start is not None]
    return min(starts) if starts else None


def _has_leave(ctx: EngineContext, eid: str) -> bool:
    return bool(ctx.state.leaves.get(eid))


def _role_successors(ctx: EngineContext) -> dict[str, list[str]]:
    frame = ctx.frame("roles")
    if frame is None or "allowed_successor_role_codes" not in frame.columns:
        return {}
    out: dict[str, list[str]] = {}
    for row in frame.iter_rows(named=True):
        code = row.get("role_code")
        successors = row.get("allowed_successor_role_codes")
        if code is None or not isinstance(successors, list):
            continue
        out[str(code)] = [str(x) for x in successors]
    return out


def _before(day: date) -> date:
    from datetime import timedelta

    return day - timedelta(days=1)
