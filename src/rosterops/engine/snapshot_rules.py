"""Mode B (snapshot) rule implementations.

These rules operate on canonical baseline/snapshot frames plus the optional
territory/normalized master frames. They raise findings through the shared
:class:`~rosterops.engine.context.EngineContext`, which applies per-rule
enable/severity overrides.

Implemented here (REQUIREMENTS §8, Phase 4):
ID-001, ID-003, ID-004, DAT-001, DAT-002, DAT-003, DAT-004, EMP-006, EMP-008,
LOA-005, TRF-009, GRN-* (via baseline), TER-001..006/008/009, ORG-001..005,
REC-005, REC-007, PRO-006.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl

from rosterops.domain.intervals import find_overlapping_pairs
from rosterops.engine.context import EngineContext
from rosterops.engine.state import AssignmentInterval
from rosterops.rules import employment_rules as D
from rosterops.rules import hierarchy_rules as H
from rosterops.rules import identifier_rules as I
from rosterops.rules import leave_rules as L
from rosterops.rules import promotion_rules as P
from rosterops.rules import reconciliation_rules as R
from rosterops.rules import temporal_rules as T
from rosterops.rules import territory_rules as TE
from rosterops.rules import transfer_rules as TR

__all__ = ["run_snapshot_rules", "run_state_rules"]

_TERRITORY_MASTER_ROLES = ("territories",)


def run_state_rules(ctx: EngineContext) -> None:
    """Mode A: state-based rules over the reconstructed as-of roster.

    Runs territory/primary/capacity/final-status checks against
    ``ctx.state`` at ``as_of`` plus hierarchy checks against the static
    employee master frame. Event-specific lifecycle rules are raised during
    application (:mod:`rosterops.engine.reconstruction`).
    """
    baseline = ctx.frame("baseline")
    if baseline is not None:
        _hierarchy_rules(ctx, baseline)
    _territory_rules(ctx, pl.DataFrame())
    day = ctx.as_of or date.max
    active = ctx.state.active_employee_ids(day)
    ctx.emit(
        D.EMP_008,
        f"headcount computed as distinct employees active on as-of = {len(active)} "
        f"(leave does not reduce headcount)",
        actual_value=str(len(active)),
        severity_override=False,
    )
    _reconciliation_rules(ctx, pl.DataFrame(), snapshot=False)


def run_snapshot_rules(ctx: EngineContext) -> None:
    """Execute all Mode B rules against the context."""
    frame = ctx.frame("baseline")
    if frame is None:
        frame = ctx.frame("snapshot")
    if frame is None:
        return
    _identifier_rules(ctx, frame)
    _temporal_rules(ctx, frame)
    _employment_rules(ctx, frame)
    _hierarchy_rules(ctx, frame)
    _territory_rules(ctx, frame)
    _leave_rules(ctx, frame)
    _transfer_rules(ctx, frame)
    _promotion_rules(ctx, frame)
    _reconciliation_rules(ctx, frame, snapshot=True)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _rows(frame: pl.DataFrame) -> list[dict[str, object]]:
    return list(frame.iter_rows(named=True))


def _s(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _b(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "yes", "y", "1"}
    return False


def _i(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _lineage(row: dict[str, object]) -> dict[str, Any]:
    return {
        "source_file": _s(row.get("source_file")),
        "source_sheet": _s(row.get("source_sheet")),
        "source_row": row.get("source_row"),
    }


# --------------------------------------------------------------------------- #
# Group B — identifiers
# --------------------------------------------------------------------------- #
def _identifier_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    # ID-001: employee id non-null/non-empty.
    for row in _rows(frame):
        if _s(row.get("employee_id")) is None:
            ctx.emit(I.ID_001, "record has no employee id", **_lineage(row))

    # ID-003: duplicates at declared grain.
    keys = list(_grain_keys(ctx))
    if keys and frame.height:
        present = [k for k in keys if k in frame.columns]
        if len(present) == len(keys):
            grouped = frame.group_by(present).len().filter(pl.col("len") > 1)
            for row in grouped.iter_rows(named=True):
                detail = ", ".join(f"{k}={row.get(k)!r}" for k in keys)
                ctx.emit(
                    I.ID_003,
                    f"duplicate record at declared grain: {detail} (x{row['len']})",
                    actual_value=str(row["len"]),
                )

    # ID-004: duplicate assignment key (employee, territory, type, start).
    akeys = ["employee_id", "territory_id", "assignment_type", "effective_from"]
    if all(k in frame.columns for k in akeys):
        grouped = (
            frame.filter(pl.col("territory_id").is_not_null())
            .group_by(akeys)
            .len()
            .filter(pl.col("len") > 1)
        )
        for row in grouped.iter_rows(named=True):
            ctx.emit(
                I.ID_004,
                f"duplicate assignment key for employee {row.get('employee_id')!r} "
                f"territory {row.get('territory_id')!r} (x{row['len']})",
                employee_id=_s(row.get("employee_id")),
                territory_id=_s(row.get("territory_id")),
            )


def _grain_keys(ctx: EngineContext) -> tuple[str, ...]:
    from rosterops.models import grain_keys

    return grain_keys(ctx.config.data.grain, ctx.config.data.grain_keys)


# --------------------------------------------------------------------------- #
# Group C — temporal
# --------------------------------------------------------------------------- #
def _temporal_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    # DAT-001: effective_from valid/parseable (present-but-null when column exists).
    if "effective_from" in frame.columns:
        for row in _rows(frame):
            if row.get("effective_from") is None and _s(row.get("territory_id")):
                ctx.emit(
                    T.DAT_001,
                    "assignment has no usable effective_from date",
                    employee_id=_s(row.get("employee_id")),
                    territory_id=_s(row.get("territory_id")),
                    **_lineage(row),
                )

    # DAT-002: interval bounds valid (end >= start).
    if {"effective_from", "effective_to"} <= set(frame.columns):
        for row in _rows(frame):
            start = row.get("effective_from")
            end = row.get("effective_to")
            if isinstance(start, date) and isinstance(end, date) and end < start:
                ctx.emit(
                    T.DAT_002,
                    f"invalid interval: effective_to {end} < effective_from {start}",
                    employee_id=_s(row.get("employee_id")),
                    territory_id=_s(row.get("territory_id")),
                    actual_value=f"{start}..{end}",
                    **_lineage(row),
                )

    # DAT-003: incompatible assignment overlaps per employee.
    _overlap_rules(ctx, frame)


def _overlap_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    by_employee: dict[str, list[AssignmentInterval]] = {}
    for row in _rows(frame):
        eid = _s(row.get("employee_id"))
        territory = _s(row.get("territory_id"))
        start = row.get("effective_from")
        if eid is None or territory is None or not isinstance(start, date):
            continue
        raw_end = row.get("effective_to")
        end = raw_end if isinstance(raw_end, date) else None
        by_employee.setdefault(eid, []).append(
            AssignmentInterval(
                employee_id=eid,
                territory_id=territory,
                assignment_type=_s(row.get("assignment_type")),
                is_primary=_b(row.get("is_primary")),
                start=start,
                end=end,
            )
        )
    for eid, intervals in by_employee.items():
        keyed = [(f"{a.territory_id}|{a.start}", a.start, a.end) for a in intervals if a.start]
        for pair in find_overlapping_pairs(keyed):
            a_terr = pair.key_a.split("|", 1)[0]
            b_terr = pair.key_b.split("|", 1)[0]
            if a_terr == b_terr:
                continue  # same-territory overlap handled by TER-003
            ov_end = pair.overlap_end.isoformat() if pair.overlap_end else "open"
            ctx.emit(
                T.DAT_003,
                f"overlapping assignments for employee {eid!r}: territories "
                f"{a_terr!r} and {b_terr!r} overlap "
                f"[{pair.overlap_start.isoformat()}, {ov_end})",
                employee_id=eid,
                actual_value=f"[{pair.overlap_start.isoformat()}, {ov_end})",
            )

    # DAT-004: temporal gap in required-coverage intervals (policy-gated warning).
    if ctx.config.policies.leave.coverage_required_by_default:
        _gap_detection(ctx, by_employee)


def _gap_detection(ctx: EngineContext, by_employee: dict[str, list[AssignmentInterval]]) -> None:
    for eid, intervals in by_employee.items():
        ordered = sorted(
            [a for a in intervals if a.start],
            key=lambda a: a.start or date.min,
        )
        prior_end: date | None = None
        for interval in ordered:
            if prior_end is not None and interval.start and interval.start > prior_end:
                ctx.emit(
                    T.DAT_004,
                    f"coverage gap for employee {eid!r} between "
                    f"{prior_end.isoformat()} and {interval.start.isoformat()}",
                    employee_id=eid,
                    actual_value=f"[{prior_end.isoformat()}, {interval.start.isoformat()})",
                )
            if interval.end is None:
                prior_end = date.max
            elif prior_end is None or interval.end > prior_end:
                prior_end = interval.end


# --------------------------------------------------------------------------- #
# Group D — employment
# --------------------------------------------------------------------------- #
def _employment_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    # EMP-006: final status agrees with lifecycle events / dates.
    if "employee_status" in frame.columns:
        for row in _rows(frame):
            status = (_s(row.get("employee_status")) or "").lower()
            end = row.get("employment_end_date")
            if status in {"terminated", "inactive"} and not isinstance(end, date):
                ctx.emit(
                    D.EMP_006,
                    f"employee status {status!r} but employment_end_date is empty",
                    employee_id=_s(row.get("employee_id")),
                    **_lineage(row),
                )

    # EMP-008: headcount uses employment semantics — informational, per employee.
    active = ctx.state.active_employee_ids(ctx.as_of or date.max)
    ctx.emit(
        D.EMP_008,
        f"headcount computed as distinct employees active on as-of = {len(active)} "
        f"(leave does not reduce headcount)",
        actual_value=str(len(active)),
        severity_override=False,
    )


# --------------------------------------------------------------------------- #
# Group J — hierarchy
# --------------------------------------------------------------------------- #
def _hierarchy_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    if "manager_id" not in frame.columns:
        return
    known = {_s(row.get("employee_id")) for row in _rows(frame)}
    manager_of: dict[str, str] = {}
    for row in _rows(frame):
        eid = _s(row.get("employee_id"))
        mid = _s(row.get("manager_id"))
        if eid is None:
            continue
        if mid is None:
            continue
        manager_of[eid] = mid
        if mid not in known:
            ctx.emit(
                H.ORG_001,
                f"manager {mid!r} for employee {eid!r} is not a known employee",
                employee_id=eid,
                actual_value=mid,
                **_lineage(row),
            )
        if mid == eid:
            ctx.emit(
                H.ORG_002,
                f"employee {eid!r} is their own manager",
                employee_id=eid,
                **_lineage(row),
            )

    # ORG-003: reporting cycles.
    for eid in sorted(manager_of):
        seen: list[str] = []
        current: str | None = eid
        while current is not None and current not in seen:
            seen.append(current)
            current = manager_of.get(current)
        if current is not None and current in seen:
            cycle = seen[seen.index(current) :]
            if len(cycle) >= 2:
                ctx.emit(
                    H.ORG_003,
                    f"reporting cycle detected: {' -> '.join([*cycle, cycle[0]])}",
                    employee_id=eid,
                    actual_value=" -> ".join(cycle),
                )

    # ORG-004: manager effective for the date (warning when policy requires).
    if ctx.config.policies.require_active_manager:
        for row in _rows(frame):
            eid = _s(row.get("employee_id"))
            mid = _s(row.get("manager_id"))
            if eid is None or mid is None or mid == eid:
                continue
            end = row.get("employment_end_date")
            if isinstance(end, date) and ctx.as_of and end <= ctx.as_of:
                ctx.emit(
                    H.ORG_004,
                    f"manager {mid!r} for employee {eid!r} is not active on "
                    f"as-of {ctx.as_of.isoformat()}",
                    employee_id=eid,
                    **_lineage(row),
                )

    # ORG-005: org relationships agree with territory hierarchy (if master).
    _org_territory_match(ctx, frame)


def _org_territory_match(ctx: EngineContext, frame: pl.DataFrame) -> None:
    terr = ctx.frame("territories")
    if terr is None or "region_id" not in frame.columns:
        return
    terr_region = {_s(row.get("territory_id")): _s(row.get("region_id")) for row in _rows(terr)}
    for row in _rows(frame):
        territory = _s(row.get("territory_id"))
        if territory is None or territory not in terr_region:
            continue
        emp_region = _s(row.get("region_id"))
        ter_region = terr_region[territory]
        if emp_region and ter_region and emp_region != ter_region:
            ctx.emit(
                H.ORG_005,
                f"employee region {emp_region!r} does not match territory "
                f"{territory!r} region {ter_region!r}",
                employee_id=_s(row.get("employee_id")),
                territory_id=territory,
                **_lineage(row),
            )


# --------------------------------------------------------------------------- #
# Group H — territory
# --------------------------------------------------------------------------- #
def _territory_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    terr = ctx.frame("territories")
    known_territories: set[str] = set()
    requires_owner: dict[str, bool] = {}
    status_of: dict[str, str] = {}
    max_assignees: dict[str, int | None] = {}
    allowed_roles: dict[str, list[str]] = {}
    if terr is not None:
        for row in _rows(terr):
            tid = _s(row.get("territory_id"))
            if tid is None:
                continue
            known_territories.add(tid)
            requires_owner[tid] = _b(row.get("requires_primary_owner"))
            status_of[tid] = (_s(row.get("territory_status")) or "").lower()
            ma = row.get("max_assignees")
            max_assignees[tid] = ma if isinstance(ma, int) else None
            roles = row.get("allowed_roles")
            allowed_roles[tid] = [str(x) for x in roles] if isinstance(roles, list) else []

    # TER-001: assigned territory exists.
    if terr is not None:
        for row in _rows(frame):
            territory = _s(row.get("territory_id"))
            if territory is not None and territory not in known_territories:
                ctx.emit(
                    TE.TER_001,
                    f"assigned territory {territory!r} is absent from the master",
                    employee_id=_s(row.get("employee_id")),
                    territory_id=territory,
                    **_lineage(row),
                )

    # Build per-day assignment view at as_of.
    day = ctx.as_of or date.max
    per_territory_primary: dict[str, list[str]] = {}
    per_territory_all: dict[str, list[str]] = {}
    per_employee_primary: dict[str, list[str]] = {}
    for eid in ctx.state.employee_ids():
        for a in ctx.state.active_assignments(eid, day):
            if a.territory_id is None:
                continue
            per_territory_all.setdefault(a.territory_id, []).append(eid)
            if a.is_primary:
                per_territory_primary.setdefault(a.territory_id, []).append(eid)
                per_employee_primary.setdefault(eid, []).append(a.territory_id)

    # TER-002: max primaries per employee.
    limit = ctx.config.policies.max_primary_territories_per_employee
    for eid, territories in per_employee_primary.items():
        distinct = sorted(set(territories))
        if len(distinct) > limit:
            ctx.emit(
                TE.TER_002,
                f"employee {eid!r} holds {len(distinct)} primary territories "
                f"(limit {limit}): {', '.join(distinct)}",
                employee_id=eid,
                actual_value=str(len(distinct)),
                expected_value=str(limit),
            )

    # TER-003: territory occupancy (same territory primary overlap).
    for territory, primaries in per_territory_primary.items():
        distinct = sorted(set(primaries))
        if len(distinct) > 1:
            ctx.emit(
                TE.TER_003,
                f"territory {territory!r} has {len(distinct)} simultaneous primary "
                f"occupants: {', '.join(distinct)}",
                territory_id=territory,
                actual_value=str(len(distinct)),
            )

    # TER-004: territory role eligibility (warning).
    if terr is not None:
        for row in _rows(frame):
            territory = _s(row.get("territory_id"))
            if territory is None:
                continue
            allowed = allowed_roles.get(territory, [])
            role = _s(row.get("role_code"))
            if allowed and role and role not in allowed:
                ctx.emit(
                    TE.TER_004,
                    f"role {role!r} is not eligible for territory {territory!r} "
                    f"(allowed: {', '.join(allowed)})",
                    employee_id=_s(row.get("employee_id")),
                    territory_id=territory,
                    **_lineage(row),
                )

    # TER-008: capacity.
    for territory, all_assignees in per_territory_all.items():
        cap = max_assignees.get(territory)
        distinct = sorted(set(all_assignees))
        if cap is not None and len(distinct) > cap:
            ctx.emit(
                TE.TER_008,
                f"territory {territory!r} has {len(distinct)} assignees (capacity {cap})",
                territory_id=territory,
                actual_value=str(len(distinct)),
                expected_value=str(cap),
            )

    # TER-009: multiple active territories vs policy.
    if not ctx.config.policies.allow_multiple_active_territories:
        for eid in ctx.state.employee_ids():
            terr_set = {
                a.territory_id for a in ctx.state.active_assignments(eid, day) if a.territory_id
            }
            if len(terr_set) > 1:
                ctx.emit(
                    TE.TER_009,
                    f"employee {eid!r} holds multiple active territories while policy "
                    f"disallows it: {', '.join(sorted(terr_set))}",
                    employee_id=eid,
                )

    # TER-005/TER-006: required-owner vacancies (only with a master).
    _vacancy_findings(ctx, status_of, requires_owner, per_territory_primary)


def _vacancy_findings(
    ctx: EngineContext,
    status_of: dict[str, str],
    requires_owner: dict[str, bool],
    per_territory_primary: dict[str, list[str]],
) -> None:
    if not status_of:
        return
    for territory in sorted(status_of):
        status = status_of[territory]
        needs = requires_owner.get(territory, False)
        occupied = bool(per_territory_primary.get(territory))
        inactive = status not in {"", "active"}
        if active_vacancy := (needs and not occupied and not inactive):
            ctx.emit(
                TE.TER_005,
                f"required-owner territory {territory!r} has no active primary owner",
                territory_id=territory,
                severity_override=False,
            )
        elif not needs or inactive:
            # TER-006: informational, not counted as a vacancy.
            reason = "inactive" if inactive else "does not require a primary owner"
            if not occupied:
                ctx.emit(
                    TE.TER_006,
                    f"territory {territory!r} unassigned but not a vacancy ({reason})",
                    territory_id=territory,
                    severity_override=False,
                )
        _ = active_vacancy


# --------------------------------------------------------------------------- #
# Group G — leave (snapshot branch: LOA-005)
# --------------------------------------------------------------------------- #
def _leave_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    # LOA-005: leave does not silently terminate employment — informational check.
    if "employee_status" in frame.columns:
        for row in _rows(frame):
            status = (_s(row.get("employee_status")) or "").lower()
            if status in {"on_leave", "leave"}:
                ctx.emit(
                    L.LOA_005,
                    f"employee {row.get('employee_id')!r} is on leave; employment "
                    f"status must remain active (leave ≠ termination)",
                    employee_id=_s(row.get("employee_id")),
                    severity_override=False,
                    **_lineage(row),
                )


# --------------------------------------------------------------------------- #
# Group E/F — transfers/promotions snapshot branches
# --------------------------------------------------------------------------- #
def _transfer_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    # TRF-009: multiple-territory assignments respect policy.
    limit = ctx.param("TRF-009", "max_territories_per_employee")
    if limit is None:
        return
    day = ctx.as_of or date.max
    limit_int = _i(limit)
    if limit_int is None:
        return
    for eid in ctx.state.employee_ids():
        terr_set = {
            a.territory_id for a in ctx.state.active_assignments(eid, day) if a.territory_id
        }
        if len(terr_set) > limit_int:
            ctx.emit(
                TR.TRF_009,
                f"employee {eid!r} holds {len(terr_set)} territories (policy max {limit})",
                employee_id=eid,
                actual_value=str(len(terr_set)),
                expected_value=str(limit),
            )


def _promotion_rules(ctx: EngineContext, frame: pl.DataFrame) -> None:
    # PRO-006: promotion counts are event-based; no inference from snapshots.
    ctx.emit(
        P.PRO_006,
        "promotion counts are not derivable from a single snapshot and are "
        "reported as not_available",
        severity_override=False,
    )


# --------------------------------------------------------------------------- #
# Group K — reconciliation snapshot branches
# --------------------------------------------------------------------------- #
def _reconciliation_rules(ctx: EngineContext, frame: pl.DataFrame, *, snapshot: bool) -> None:
    day = ctx.as_of or date.max
    active = ctx.state.active_employee_ids(day)
    # REC-005: vacancy/active-primary reconciliation.
    terr = ctx.frame("territories")
    if terr is not None:
        requires = [
            _s(row.get("territory_id"))
            for row in _rows(terr)
            if _b(row.get("requires_primary_owner"))
        ]
        primaries = {
            a.territory_id
            for eid in active
            for a in ctx.state.active_assignments(eid, day)
            if a.is_primary and a.territory_id
        }
        missing = sorted(t for t in requires if t and t not in primaries)
        if missing:
            ctx.emit(
                R.REC_005,
                f"{len(missing)} required-owner territory(ies) without an active "
                f"primary: {', '.join(missing)}",
                severity_override=False,
                actual_value=str(len(missing)),
            )

    # REC-007: movement summary consistency — in Mode B movements are unavailable.
    if snapshot:
        ctx.emit(
            R.REC_007,
            "historical movement metrics are not derivable from a single snapshot; "
            "they are reported as not_available",
            severity_override=False,
        )
