from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from rosterops.cli import build_parser, main


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def test_version_flag() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_help_available() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_bare_invocation_prints_help() -> None:
    code, out, _ = _run([])
    assert code == 0
    assert "usage: rosterops" in out


def test_parser_exposes_all_commands() -> None:
    parser = build_parser()
    # Smoke-parse the documented commands.
    args = parser.parse_args(["rules", "list"])
    assert args.command == "rules"
    args = parser.parse_args(["validate-inputs", "--config", "c.yaml"])
    assert args.command == "validate-inputs"
    assert args.config == "c.yaml"


def test_rules_list_shows_all_rules() -> None:
    code, out, _ = _run(["rules", "list"])
    assert code == 0
    assert "86 rules" in out
    assert "ING-001" in out
    assert "GRN-003" in out
    assert "TRF-002" in out


def test_rules_describe() -> None:
    code, out, _ = _run(["rules", "describe", "TRF-002"])
    assert code == 0
    assert "TRF-002" in out
    assert "default severity: ERROR" in out
    assert "modes:          process" in out
    assert "transfer" in out


def test_rules_describe_renders_unicode_names() -> None:
    code, out, _ = _run(["rules", "describe", "DAT-002"])
    assert code == 0
    assert "≥" in out


def test_rules_describe_with_params() -> None:
    code, out, _ = _run(["rules", "describe", "TER-005"])
    assert code == 0
    assert "grace_days: int" in out


def test_rules_describe_unknown_rule_exits_2() -> None:
    code, _, err = _run(["rules", "describe", "ZZZ-999"])
    assert code == 2
    assert "unknown rule id" in err


def test_process_runs_and_writes_outputs(tmp_path: object) -> None:
    root = tmp_path  # type: ignore[assignment]
    inp = root / "in"  # type: ignore[operator]
    inp.mkdir()
    _write_scenario_csvs(inp)
    cfg = _write_config(root)

    code, out, _ = _run(
        [
            "process",
            "--baseline",
            str(inp / "baseline.csv"),
            "--baseline-date",
            "2026-09-30",
            "--as-of",
            "2026-10-31",
            "--transfers",
            str(inp / "transfers.csv"),
            "--territories",
            str(inp / "territories.csv"),
            "--config",
            str(cfg),
            "--output-dir",
            str(root / "out"),
        ]
    )
    assert "mode: process" in out
    assert "exit code:" in out
    outdir = root / "out"  # type: ignore[operator]
    assert (outdir / "final_roster.csv").exists()
    assert (outdir / "run_metadata.json").exists()
    assert code == 1  # scenario intentionally has a primary-owner clash (TER-003)


def test_process_refuses_existing_output_dir(tmp_path: object) -> None:
    root = tmp_path  # type: ignore[assignment]
    inp = root / "in"  # type: ignore[operator]
    inp.mkdir()
    _write_scenario_csvs(inp)
    cfg = _write_config(root)
    outdir = root / "out"  # type: ignore[operator]
    outdir.mkdir()
    (outdir / "sentinel.txt").write_text("x", encoding="utf-8")

    code, _, err = _run(
        [
            "process",
            "--baseline",
            str(inp / "baseline.csv"),
            "--baseline-date",
            "2026-09-30",
            "--as-of",
            "2026-10-31",
            "--config",
            str(cfg),
            "--output-dir",
            str(outdir),
        ]
    )
    assert code == 2
    assert "already exists" in err


def test_validate_snapshot_runs(tmp_path: object) -> None:
    root = tmp_path  # type: ignore[assignment]
    inp = root / "in"  # type: ignore[operator]
    inp.mkdir()
    _write_scenario_csvs(inp)
    cfg = _write_config(root)

    code, out, _ = _run(
        [
            "validate",
            "--snapshot",
            str(inp / "baseline.csv"),
            "--as-of",
            "2026-10-31",
            "--config",
            str(cfg),
            "--output-dir",
            str(root / "out"),
        ]
    )
    assert code in (0, 1)
    assert "mode: snapshot" in out
    assert "not_applicable" in out


def _write_config(root: object):
    cfg = root / "config.yaml"  # type: ignore[operator]
    cfg.write_text("version: 1\ndata:\n  grain: employee_territory\n", encoding="utf-8")
    return cfg


def _write_scenario_csvs(inp: object) -> None:
    import polars as pl

    pl.DataFrame(
        [
            {
                "employee_id": "E001",
                "employee_status": "Active",
                "role_code": "REP",
                "territory_id": "T100",
                "is_primary": True,
                "employment_start_date": "2020-01-01",
            },
            {
                "employee_id": "E002",
                "employee_status": "Active",
                "role_code": "REP",
                "territory_id": "T200",
                "is_primary": True,
                "employment_start_date": "2020-01-01",
            },
        ]
    ).write_csv(inp / "baseline.csv")  # type: ignore[operator]
    pl.DataFrame(
        [
            {"territory_id": "T100", "requires_primary_owner": True},
            {"territory_id": "T200", "requires_primary_owner": True},
        ]
    ).write_csv(inp / "territories.csv")  # type: ignore[operator]
    pl.DataFrame(
        [
            {
                "event_id": "TR001",
                "employee_id": "E001",
                "effective_date": "2026-10-01",
                "from_territory_id": "T100",
                "to_territory_id": "T200",
            }
        ]
    ).write_csv(inp / "transfers.csv")  # type: ignore[operator]


def test_validate_inputs_ok(example_config_path: object) -> None:
    code, out, _ = _run(["validate-inputs", "--config", str(example_config_path)])
    assert code == 0
    assert "configuration OK" in out
    assert "grain:   employee_territory" in out


def test_validate_inputs_bad_config_exits_2(tmp_path: object) -> None:
    bad = tmp_path / "bad.yaml"  # type: ignore[operator]
    bad.write_text("version: 99\n", encoding="utf-8")  # type: ignore[attr-defined]
    code, _, err = _run(["validate-inputs", "--config", str(bad)])
    assert code == 2
    assert "configuration error" in err


def test_validate_inputs_missing_file_exits_2(tmp_path: object) -> None:
    code, _, err = _run(["validate-inputs", "--config", str(tmp_path / "missing.yaml")])  # type: ignore[operator]
    assert code == 2
    assert "not found" in err
