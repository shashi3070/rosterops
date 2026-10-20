"""Vacancy / coverage analysis producing ``result.vacancies`` (REQUIREMENTS §11.1).

A vacancy is a dated interval for a territory that requires a primary owner but
has none. Vacancy kinds (per §11.1): ``permanently_unassigned``,
``after_transfer``, ``after_termination``, ``coverage_required``,
``coverage_missing``, ``unassigned_by_design``.

Mode B (single snapshot) yields the current vacancy set at ``as_of`` (open-ended
interval). Mode A additionally derives intervals from the event ledger.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops.config import RosterConfig
from rosterops.engine.state import BaselineState

__all__ = ["VACANCY_COLUMNS", "compute_vacancies"]

VACANCY_COLUMNS = (
    "territory_id",
    "vacancy_kind",
    "vacancy_start",
    "vacancy_end",
    "as_of",
    "detail",
)


def compute_vacancies(
    state: BaselineState,
    territories: pl.DataFrame | None,
    config: RosterConfig,
    *,
    as_of: date,
    event_kinds: dict[str, str] | None = None,
) -> pl.DataFrame:
    """Compute the vacancy set as of ``as_of``.

    ``event_kinds`` optionally maps a territory id to a vacancy kind derived from
    the event ledger (e.g. ``after_transfer``/``after_termination``); absent that
    information the kind is ``permanently_unassigned``.
    """
    if territories is None or territories.height == 0:
        return pl.DataFrame(schema={c: pl.String for c in VACANCY_COLUMNS})

    event_kinds = event_kinds or {}

    # Precompute occupancy once: the set of territories with an active primary
    # at as_of, and the latest prior primary end per territory. Both are built
    # in O(total assignments) rather than rescanning every employee per
    # territory.
    occupied: set[str] = set()
    latest_end: dict[str, date] = {}
    for employee_id in state.employee_ids():
        for assignment in state.active_assignments(employee_id, as_of):
            if assignment.is_primary and assignment.territory_id:
                occupied.add(assignment.territory_id)
        for assignment in state.assignments.get(employee_id, []):
            territory_id = assignment.territory_id
            if not assignment.is_primary or not territory_id or assignment.end is None:
                continue
            prior = latest_end.get(territory_id)
            if prior is None or assignment.end > prior:
                latest_end[territory_id] = assignment.end

    rows: list[dict[str, object]] = []
    for row in territories.iter_rows(named=True):
        territory_id = _s(row.get("territory_id"))
        if territory_id is None:
            continue
        requires = _b(row.get("requires_primary_owner"))
        status = (_s(row.get("territory_status")) or "").lower()
        inactive = status not in {"", "active"}

        is_occupied = territory_id in occupied

        if inactive or not requires:
            if not is_occupied:
                rows.append(
                    _entry(
                        territory_id,
                        "unassigned_by_design",
                        as_of,
                        "territory does not require a primary owner or is inactive",
                    )
                )
            continue
        if is_occupied:
            continue
        kind = event_kinds.get(territory_id, "permanently_unassigned")
        rows.append(
            _entry(
                territory_id,
                kind,
                as_of,
                "no active primary owner",
                start=latest_end.get(territory_id),
            )
        )

    if not rows:
        return pl.DataFrame(schema={c: pl.String for c in VACANCY_COLUMNS})
    frame = pl.DataFrame(rows)
    return frame.select(list(VACANCY_COLUMNS)).sort("territory_id")


def _entry(
    territory_id: str,
    kind: str,
    as_of: date,
    detail: str,
    *,
    start: date | None = None,
) -> dict[str, object]:
    return {
        "territory_id": territory_id,
        "vacancy_kind": kind,
        "vacancy_start": start if start is not None else as_of,
        "vacancy_end": None,
        "as_of": as_of,
        "detail": detail,
    }


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
