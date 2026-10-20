"""Unit tests for post-reconstruction lifecycle rules (Groups C/E/F/G/I/K).

These exercise ``rosterops.engine.lifecycle_rules`` through the public engine so
the wiring in the orchestrator is covered too.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops import RosterConfig, RosterEngine


def _baseline(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _process(**kwargs: object):
    return RosterEngine(RosterConfig()).process(
        baseline_date="2026-09-30",
        as_of="2026-10-31",
        **kwargs,
    )


def _rules(result: object) -> set[str]:
    return {f.rule_id for f in result.findings}  # type: ignore[attr-defined]


_REP = {
    "employee_id": "E1",
    "territory_id": "T1",
    "role_code": "REP",
    "is_primary": True,
    "employment_start_date": date(2020, 1, 1),
}


# --------------------------------------------------------------------------- #
# transfer (Group E)
# --------------------------------------------------------------------------- #
def test_trf008_informational_on_transfer() -> None:
    baseline = _baseline([_REP, {**_REP, "employee_id": "E2", "territory_id": "T2"}])
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
    result = _process(baseline=baseline, transfers=transfers)
    assert "TRF-008" in _rules(result)


def test_trf005_transfer_before_employment_start() -> None:
    baseline = _baseline([{**_REP, "employment_start_date": date(2026, 10, 15)}])
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
    result = _process(baseline=baseline, transfers=transfers)
    assert "TRF-005" in _rules(result)


# --------------------------------------------------------------------------- #
# promotion (Group F)
# --------------------------------------------------------------------------- #
def test_pro005_promotion_same_role() -> None:
    baseline = _baseline([_REP])
    promotions = pl.DataFrame(
        [
            {
                "event_id": "PR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 15),
                "old_role_code": "REP",
                "new_role_code": "REP",
            }
        ]
    )
    result = _process(baseline=baseline, promotions=promotions)
    assert "PRO-005" in _rules(result)


def test_pro003_duplicate_promotion() -> None:
    baseline = _baseline([_REP])
    promotions = pl.DataFrame(
        [
            {
                "event_id": "PR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 15),
                "old_role_code": "REP",
                "new_role_code": "SENIOR_REP",
            },
            {
                "event_id": "PR2",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 15),
                "old_role_code": "REP",
                "new_role_code": "SENIOR_REP",
            },
        ]
    )
    result = _process(baseline=baseline, promotions=promotions)
    assert "PRO-003" in _rules(result)


def test_pro002_role_transition_not_permitted() -> None:
    baseline = _baseline([_REP])
    roles = pl.DataFrame(
        [
            {
                "role_code": "REP",
                "allowed_successor_role_codes": ["SENIOR_REP"],
            }
        ]
    )
    promotions = pl.DataFrame(
        [
            {
                "event_id": "PR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 15),
                "old_role_code": "REP",
                "new_role_code": "DIRECTOR",
            }
        ]
    )
    result = _process(baseline=baseline, roles=roles, promotions=promotions)
    assert "PRO-002" in _rules(result)


# --------------------------------------------------------------------------- #
# leave (Group G)
# --------------------------------------------------------------------------- #
def test_loa009_metrics_emitted() -> None:
    baseline = _baseline([_REP])
    leaves = pl.DataFrame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 5),
                "leave_end_date": date(2026, 10, 12),
            }
        ]
    )
    returns = pl.DataFrame(
        [{"event_id": "RT1", "employee_id": "E1", "effective_date": date(2026, 10, 13)}]
    )
    result = _process(baseline=baseline, leaves=leaves, returns=returns)
    assert "LOA-009" in _rules(result)


def test_loa010_open_leave_flagged_informational() -> None:
    baseline = _baseline([_REP])
    leaves = pl.DataFrame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 5),
            }
        ]
    )
    result = _process(baseline=baseline, leaves=leaves)
    assert "LOA-010" in _rules(result)


def test_loa006_leave_after_termination() -> None:
    baseline = _baseline([_REP])
    terms = pl.DataFrame(
        [{"event_id": "TM1", "employee_id": "E1", "effective_date": date(2026, 10, 10)}]
    )
    leaves = pl.DataFrame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 20),
            }
        ]
    )
    result = _process(baseline=baseline, terminations=terms, leaves=leaves)
    assert "LOA-006" in _rules(result)


# --------------------------------------------------------------------------- #
# coverage (Group I)
# --------------------------------------------------------------------------- #
def test_cov003_coverage_without_leave() -> None:
    baseline = _baseline([_REP, {**_REP, "employee_id": "E2", "territory_id": "T2"}])
    coverage = pl.DataFrame(
        [
            {
                "coverage_id": "CV1",
                "covering_employee_id": "E2",
                "covered_territory_id": "T1",
                "covered_employee_id": "E1",
                "coverage_start_date": date(2026, 10, 5),
                "coverage_end_date": date(2026, 10, 12),
            }
        ]
    )
    result = _process(baseline=baseline, coverage=coverage)
    assert "COV-003" in _rules(result)


# --------------------------------------------------------------------------- #
# territory vacancy interval (Group D, TER-007)
# --------------------------------------------------------------------------- #
def test_ter007_vacancy_interval_for_terminated_owner() -> None:
    baseline = _baseline([_REP])
    territories = pl.DataFrame([{"territory_id": "T1", "requires_primary_owner": True}])
    terms = pl.DataFrame(
        [{"event_id": "TM1", "employee_id": "E1", "effective_date": date(2026, 10, 20)}]
    )
    result = _process(baseline=baseline, territories=territories, terminations=terms)
    assert "TER-007" in _rules(result)


# --------------------------------------------------------------------------- #
# dat-005 events after termination
# --------------------------------------------------------------------------- #
def test_dat005_transfer_after_termination() -> None:
    baseline = _baseline([_REP])
    terms = pl.DataFrame(
        [{"event_id": "TM1", "employee_id": "E1", "effective_date": date(2026, 10, 10)}]
    )
    transfers = pl.DataFrame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E1",
                "effective_date": date(2026, 10, 20),
                "from_territory_id": "T1",
                "to_territory_id": "T2",
            }
        ]
    )
    result = _process(baseline=baseline, terminations=terms, transfers=transfers)
    assert "DAT-005" in _rules(result)


# --------------------------------------------------------------------------- #
# cov-005 / loa-008 guards (satisfied by construction -> must not fire)
# --------------------------------------------------------------------------- #
def test_cov005_loa008_not_spurious_for_well_formed_coverage() -> None:
    baseline = _baseline([_REP, {**_REP, "employee_id": "E2", "territory_id": "T2"}])
    leaves = pl.DataFrame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E1",
                "leave_start_date": date(2026, 10, 5),
                "leave_end_date": date(2026, 10, 12),
            }
        ]
    )
    coverage = pl.DataFrame(
        [
            {
                "coverage_id": "CV1",
                "covering_employee_id": "E2",
                "covered_territory_id": "T1",
                "covered_employee_id": "E1",
                "coverage_start_date": date(2026, 10, 5),
                "coverage_end_date": date(2026, 10, 12),
            }
        ]
    )
    result = _process(baseline=baseline, leaves=leaves, coverage=coverage)
    assert "COV-005" not in _rules(result)
    assert "LOA-008" not in _rules(result)
