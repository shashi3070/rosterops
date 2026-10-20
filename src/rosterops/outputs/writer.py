"""Result writers and console report rendering (REQUIREMENTS §11.2, §13).

Mode A emits the full file set (roster, assignments, events, issues, movement
summary, vacancies, reconciliation, metadata; plus ``rosterops_report.xlsx``
when the ``[excel]`` extra is installed). Mode B emits only the subset that
applies — unavailable reports are omitted, never written as misleading empty
files.

Safety (REQUIREMENTS §11.3): never write into input folders, refuse output
directories that collide with inputs, and require ``overwrite=True`` to replace
an existing non-empty directory.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from rosterops.engine.result import RosterResult
from rosterops.exceptions import InputError

__all__ = ["OUTPUT_FILES", "WriteReport", "console_report", "write_outputs"]

#: Canonical file names written for Mode A (subset written for Mode B).
OUTPUT_FILES = (
    "final_roster.parquet",
    "final_roster.csv",
    "assignment_intervals.parquet",
    "normalized_events.parquet",
    "validation_issues.csv",
    "movement_summary.csv",
    "vacancy_report.csv",
    "reconciliation.json",
    "run_metadata.json",
)

_XLSX_NAME = "rosterops_report.xlsx"
_XLSX_ROW_CAP = 100_000
_SHEET_TITLE_MAX = 31


@dataclass(frozen=True, slots=True)
class WriteReport:
    """Paths written by :func:`write_outputs` plus any documented omissions."""

    output_dir: Path
    written: tuple[Path, ...]
    omitted: tuple[tuple[str, str], ...]  # (file_name, reason)


def write_outputs(
    result: RosterResult,
    output_dir: str | Path,
    *,
    input_paths: list[str] | tuple[str, ...] = (),
    overwrite: bool = False,
    excel: bool = True,
) -> WriteReport:
    """Write the result file set into ``output_dir``.

    Raises :class:`InputError` when the directory collides with an input path
    or already exists without ``overwrite=True``.
    """
    out = Path(output_dir)
    _check_output_dir(out, input_paths, overwrite=overwrite)
    written: list[Path] = []
    omitted: list[tuple[str, str]] = []

    # Roster + assignments (always present).
    written.append(_write_frame(result.roster, out / "final_roster.parquet", "parquet"))
    written.append(_write_frame(result.roster, out / "final_roster.csv", "csv"))
    written.append(
        _write_frame(result.assignments, out / "assignment_intervals.parquet", "parquet")
    )

    mode_a = result.mode == "process"
    if mode_a:
        written.append(_write_frame(result.events, out / "normalized_events.parquet", "parquet"))
    else:
        omitted.append(("normalized_events.parquet", "no event ledger in snapshot mode"))

    issues = result.issues if result.issues.width else _empty_issues()
    written.append(_write_frame(issues, out / "validation_issues.csv", "csv"))

    if mode_a:
        written.append(_write_frame(_movement_summary(result), out / "movement_summary.csv", "csv"))
    else:
        omitted.append(("movement_summary.csv", "movement metrics unavailable in snapshot mode"))

    if result.vacancies.width:
        written.append(_write_frame(result.vacancies, out / "vacancy_report.csv", "csv"))
    else:
        omitted.append(("vacancy_report.csv", "vacancy report not derivable from inputs"))

    written.append(_write_reconciliation(result, out / "reconciliation.json"))
    written.append(
        _write_json(result.metadata.to_dict() if result.metadata else {}, out / "run_metadata.json")
    )

    if excel and _openpyxl_available():
        xlsx = out / _XLSX_NAME
        _write_excel(result, xlsx)
        written.append(xlsx)
    elif excel:
        omitted.append((_XLSX_NAME, "install rosterops[excel] to emit the Excel workbook"))

    return WriteReport(output_dir=out, written=tuple(written), omitted=tuple(omitted))


# --------------------------------------------------------------------------- #
# directory safety
# --------------------------------------------------------------------------- #
def _check_output_dir(
    out: Path, input_paths: list[str] | tuple[str, ...], *, overwrite: bool
) -> None:
    resolved = out.resolve()
    for raw in input_paths:
        input_path = Path(raw).resolve()
        if resolved == input_path or resolved == input_path.parent:
            raise InputError(f"refusing to write outputs into input location or its parent: {out}")
        if input_path.is_file() and resolved == input_path.parent:
            raise InputError(f"output directory collides with input folder: {out}")
    if out.exists():
        if not overwrite and any(out.iterdir()):
            raise InputError(
                f"output directory already exists and is not empty: {out} (use --overwrite)"
            )
        if overwrite:
            shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# frame writers
# --------------------------------------------------------------------------- #
def _write_frame(frame: pl.DataFrame, path: Path, fmt: str) -> Path:
    if fmt == "parquet":
        frame.write_parquet(path)
    elif fmt == "csv":
        frame.write_csv(path)
    else:  # pragma: no cover - defensive
        raise InputError(f"unsupported output format: {fmt}")
    return path


def _write_json(payload: Any, path: Path) -> Path:
    path.write_text(json.dumps(payload, indent=2, default=str, sort_keys=True), encoding="utf-8")
    return path


def _write_reconciliation(result: RosterResult, path: Path) -> Path:
    payload = {
        "mode": result.mode,
        "checks": [r.to_dict() for r in result.reconciliation],
        "status": (
            "not_applicable"
            if not result.reconciliation
            else ("fail" if any(r.status == "fail" for r in result.reconciliation) else "pass")
        ),
    }
    return _write_json(payload, path)


def _empty_issues() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "issue_id": [],
            "rule_id": [],
            "category": [],
            "severity": [],
            "message": [],
        }
    )


def _movement_summary(result: RosterResult) -> pl.DataFrame:
    metrics = result.summary.get("metrics", {})
    rows = [
        {
            "metric": key,
            "value": mv.get("value"),
            "status": mv.get("status"),
            "reason": mv.get("reason"),
        }
        for key, mv in sorted(metrics.items())
    ]
    return pl.DataFrame(rows)


# --------------------------------------------------------------------------- #
# excel (optional)
# --------------------------------------------------------------------------- #
def _write_excel(result: RosterResult, path: Path) -> None:
    from openpyxl import Workbook  # type: ignore[import-untyped]

    sheets: dict[str, pl.DataFrame] = {
        "Summary": _movement_summary(result),
        "Final_Roster": result.roster,
        "Vacancies": result.vacancies,
        "Validation_Issues": result.issues if result.issues.width else _empty_issues(),
        "Reconciliation": _reconciliation_frame(result),
        "Run_Metadata": _metadata_frame(result),
    }
    if result.mode == "process":
        sheets["Transfers"] = _events_by_type(result, "transfer")
        sheets["Promotions"] = _events_by_type(result, "promotion")
        sheets["Terminations"] = _events_by_type(result, "termination")
        sheets["Leave_Activity"] = _leave_activity(result)

    workbook = Workbook(write_only=True)
    for name, frame in sheets.items():
        sheet = workbook.create_sheet(title=name[:_SHEET_TITLE_MAX])
        sheet.append(list(frame.columns))
        for row in frame.head(_XLSX_ROW_CAP).iter_rows():
            sheet.append(["#N/A" if value is None else str(value) for value in row])
    workbook.save(path)


def _openpyxl_available() -> bool:
    from importlib.util import find_spec

    return find_spec("openpyxl") is not None


def _events_by_type(result: RosterResult, event_type: str) -> pl.DataFrame:
    if not result.events.width or "event_type" not in result.events.columns:
        return pl.DataFrame()
    return result.events.filter(pl.col("event_type") == event_type)


def _leave_activity(result: RosterResult) -> pl.DataFrame:
    if not result.events.width or "event_type" not in result.events.columns:
        return pl.DataFrame()
    return result.events.filter(pl.col("event_type").is_in(["leave_start", "leave_return"]))


def _reconciliation_frame(result: RosterResult) -> pl.DataFrame:
    if not result.reconciliation:
        return pl.DataFrame({"rule_id": [], "status": [], "detail": []})
    return pl.DataFrame([r.to_dict() for r in result.reconciliation])


def _metadata_frame(result: RosterResult) -> pl.DataFrame:
    payload = result.metadata.to_dict() if result.metadata else {}
    rows = [
        {
            "key": key,
            "value": json.dumps(value, default=str) if not isinstance(value, str) else value,
        }
        for key, value in sorted(payload.items())
    ]
    return pl.DataFrame(rows)


# --------------------------------------------------------------------------- #
# console report (REQUIREMENTS §13)
# --------------------------------------------------------------------------- #
def console_report(result: RosterResult, report: WriteReport | None = None) -> str:
    """Render the concise console report (no full employee rows)."""
    lines: list[str] = []
    lines.append(f"rosterops {_tool_version(result)} — mode: {result.mode}")
    lines.append(f"as-of: {result.as_of}   baseline: {result.baseline_date or 'n/a'}")
    if result.metadata and result.metadata.input_files:
        lines.append("inputs:")
        for item in result.metadata.input_files:
            lines.append(f"  - {item.get('role')}: {item.get('name')}")
    lines.append(f"roster rows: {result.roster.height}")
    lines.append(f"assignment intervals: {result.assignments.height}")
    if result.mode == "process":
        lines.append(f"events: {result.events.height}")
        lines.extend(_event_count_lines(result))

    lines.extend(_metric_lines(result))

    vac = result.vacancies.height
    lines.append(f"vacancy rows: {vac}")

    lines.append(f"findings: {result.error_count()} error(s), {result.warning_count()} warning(s)")
    lines.extend(_severity_by_rule(result))

    if result.reconciliation:
        lines.append("reconciliation:")
        for rec in result.reconciliation:
            lines.append(f"  {rec.rule_id}: {rec.status} ({rec.detail or ''})".rstrip())
    else:
        lines.append("reconciliation: not_applicable (snapshot mode)")

    if report is not None:
        lines.append(f"outputs: {report.output_dir}")
        for path in report.written:
            lines.append(f"  - {path.name}")
        for name, reason in report.omitted:
            lines.append(f"  - {name}: omitted ({reason})")

    top = [f for f in result.findings if f.severity.value in {"error", "warning"}][:10]
    if top:
        lines.append("high-priority findings:")
        for finding in top:
            entity = finding.employee_id or finding.territory_id or finding.event_id or "-"
            tag = finding.severity.value.upper()
            lines.append(f"  [{tag}] {finding.rule_id} {entity}: {finding.message}")

    lines.append(f"exit code: {result.exit_code()}")
    return "\n".join(lines)


def _tool_version(result: RosterResult) -> str:
    return result.metadata.tool_version if result.metadata else "?"


def _event_count_lines(result: RosterResult) -> list[str]:
    metrics = result.summary.get("metrics", {})
    keys = (
        "transfer_events",
        "promotion_events",
        "termination_events",
        "leave_starts",
        "leave_returns",
        "hire_events",
        "rehire_events",
    )
    parts = [f"{k}={metrics[k].get('value')}" for k in keys if k in metrics]
    return ["event counts: " + ", ".join(parts)] if parts else []


def _metric_lines(result: RosterResult) -> list[str]:
    metrics = result.summary.get("metrics", {})
    out: list[str] = []
    for key in ("starting_active", "ending_active", "on_leave_at_cutoff"):
        if key in metrics:
            mv = metrics[key]
            if mv.get("status") == "available":
                out.append(f"{key}: {mv.get('value')}")
            else:
                out.append(f"{key}: not_available ({mv.get('reason')})")
    return out


def _severity_by_rule(result: RosterResult) -> list[str]:
    counts: dict[tuple[str, str], int] = {}
    for finding in result.findings:
        key = (finding.severity.value, finding.rule_id)
        counts[key] = counts.get(key, 0) + 1
    lines = []
    for (severity, rule), count in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        lines.append(f"  {severity} {rule}: {count}")
    return lines
