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


def test_process_not_implemented_exits_2() -> None:
    code, _, err = _run(
        [
            "process",
            "--baseline",
            "b.xlsx",
            "--baseline-date",
            "2026-09-30",
            "--as-of",
            "2026-10-31",
            "--config",
            "c.yaml",
            "--output-dir",
            "out",
        ]
    )
    assert code == 2
    assert "not implemented yet" in err


def test_validate_not_implemented_exits_2() -> None:
    code, _, err = _run(
        [
            "validate",
            "--snapshot",
            "s.xlsx",
            "--as-of",
            "2026-10-31",
            "--config",
            "c.yaml",
            "--output-dir",
            "out",
        ]
    )
    assert code == 2
    assert "not implemented yet" in err


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
