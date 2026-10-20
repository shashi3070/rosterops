"""Materialize the reconstructed roster as of ``as_of`` (REQUIREMENTS §11.1).

The roster is the employee-centric view at the cutoff: each employee with their
employment status, current role, primary territory, and on-leave flag. Headcount
is always the distinct employee count under employment-date semantics.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops.engine.context import EngineContext

__all__ = ["ROSTER_COLUMNS", "materialize_roster"]

ROSTER_COLUMNS = (
    "employee_id",
    "employee_status",
    "grade_code",
    "manager_id",
    "business_unit",
    "country",
    "region_id",
    "district_id",
    "role_code",
    "territory_id",
    "is_primary",
    "on_leave",
    "active",
    "as_of",
)


def materialize_roster(ctx: EngineContext, as_of: date) -> pl.DataFrame:
    """Build the as-of roster frame from the reconstructed state."""
    rows: list[dict[str, object]] = []
    for eid in ctx.state.employee_ids():
        record = ctx.state.employees[eid]
        active = any(ep.active_on(as_of) for ep in ctx.state.employment.get(eid, []))
        territory = ctx.state.primary_territory(eid, as_of)
        assignments = ctx.state.active_assignments(eid, as_of)
        is_primary = any(a.is_primary and a.territory_id == territory for a in assignments)
        status = record.employee_status
        if status is None:
            status = "Active" if active else "Inactive"
        rows.append(
            {
                "employee_id": eid,
                "employee_status": status,
                "grade_code": record.grade_code,
                "manager_id": record.manager_id,
                "business_unit": record.business_unit,
                "country": record.country,
                "region_id": record.region_id,
                "district_id": record.district_id,
                "role_code": ctx.state.role_on(eid, as_of),
                "territory_id": territory,
                "is_primary": is_primary,
                "on_leave": ctx.state.on_leave(eid, as_of),
                "active": active,
                "as_of": as_of,
            }
        )
    if not rows:
        return pl.DataFrame(schema={c: pl.String for c in ROSTER_COLUMNS})
    return pl.DataFrame(rows).select(list(ROSTER_COLUMNS)).sort("employee_id")
