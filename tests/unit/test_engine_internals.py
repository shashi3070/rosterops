"""Unit tests for engine internals: baseline/grain, vacancies, reconstruction."""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops import RosterConfig, RosterEngine
from rosterops.engine.baseline import build_baseline_state, validate_grain
from rosterops.engine.vacancies import VACANCY_COLUMNS, compute_vacancies


def _baseline(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


# --------------------------------------------------------------------------- #
# grain enforcement (GRN-001..003)
# --------------------------------------------------------------------------- #
def test_duplicate_grain_key_flagged() -> None:
    frame = _baseline(
        [
            {"employee_id": "E1", "territory_id": "T1", "is_primary": True},
            {"employee_id": "E1", "territory_id": "T1", "is_primary": True},
        ]
    )
    findings = validate_grain(frame, RosterConfig())
    assert any(f.rule_id == "GRN-001" for f in findings)


def test_unique_grain_key_clean() -> None:
    frame = _baseline(
        [
            {"employee_id": "E1", "territory_id": "T1", "is_primary": True},
            {"employee_id": "E1", "territory_id": "T2", "is_primary": False},
        ]
    )
    assert not [f for f in validate_grain(frame, RosterConfig()) if f.rule_id.startswith("GRN")]


# --------------------------------------------------------------------------- #
# baseline state
# --------------------------------------------------------------------------- #
def test_baseline_state_indexes_employment_and_roles() -> None:
    frame = _baseline(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "role_code": "REP",
                "is_primary": True,
                "employment_start_date": date(2020, 1, 1),
            }
        ]
    )
    state = build_baseline_state(frame)
    assert state.employment.get("E1")
    assert state.role_on("E1", date(2026, 1, 1)) == "REP"
    assert state.primary_territory("E1", date(2026, 1, 1)) == "T1"


def test_terminated_baseline_employee_not_active() -> None:
    frame = _baseline(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "employment_start_date": date(2020, 1, 1),
                "employment_end_date": date(2025, 1, 1),
            }
        ]
    )
    state = build_baseline_state(frame)
    assert "E1" not in state.active_employee_ids(date(2026, 1, 1))


# --------------------------------------------------------------------------- #
# vacancies
# --------------------------------------------------------------------------- #
def test_vacancy_columns_stable() -> None:
    assert VACANCY_COLUMNS == (
        "territory_id",
        "vacancy_kind",
        "vacancy_start",
        "vacancy_end",
        "as_of",
        "detail",
    )


def test_vacancy_for_unowned_required_territory() -> None:
    frame = _baseline(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "is_primary": True,
                "employment_start_date": date(2020, 1, 1),
            }
        ]
    )
    territories = pl.DataFrame(
        [
            {"territory_id": "T1", "requires_primary_owner": True},
            {"territory_id": "T2", "requires_primary_owner": True},
        ]
    )
    state = build_baseline_state(frame)
    vacancies = compute_vacancies(state, territories, RosterConfig(), as_of=date(2026, 10, 31))
    assert "T2" in vacancies["territory_id"].to_list()
    assert "T1" not in vacancies["territory_id"].to_list()


# --------------------------------------------------------------------------- #
# reconstruction findings
# --------------------------------------------------------------------------- #
def test_transfer_from_wrong_territory_flags_trf002() -> None:
    baseline = _baseline(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "role_code": "REP",
                "is_primary": True,
                "employment_start_date": date(2020, 1, 1),
            }
        ]
    )
    transfers = pl.DataFrame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 1),
                "from_territory_id": "T_WRONG",
                "to_territory_id": "T2",
            }
        ]
    )
    result = RosterEngine(RosterConfig()).process(
        baseline=baseline,
        baseline_date="2026-09-30",
        as_of="2026-10-31",
        transfers=transfers,
    )
    assert any(f.rule_id == "TRF-002" for f in result.findings)


def test_transfer_to_occupied_territory_flags_ter003() -> None:
    baseline = _baseline(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "is_primary": True,
                "employment_start_date": date(2020, 1, 1),
            },
            {
                "employee_id": "E2",
                "territory_id": "T2",
                "is_primary": True,
                "employment_start_date": date(2020, 1, 1),
            },
        ]
    )
    transfers = pl.DataFrame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 1),
                "from_territory_id": "T1",
                "to_territory_id": "T2",
            }
        ]
    )
    result = RosterEngine(RosterConfig()).process(
        baseline=baseline,
        baseline_date="2026-09-30",
        as_of="2026-10-31",
        transfers=transfers,
    )
    assert any(f.rule_id == "TER-003" for f in result.findings)


def test_termination_after_as_of_keeps_employee_active() -> None:
    baseline = _baseline(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "is_primary": True,
                "employment_start_date": date(2020, 1, 1),
            }
        ]
    )
    terms = pl.DataFrame(
        [
            {
                "event_id": "TM1",
                "employee_id": "E1",
                "effective_date": date(2026, 12, 1),
            }
        ]
    )
    result = RosterEngine(RosterConfig()).process(
        baseline=baseline,
        baseline_date="2026-09-30",
        as_of="2026-10-31",
        terminations=terms,
    )
    assert result.summary["metrics"]["ending_active"]["value"] == 1
