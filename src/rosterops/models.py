"""Canonical domain schemas, enumerations, and grain definitions.

These schemas are the contract between ingestion, reconstruction, rules, and
reports. Column names here are canonical; source files map onto them through
``inputs.<role>.columns`` configuration. Identifiers are strings end-to-end
(significant leading zeros must survive); business dates are ``pl.Date``.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import TypeAlias

import polars as pl

#: Polars dtype declaration: an instance (``pl.List(pl.String)``) or class (``pl.String``).
DtypeLike: TypeAlias = pl.DataType | type[pl.DataType]

__all__ = [
    "ASSIGNMENT_FIELDS",
    "BASELINE_FIELDS",
    "COVERAGE_FIELDS",
    "EMPLOYEE_FIELDS",
    "EVENT_FIELDS",
    "GRAIN_KEYS",
    "KNOWN_CONFLICT_POLICIES",
    "KNOWN_INPUT_ROLES",
    "LINEAGE_FIELDS",
    "MANAGER_FIELDS",
    "ORG_FIELDS",
    "REQUIRED_EVENT_FIELDS",
    "ROLE_FIELDS",
    "ROLE_MASTER_FIELDS",
    "TERRITORY_FIELDS",
    "EventType",
    "Grain",
    "InputMode",
    "Severity",
    "TerminationDateSemantics",
    "grain_keys",
]


class EventType(str, Enum):
    """Canonical event types normalized from all supported input roles."""

    TRANSFER = "transfer"
    PROMOTION = "promotion"
    TERMINATION = "termination"
    LEAVE_START = "leave_start"
    LEAVE_RETURN = "leave_return"
    HIRE = "hire"
    REHIRE = "rehire"
    TEMP_COVERAGE = "temp_coverage"


class Grain(str, Enum):
    """Declared row grain of baseline/snapshot inputs (decision D1)."""

    EMPLOYEE = "employee"
    EMPLOYEE_TERRITORY = "employee_territory"
    EMPLOYEE_TERRITORY_ASSIGNMENT = "employee_territory_assignment"
    CUSTOM = "custom"


class Severity(str, Enum):
    """Finding severity. Wire format is lowercase; tables may render uppercase."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def label(self) -> str:
        """Uppercase display label used in reports and consoles."""
        return self.value.upper()


class InputMode(str, Enum):
    """Execution mode a rule applies to."""

    SNAPSHOT = "snapshot"
    PROCESS = "process"


class TerminationDateSemantics(str, Enum):
    """How a source termination date maps onto the canonical interval."""

    LAST_WORKING_DAY_INCLUSIVE = "last_working_day_inclusive"
    FIRST_INACTIVE_DAY = "first_inactive_day"
    EXPLICIT_EFFECTIVE_END = "explicit_effective_end"


#: Named policies permitted for same-date conflict resolution.
KNOWN_CONFLICT_POLICIES: tuple[str, ...] = ("effective_then_source",)

#: Input roles accepted under ``inputs:`` in configuration.
KNOWN_INPUT_ROLES: tuple[str, ...] = (
    "baseline",
    "snapshot",
    "transfers",
    "promotions",
    "terminations",
    "leaves",
    "returns",
    "hires",
    "rehires",
    "coverage",
    "territories",
    "managers",
    "organizations",
    "roles",
)

#: Injected lineage columns carried by every loaded and derived row.
LINEAGE_FIELDS: dict[str, DtypeLike] = {
    "source_file": pl.String,
    "source_sheet": pl.String,
    "source_row": pl.Int64,
}

EMPLOYEE_FIELDS: dict[str, DtypeLike] = {
    "employee_id": pl.String,
    "employee_status": pl.String,
    "first_name": pl.String,
    "last_name": pl.String,
    "role_code": pl.String,
    "grade_code": pl.String,
    "manager_id": pl.String,
    "business_unit": pl.String,
    "country": pl.String,
    "region_id": pl.String,
    "district_id": pl.String,
    "employment_start_date": pl.Date,
    "employment_end_date": pl.Date,
}

TERRITORY_FIELDS: dict[str, DtypeLike] = {
    "territory_id": pl.String,
    "territory_name": pl.String,
    "region_id": pl.String,
    "district_id": pl.String,
    "country": pl.String,
    "territory_status": pl.String,
    "requires_primary_owner": pl.Boolean,
    "max_assignees": pl.Int64,
    "allowed_roles": pl.List(pl.String),
    "coverage_required_during_leave": pl.Boolean,
}

ASSIGNMENT_FIELDS: dict[str, DtypeLike] = {
    "employee_id": pl.String,
    "territory_id": pl.String,
    "assignment_type": pl.String,
    "is_primary": pl.Boolean,
    "effective_from": pl.Date,
    "effective_to": pl.Date,
    "assignment_status": pl.String,
    "source_event_id": pl.String,
}

#: Mappable canonical fields for event inputs (lineage is injected separately).
EVENT_FIELDS: dict[str, DtypeLike] = {
    "event_id": pl.String,
    "event_type": pl.String,
    "employee_id": pl.String,
    "effective_date": pl.Date,
    "recorded_date": pl.Date,
    "old_value": pl.String,
    "new_value": pl.String,
    "from_territory_id": pl.String,
    "to_territory_id": pl.String,
    "old_role_code": pl.String,
    "new_role_code": pl.String,
    "leave_start_date": pl.Date,
    "leave_end_date": pl.Date,
    "source_system": pl.String,
}

COVERAGE_FIELDS: dict[str, DtypeLike] = {
    "coverage_id": pl.String,
    "covering_employee_id": pl.String,
    "covered_territory_id": pl.String,
    "covered_employee_id": pl.String,
    "coverage_start_date": pl.Date,
    "coverage_end_date": pl.Date,
    "coverage_type": pl.String,
    "is_primary_coverage": pl.Boolean,
    "source_event_id": pl.String,
}

MANAGER_FIELDS: frozenset[str] = frozenset(
    {"employee_id", "manager_id", "employee_status", "employment_start_date", "employment_end_date"}
)

ORG_FIELDS: dict[str, DtypeLike] = {
    "organization_id": pl.String,
    "organization_name": pl.String,
    "organization_type": pl.String,
    "parent_organization_id": pl.String,
    "region_id": pl.String,
    "district_id": pl.String,
    "country": pl.String,
}

ROLE_MASTER_FIELDS: dict[str, DtypeLike] = {
    "role_code": pl.String,
    "role_name": pl.String,
    "role_class": pl.String,
    "allowed_successor_role_codes": pl.List(pl.String),
}

#: Canonical fields a baseline/snapshot input may map (employee + assignment).
BASELINE_FIELDS: frozenset[str] = frozenset(EMPLOYEE_FIELDS) | frozenset(ASSIGNMENT_FIELDS)

#: Which canonical fields each input role is allowed to map.
ROLE_FIELDS: dict[str, frozenset[str]] = {
    "baseline": BASELINE_FIELDS,
    "snapshot": BASELINE_FIELDS,
    "transfers": frozenset(EVENT_FIELDS),
    "promotions": frozenset(EVENT_FIELDS),
    "terminations": frozenset(EVENT_FIELDS),
    "leaves": frozenset(EVENT_FIELDS),
    "returns": frozenset(EVENT_FIELDS),
    "hires": frozenset(EVENT_FIELDS),
    "rehires": frozenset(EVENT_FIELDS),
    "coverage": frozenset(COVERAGE_FIELDS) | {"event_id", "source_system"},
    "territories": frozenset(TERRITORY_FIELDS),
    "managers": MANAGER_FIELDS,
    "organizations": frozenset(ORG_FIELDS),
    "roles": frozenset(ROLE_MASTER_FIELDS),
}

#: Minimum canonical fields each event role must resolve once mapped (SCH-001).
REQUIRED_EVENT_FIELDS: dict[str, frozenset[str]] = {
    "transfers": frozenset({"event_id", "employee_id", "effective_date"}),
    "promotions": frozenset({"event_id", "employee_id", "effective_date"}),
    "terminations": frozenset({"event_id", "employee_id", "effective_date"}),
    "leaves": frozenset({"event_id", "employee_id", "leave_start_date"}),
    "returns": frozenset({"event_id", "employee_id", "effective_date"}),
    "hires": frozenset({"event_id", "employee_id", "effective_date"}),
    "rehires": frozenset({"event_id", "employee_id", "effective_date"}),
    "coverage": frozenset(
        {"coverage_id", "covering_employee_id", "covered_territory_id", "coverage_start_date"}
    ),
}

#: Grain enum value -> grain key columns (decision D1).
GRAIN_KEYS: dict[Grain, tuple[str, ...]] = {
    Grain.EMPLOYEE: ("employee_id",),
    Grain.EMPLOYEE_TERRITORY: ("employee_id", "territory_id"),
    Grain.EMPLOYEE_TERRITORY_ASSIGNMENT: (
        "employee_id",
        "territory_id",
        "assignment_type",
        "effective_from",
    ),
    Grain.CUSTOM: (),
}


def grain_keys(grain: Grain, custom_keys: Sequence[str] | None = None) -> tuple[str, ...]:
    """Resolve the effective grain key columns for a declared grain."""
    if grain is Grain.CUSTOM:
        return tuple(custom_keys or ())
    return GRAIN_KEYS[grain]
