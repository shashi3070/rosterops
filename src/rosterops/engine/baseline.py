"""Construct baseline state from canonical baseline/snapshot frames.

Also performs declared-grain cardinality checks (Group L) used by Mode B:
GRN-001 (cardinality conforms to grain), GRN-002 (grain keys mapped/populated),
GRN-003 (interval-bearing grains have required date columns).
"""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops.config import RosterConfig
from rosterops.engine.state import (
    AssignmentInterval,
    BaselineState,
    EmployeeRecord,
    EmploymentEpisode,
    RoleInterval,
)
from rosterops.models import Grain, grain_keys
from rosterops.rules.base import Finding
from rosterops.rules.grain_rules import GRN_001, GRN_002, GRN_003

__all__ = ["build_baseline_state", "validate_grain"]


def _as_date(value: object) -> date | None:
    return value if isinstance(value, date) else None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "yes", "y", "1"}
    return False


def build_baseline_state(frame: pl.DataFrame) -> BaselineState:
    """Build the baseline state from a canonical baseline/snapshot frame.

    Each row yields an employee record, an open-ended employment episode, an
    open-ended role interval, and — when a territory is present — an
    open-ended assignment interval. Employment endpoints in the baseline
    (``employment_start_date``/``employment_end_date``) are honored directly.
    """
    state = BaselineState()
    if frame.height == 0:
        return state
    columns = set(frame.columns)

    for row in frame.iter_rows(named=True):
        employee_id = _as_str(row.get("employee_id"))
        if employee_id is None:
            continue
        emp_start = (
            _as_date(row.get("employment_start_date"))
            if "employment_start_date" in columns
            else None
        )
        emp_end = (
            _as_date(row.get("employment_end_date")) if "employment_end_date" in columns else None
        )
        state.add_employee(
            EmployeeRecord(
                employee_id=employee_id,
                employee_status=_as_str(row.get("employee_status")),
                first_name=_as_str(row.get("first_name")),
                last_name=_as_str(row.get("last_name")),
                role_code=_as_str(row.get("role_code")),
                grade_code=_as_str(row.get("grade_code")),
                manager_id=_as_str(row.get("manager_id")),
                business_unit=_as_str(row.get("business_unit")),
                country=_as_str(row.get("country")),
                region_id=_as_str(row.get("region_id")),
                district_id=_as_str(row.get("district_id")),
            )
        )
        if not state.employment.get(employee_id):
            state.add_employment(
                EmploymentEpisode(employee_id=employee_id, start=emp_start, end=emp_end)
            )
        role_code = _as_str(row.get("role_code"))
        if role_code is not None and "role_code" in columns:
            state.add_role(
                RoleInterval(employee_id=employee_id, role_code=role_code, start=emp_start)
            )
        territory_id = _as_str(row.get("territory_id"))
        if territory_id is not None:
            state.add_assignment(
                AssignmentInterval(
                    employee_id=employee_id,
                    territory_id=territory_id,
                    assignment_type=_as_str(row.get("assignment_type")),
                    is_primary=_as_bool(row.get("is_primary")),
                    start=_as_date(row.get("effective_from")) or emp_start,
                    end=_as_date(row.get("effective_to")),
                    assignment_status=_as_str(row.get("assignment_status")),
                    source_event_id=_as_str(row.get("source_event_id")),
                )
            )
    return state


def validate_grain(
    frame: pl.DataFrame,
    config: RosterConfig,
) -> list[Finding]:
    """Validate a baseline/snapshot frame against the declared grain (Group L)."""
    findings: list[Finding] = []
    keys = grain_keys(config.data.grain, config.data.grain_keys)

    # GRN-002: declared grain keys must be present and populated.
    present = set(frame.columns)
    missing = [k for k in keys if k not in present]
    if missing:
        findings.append(
            Finding.from_spec(
                GRN_002,
                f"declared grain key column(s) not mapped: {', '.join(missing)}",
                expected_value=", ".join(keys),
                actual_value=", ".join(sorted(present & set(keys))),
            )
        )
        return findings

    empty_rows: list[int] = []
    for row in frame.iter_rows(named=True):
        if any(_as_str(row.get(k)) is None for k in keys):
            row_number = row.get("source_row")
            empty_rows.append(row_number if isinstance(row_number, int) else 0)
    if empty_rows:
        findings.append(
            Finding.from_spec(
                GRN_002,
                f"{len(empty_rows)} row(s) have empty grain key value(s): {', '.join(keys)}",
                actual_value=str(empty_rows[:20]),
            )
        )

    # GRN-003: interval-bearing grain needs the date columns.
    if config.data.grain in (Grain.EMPLOYEE_TERRITORY_ASSIGNMENT, Grain.CUSTOM):
        for required in ("effective_from",):
            if required not in present:
                findings.append(
                    Finding.from_spec(
                        GRN_003,
                        f"grain {config.data.grain.value!r} requires date column "
                        f"{required!r}, which is not mapped",
                        expected_value=required,
                    )
                )

    # GRN-001: cardinality conforms to the declared grain.
    if keys and frame.height > 0:
        duplicated = frame.group_by(list(keys)).len().filter(pl.col("len") > 1).sort(list(keys))
        if duplicated.height > 0:
            sample = duplicated.head(5)
            details = "; ".join(
                "{" + ", ".join(f"{k}={row.get(k)!r}" for k in keys) + f"}} x{row['len']}"
                for row in sample.iter_rows(named=True)
            )
            findings.append(
                Finding.from_spec(
                    GRN_001,
                    f"{duplicated.height} key group(s) duplicate at declared grain "
                    f"{config.data.grain.value!r} (keys: {', '.join(keys)}); e.g. {details}",
                    actual_value=f"{duplicated.height} duplicate group(s)",
                    expected_value="unique per declared grain",
                )
            )
    return findings
