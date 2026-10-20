"""Phase 8 invalid-variant integration matrix (IMPLEMENTATION_PHASES §2, Phase 8).

Each test drives the public engine with one deliberately invalid variant and
asserts the expected rule id(s) are raised (or, for informational rows, that no
false error is raised). See the matrix table in ``IMPLEMENTATION_PHASES.md``.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops import RosterConfig, RosterEngine


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _process(**kwargs: object):
    return RosterEngine(RosterConfig()).process(
        baseline_date="2026-09-30",
        as_of="2026-10-31",
        **kwargs,
    )


def _snapshot(snapshot: pl.DataFrame, **kwargs: object):
    return RosterEngine(RosterConfig()).validate_snapshot(snapshot, as_of="2026-10-31", **kwargs)


def _ids(result: object) -> set[str]:
    return {f.rule_id for f in result.findings}  # type: ignore[attr-defined]


_REP = {
    "employee_id": "E1",
    "territory_id": "T1",
    "role_code": "REP",
    "is_primary": True,
    "employment_start_date": date(2020, 1, 1),
}


# 1 -- Unknown employee in transfer -> ID-006 / TRF-001
def test_unknown_employee_in_transfer() -> None:
    baseline = _frame([_REP])
    transfers = _frame(
        [
            {
                "event_id": "TR1",
                "employee_id": "GHOST",
                "effective_date": date(2026, 10, 1),
                "from_territory_id": "T1",
                "to_territory_id": "T2",
            }
        ]
    )
    ids = _ids(_process(baseline=baseline, transfers=transfers))
    assert {"ID-006", "TRF-001"} <= ids


# 2 -- Nonexistent destination territory -> TRF-004
def test_transfer_to_missing_territory() -> None:
    baseline = _frame([_REP])
    transfers = _frame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 1),
                "from_territory_id": "T1",
                "to_territory_id": "T_NOPE",
            }
        ]
    )
    territories = _frame([{"territory_id": "T1", "requires_primary_owner": True}])
    ids = _ids(_process(baseline=baseline, transfers=transfers, territories=territories))
    assert "TRF-004" in ids


# 3 -- Transfer source != baseline assignment -> TRF-002
def test_transfer_source_mismatch() -> None:
    baseline = _frame([_REP])
    transfers = _frame(
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
    assert "TRF-002" in _ids(_process(baseline=baseline, transfers=transfers))


# 4 -- Two conflicting same-date transfers -> DAT-007 / TRF-006
def test_conflicting_same_date_transfers() -> None:
    baseline = _frame([_REP])
    transfers = _frame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 1),
                "from_territory_id": "T1",
                "to_territory_id": "T2",
            },
            {
                "event_id": "TR2",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 1),
                "from_territory_id": "T1",
                "to_territory_id": "T3",
            },
        ]
    )
    ids = _ids(_process(baseline=baseline, transfers=transfers))
    assert {"DAT-007", "TRF-006"} <= ids


# 5 -- Promotion after termination -> EMP-005 / PRO-004
def test_promotion_after_termination() -> None:
    baseline = _frame([_REP])
    terms = _frame([{"event_id": "TM1", "employee_id": "E1", "effective_date": date(2026, 10, 5)}])
    promotions = _frame(
        [
            {
                "event_id": "PR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 20),
                "old_role_code": "REP",
                "new_role_code": "SENIOR_REP",
            }
        ]
    )
    ids = _ids(_process(baseline=baseline, terminations=terms, promotions=promotions))
    assert "EMP-005" in ids or "PRO-004" in ids


# 6 -- Duplicate termination across files -> EMP-004 / ID-007
def test_duplicate_termination() -> None:
    baseline = _frame([_REP])
    terms = _frame(
        [
            {"event_id": "TM1", "employee_id": "E1", "effective_date": date(2026, 10, 5)},
            {"event_id": "TM2", "employee_id": "E1", "effective_date": date(2026, 10, 5)},
        ]
    )
    ids = _ids(_process(baseline=baseline, terminations=terms))
    assert {"EMP-004", "ID-007"} & ids


# 7 -- Leave starts before employment start -> LOA-002 / LOA-001
def test_leave_before_employment_start() -> None:
    baseline = _frame([{**_REP, "employment_start_date": date(2026, 10, 15)}])
    leaves = _frame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 1),
            }
        ]
    )
    ids = _ids(_process(baseline=baseline, leaves=leaves))
    assert {"LOA-002", "LOA-001"} & ids


# 8 -- Leave extends beyond termination -> LOA-006
def test_leave_after_termination() -> None:
    baseline = _frame([_REP])
    terms = _frame([{"event_id": "TM1", "employee_id": "E1", "effective_date": date(2026, 10, 10)}])
    leaves = _frame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 20),
            }
        ]
    )
    assert "LOA-006" in _ids(_process(baseline=baseline, terminations=terms, leaves=leaves))


# 9 -- Return earlier than leave start -> LOA-004
def test_return_before_leave_start() -> None:
    baseline = _frame([_REP])
    leaves = _frame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 10),
                "leave_end_date": date(2026, 10, 20),
            }
        ]
    )
    returns = _frame(
        [{"event_id": "RT1", "employee_id": "E1", "effective_date": date(2026, 10, 5)}]
    )
    assert "LOA-004" in _ids(_process(baseline=baseline, leaves=leaves, returns=returns))


# 10 -- Open leave at as-of -> LOA-010 (INFO, no false error)
def test_open_leave_is_informational_only() -> None:
    baseline = _frame([_REP])
    leaves = _frame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 5),
            }
        ]
    )
    result = _process(baseline=baseline, leaves=leaves)
    ids = _ids(result)
    assert "LOA-010" in ids
    loa010 = [f for f in result.findings if f.rule_id == "LOA-010"]  # type: ignore[attr-defined]
    assert all(f.severity != "error" for f in loa010)


# 11 -- Coverage overlaps beyond capacity -> COV-004
def test_coverage_beyond_capacity() -> None:
    baseline = _frame(
        [
            _REP,
            {**_REP, "employee_id": "E2", "territory_id": "T2"},
            {**_REP, "employee_id": "E3", "territory_id": "T3"},
        ]
    )
    coverage = _frame(
        [
            {
                "coverage_id": "CV1",
                "covering_employee_id": "E2",
                "covered_territory_id": "T1",
                "covered_employee_id": "E1",
                "coverage_start_date": date(2026, 10, 5),
                "coverage_end_date": date(2026, 10, 20),
            },
            {
                "coverage_id": "CV2",
                "covering_employee_id": "E2",
                "covered_territory_id": "T3",
                "covered_employee_id": "E3",
                "coverage_start_date": date(2026, 10, 6),
                "coverage_end_date": date(2026, 10, 20),
            },
        ]
    )
    assert "COV-004" in _ids(_process(baseline=baseline, coverage=coverage))


# 12 -- Two primaries where max = 1 -> TER-002 / DAT-003
def test_two_primaries_beyond_limit() -> None:
    baseline = _frame(
        [
            _REP,
            {**_REP, "territory_id": "T2"},
        ]
    )
    ids = _ids(_process(baseline=baseline))
    assert "TER-002" in ids


def test_two_primaries_snapshot_dat003() -> None:
    snapshot = _frame(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "is_primary": True,
                "effective_from": date(2026, 1, 1),
                "employment_start_date": date(2020, 1, 1),
            },
            {
                "employee_id": "E1",
                "territory_id": "T2",
                "is_primary": True,
                "effective_from": date(2026, 1, 1),
                "employment_start_date": date(2020, 1, 1),
            },
        ]
    )
    assert "DAT-003" in _ids(_snapshot(snapshot))


# 13 -- Inactive territory counted as vacancy -> TER-006 (must NOT count)
def test_inactive_territory_not_a_vacancy() -> None:
    baseline = _frame([_REP])
    territories = _frame(
        [
            {"territory_id": "T1", "requires_primary_owner": True},
            {"territory_id": "T9", "requires_primary_owner": True, "territory_status": "inactive"},
        ]
    )
    result = _process(baseline=baseline, territories=territories)
    ids = _ids(result)
    assert "TER-006" in ids
    vacancies = result.vacancies  # type: ignore[attr-defined]
    t9 = vacancies.filter(pl.col("territory_id") == "T9")
    if t9.height:
        assert t9["vacancy_kind"].to_list() == ["unassigned_by_design"]


# 14 -- Manager self-reference -> ORG-002
def test_manager_self_reference() -> None:
    baseline = _frame([{**_REP, "manager_id": "E1"}])
    assert "ORG-002" in _ids(_process(baseline=baseline))


# 15 -- 2-node hierarchy cycle -> ORG-003
def test_hierarchy_cycle() -> None:
    baseline = _frame(
        [
            {**_REP, "manager_id": "E2"},
            {**_REP, "employee_id": "E2", "territory_id": "T2", "manager_id": "E1"},
        ]
    )
    assert "ORG-003" in _ids(_process(baseline=baseline))


# 16 -- Event effective <= baseline date -> DAT-006
def test_event_on_baseline_date_is_out_of_window() -> None:
    baseline = _frame([_REP])
    terms = _frame([{"event_id": "TM1", "employee_id": "E1", "effective_date": date(2026, 9, 30)}])
    assert "DAT-006" in _ids(_process(baseline=baseline, terminations=terms))


# 17 -- Same event in two input files -> ID-007
def test_same_event_in_two_files() -> None:
    baseline = _frame([_REP])
    transfers = _frame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 1),
                "from_territory_id": "T1",
                "to_territory_id": "T2",
            },
            {
                "event_id": "TR2",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 1),
                "from_territory_id": "T1",
                "to_territory_id": "T2",
            },
        ]
    )
    assert "ID-007" in _ids(_process(baseline=baseline, transfers=transfers))


# 18 -- Snapshot mode asked for movement counts -> REC-007 not_available
def test_snapshot_movement_metrics_not_available() -> None:
    snapshot = _frame(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "is_primary": True,
                "effective_from": date(2026, 1, 1),
                "employment_start_date": date(2020, 1, 1),
            }
        ]
    )
    result = _snapshot(snapshot)
    ids = _ids(result)
    assert "REC-007" in ids
    rec007 = [f for f in result.findings if f.rule_id == "REC-007"]  # type: ignore[attr-defined]
    assert any("not_available" in f.message for f in rec007)


# 19 -- Assignment interval end < start -> DAT-002
def test_interval_end_before_start() -> None:
    snapshot = _frame(
        [
            {
                "employee_id": "E1",
                "territory_id": "T1",
                "is_primary": True,
                "effective_from": date(2026, 6, 1),
                "effective_to": date(2026, 1, 1),
                "employment_start_date": date(2020, 1, 1),
            }
        ]
    )
    assert "DAT-002" in _ids(_snapshot(snapshot))


# 20 -- Overlapping incompatible leave -> LOA-003
def test_overlapping_incompatible_leave() -> None:
    baseline = _frame([_REP])
    leaves = _frame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 1),
                "leave_end_date": date(2026, 10, 20),
            },
            {
                "event_id": "LV2",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 10),
                "leave_end_date": date(2026, 10, 25),
            },
        ]
    )
    assert "LOA-003" in _ids(_process(baseline=baseline, leaves=leaves))
