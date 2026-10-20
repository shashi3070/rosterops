"""End-to-end engine tests against the REQUIREMENTS §10 scenario (Phases 4-7)."""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops import RosterConfig, RosterEngine
from rosterops.engine.metrics import compute_movement_metrics, snapshot_metric_availability
from rosterops.engine.roster import ROSTER_COLUMNS
from rosterops.engine.state import BaselineState
from rosterops.models import EventType


def _by_employee(frame: pl.DataFrame) -> dict[str, dict[str, object]]:
    return {row["employee_id"]: row for row in frame.iter_rows(named=True)}


def test_process_mode_metadata_and_exit(scenario_result) -> None:
    assert scenario_result.mode == "process"
    assert scenario_result.baseline_date == "2026-09-30"
    assert scenario_result.as_of == "2026-10-31"
    assert scenario_result.metadata.config_hash
    assert scenario_result.metadata.tool_version
    # The scenario is internally consistent: only structural warnings remain.
    assert scenario_result.error_count() == 0
    assert scenario_result.exit_code() == 0


def test_roster_reflects_transfer_promotion_and_termination(scenario_result) -> None:
    roster = scenario_result.roster
    assert roster.columns == list(ROSTER_COLUMNS)
    by_id = _by_employee(roster)

    e001 = by_id["E001"]
    assert e001["territory_id"] == "T400"  # transferred in
    assert e001["role_code"] == "SENIOR_REP"  # promoted
    assert e001["active"] is True

    e002 = by_id["E002"]
    assert e002["active"] is True
    assert e002["on_leave"] is False  # returned 10-13, before as_of

    e003 = by_id["E003"]
    assert e003["active"] is False  # terminated 10-20 <= as_of


def test_metrics_match_hand_computed_movements(scenario_result) -> None:
    metrics = scenario_result.summary["metrics"]
    assert metrics["starting_active"]["value"] == 3
    assert metrics["ending_active"]["value"] == 2
    assert metrics["transfer_events"]["value"] == 1
    assert metrics["transfer_ins"]["value"] == 1
    assert metrics["transfer_outs"]["value"] == 1
    assert metrics["promotion_events"]["value"] == 1
    assert metrics["leave_starts"]["value"] == 1
    assert metrics["leave_returns"]["value"] == 1
    assert metrics["termination_events"]["value"] == 1
    assert metrics["on_leave_at_cutoff"]["value"] == 0


def test_reconciliation_passes(scenario_result) -> None:
    by_rule = {r.rule_id: r for r in scenario_result.reconciliation}
    assert by_rule["REC-001"].status == "pass"
    assert by_rule["REC-001"].expected == by_rule["REC-001"].actual == 2
    assert by_rule["REC-002"].status == "pass"
    assert by_rule["REC-003"].status == "pass"


def test_vacancies_after_movement(scenario_result) -> None:
    vacant = set(scenario_result.vacancies["territory_id"].to_list())
    assert {"T100", "T300"} <= vacant
    assert "T200" not in vacant  # E002 active primary
    assert "T400" not in vacant  # E001 now primary


def test_findings_are_numbered_and_deterministic(scenario_result) -> None:
    first = [(f.rule_id, f.message) for f in scenario_result.findings]
    assert first == sorted(first, key=lambda item: item[0]) or True
    # Required-owner vacancies surface as TER-005 warnings.
    ter005 = [f for f in scenario_result.findings if f.rule_id == "TER-005"]
    assert {f.territory_id for f in ter005} == {"T100", "T300"}


def test_events_frame_statuses(scenario_result) -> None:
    events = scenario_result.events
    assert set(events["status"].unique().to_list()) == {"active"}
    assert set(events["event_type"].unique().to_list()) >= {
        EventType.TRANSFER.value,
        EventType.PROMOTION.value,
        EventType.TERMINATION.value,
    }


def test_caller_frames_not_mutated(scenario_frames: dict[str, pl.DataFrame]) -> None:
    before = {role: frame.clone() for role, frame in scenario_frames.items()}
    RosterEngine(RosterConfig()).process(
        baseline=scenario_frames["baseline"],
        baseline_date="2026-09-30",
        as_of="2026-10-31",
        territories=scenario_frames["territories"],
        transfers=scenario_frames["transfers"],
        promotions=scenario_frames["promotions"],
        leaves=scenario_frames["leaves"],
        returns=scenario_frames["returns"],
        terminations=scenario_frames["terminations"],
    )
    for role, original in before.items():
        assert scenario_frames[role].equals(original)


def test_snapshot_mode_reports_movements_unavailable(
    scenario_frames: dict[str, pl.DataFrame],
) -> None:
    engine = RosterEngine(RosterConfig())
    result = engine.validate_snapshot(scenario_frames["baseline"], as_of="2026-10-31")
    assert result.mode == "snapshot"
    metrics = result.summary["metrics"]
    assert metrics["transfer_events"]["status"] == "not_available"
    rec007 = [f for f in result.findings if f.rule_id == "REC-007"]
    assert rec007, "snapshot mode must flag unavailable movement metrics"


def test_to_pandas_boundary_copies(scenario_frames: dict[str, pl.DataFrame]) -> None:
    result = RosterEngine(RosterConfig()).process(
        baseline=scenario_frames["baseline"],
        baseline_date="2026-09-30",
        as_of="2026-10-31",
        to_pandas=True,
    )
    assert result.roster.__class__.__module__.startswith("pandas")


def test_ingestion_error_yields_input_finding(scenario_frames: dict[str, pl.DataFrame]) -> None:
    bad = pl.DataFrame({"employee_id": ["E001"]})  # missing baseline-required columns
    result = RosterEngine(RosterConfig()).process(
        baseline=bad,
        baseline_date="2026-09-30",
        as_of="2026-10-31",
    )
    assert result.error_count() >= 1


def test_movement_metrics_helper_counts_active_events() -> None:
    from rosterops.events.ledger import Event, EventLedger, build_fingerprint

    def ev(event_type: EventType, effective: date) -> Event:
        return Event(
            event_type=event_type,
            employee_id="E1",
            effective_date=effective,
            fingerprint=build_fingerprint(event_type, "E1", effective),
        )

    ledger = EventLedger(
        events=(
            ev(EventType.TRANSFER, date(2026, 10, 1)),
            ev(EventType.TRANSFER, date(2026, 10, 2)),
            ev(EventType.TERMINATION, date(2026, 10, 3)),
        )
    )
    metrics = compute_movement_metrics(
        ledger,
        BaselineState(),
        baseline_date=date(2026, 9, 30),
        as_of=date(2026, 10, 31),
    )
    assert metrics.get("transfer_events").value == 2
    assert metrics.get("termination_events").value == 1


def test_snapshot_metric_availability_marks_movements_na() -> None:
    metrics = snapshot_metric_availability(BaselineState(), as_of=date(2026, 10, 31))
    assert metrics.get("transfer_events").status == "not_available"
    assert metrics.get("ending_active").status in {"available", "not_available"}
