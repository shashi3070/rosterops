"""Tests for output writers and the console report (REQUIREMENTS §11.2/§13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rosterops import RosterConfig, RosterEngine
from rosterops.exceptions import InputError
from rosterops.outputs import OUTPUT_FILES, console_report, write_outputs


def _result(scenario_frames, *, mode: str = "process"):
    engine = RosterEngine(RosterConfig())
    if mode == "process":
        return engine.process(
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
    return engine.validate_snapshot(scenario_frames["baseline"], as_of="2026-10-31")


def test_mode_a_writes_full_set(scenario_frames, tmp_path: Path) -> None:
    report = write_outputs(_result(scenario_frames), tmp_path / "out", excel=False)
    names = {p.name for p in report.written}
    for expected in OUTPUT_FILES:
        assert expected in names
    assert (tmp_path / "out" / "final_roster.csv").exists()
    meta = json.loads((tmp_path / "out" / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["mode"] == "process"


def test_reconciliation_json_status(scenario_frames, tmp_path: Path) -> None:
    write_outputs(_result(scenario_frames), tmp_path / "out", excel=False)
    payload = json.loads((tmp_path / "out" / "reconciliation.json").read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert {c["rule_id"] for c in payload["checks"]} >= {"REC-001", "REC-002"}


def test_mode_b_omits_unavailable_with_reason(scenario_frames, tmp_path: Path) -> None:
    report = write_outputs(_result(scenario_frames, mode="snapshot"), tmp_path / "out", excel=False)
    omitted = {name: reason for name, reason in report.omitted}
    assert "normalized_events.parquet" in omitted
    assert "movement_summary.csv" in omitted
    assert not (tmp_path / "out" / "normalized_events.parquet").exists()


def test_output_dir_requires_overwrite(scenario_frames, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "existing.txt").write_text("x", encoding="utf-8")
    with pytest.raises(InputError, match="already exists"):
        write_outputs(_result(scenario_frames), out, excel=False)


def test_overwrite_clears_directory(scenario_frames, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("x", encoding="utf-8")
    write_outputs(_result(scenario_frames), out, overwrite=True, excel=False)
    assert not (out / "stale.txt").exists()
    assert (out / "final_roster.csv").exists()


def test_refuses_output_colliding_with_input(scenario_frames, tmp_path: Path) -> None:
    inp = tmp_path / "in"
    inp.mkdir()
    source = inp / "baseline.csv"
    source.write_text("employee_id\nE1\n", encoding="utf-8")
    with pytest.raises(InputError):
        write_outputs(
            _result(scenario_frames),
            inp,
            input_paths=[str(source)],
            overwrite=True,
            excel=False,
        )


def test_console_report_is_concise(scenario_frames) -> None:
    text = console_report(_result(scenario_frames))
    assert "mode: process" in text
    assert "roster rows:" in text
    assert "reconciliation:" in text
    assert "exit code:" in text
