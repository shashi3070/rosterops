from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from rosterops.config import InputRoleConfig
from rosterops.exceptions import InputError
from rosterops.io.ingest import ingest_role

_HAS_EXCEL = importlib.util.find_spec("fastexcel") is not None


def test_optional_role_without_path_skipped_silently() -> None:
    result = ingest_role("transfers", InputRoleConfig(required=False))
    assert result.skipped
    assert not result.failed
    assert result.skip_reason == "no path configured"
    assert result.findings == ()


def test_required_missing_file_raises_input_error(tmp_path: Path) -> None:
    cfg = InputRoleConfig(path=str(tmp_path / "missing.csv"), required=True)
    with pytest.raises(InputError):
        ingest_role("baseline", cfg)


def test_optional_missing_file_records_ing_001(tmp_path: Path) -> None:
    cfg = InputRoleConfig(path=str(tmp_path / "missing.csv"), required=False)
    result = ingest_role("transfers", cfg)
    assert result.skipped
    assert result.failed
    assert result.findings[0].rule_id == "ING-001"


def test_unsupported_format_optional_records_ing_002(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text("{}", encoding="utf-8")
    cfg = InputRoleConfig(path=str(path), required=False)
    result = ingest_role("transfers", cfg)
    assert result.skipped
    assert result.findings[0].rule_id == "ING-002"


def test_required_unsupported_format_raises_input_error(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text("{}", encoding="utf-8")
    cfg = InputRoleConfig(path=str(path), required=True)
    with pytest.raises(InputError):
        ingest_role("baseline", cfg)


def test_successful_ingest_end_to_end(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    path.write_text(
        "Employee Number,Home Territory,Primary Flag,Assignment Start\n"
        "007,T100,yes,2026-01-01\n"
        "123,T200,no,2026-02-01\n",
        encoding="utf-8",
    )
    cfg = InputRoleConfig(
        path=str(path),
        format="csv",
        columns={
            "employee_id": "Employee Number",
            "territory_id": "Home Territory",
            "is_primary": "Primary Flag",
            "effective_from": "Assignment Start",
        },
    )
    result = ingest_role("baseline", cfg)
    assert not result.skipped
    assert not result.failed
    assert result.frame.height == 2
    assert result.frame["employee_id"].to_list() == ["007", "123"]
    assert result.findings == ()


def test_required_structural_mapping_failure_raises(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    path.write_text("ID\n007\n", encoding="utf-8")
    # Two canonical fields pointing at the same source -> SCH-005 ambiguity.
    cfg = InputRoleConfig(
        path=str(path),
        format="csv",
        columns={"employee_id": "ID", "territory_id": "ID"},
        required=True,
    )
    with pytest.raises(InputError):
        ingest_role("baseline", cfg)


def test_optional_structural_mapping_failure_records_findings(tmp_path: Path) -> None:
    path = tmp_path / "r.csv"
    path.write_text("ID\n007\n", encoding="utf-8")
    cfg = InputRoleConfig(
        path=str(path),
        format="csv",
        columns={"employee_id": "ID", "territory_id": "ID"},
        required=False,
    )
    result = ingest_role("baseline", cfg)
    assert result.skipped
    assert result.failed
    assert any(f.rule_id == "SCH-005" for f in result.findings)


@pytest.mark.skipif(not _HAS_EXCEL, reason="rosterops[excel] extra not installed")
def test_excel_ingest_roundtrip(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "roster.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Roster"
    ws.append(["Employee Number", "Home Territory"])
    ws.append(["007", "T100"])
    wb.save(path)

    cfg = InputRoleConfig(
        path=str(path),
        format="excel",
        sheet_name="Roster",
        columns={"employee_id": "Employee Number", "territory_id": "Home Territory"},
    )
    result = ingest_role("baseline", cfg)
    assert result.frame["employee_id"].to_list() == ["007"]
    assert result.frame["source_sheet"].to_list() == ["Roster"]


@pytest.mark.skipif(not _HAS_EXCEL, reason="rosterops[excel] extra not installed")
def test_excel_missing_sheet_raises_ing_003(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "roster.xlsx"
    wb = Workbook()
    wb.active.title = "Sheet1"
    wb.save(path)

    cfg = InputRoleConfig(path=str(path), format="excel", sheet_name="Missing", required=True)
    with pytest.raises(InputError):
        ingest_role("baseline", cfg)


@pytest.mark.skipif(_HAS_EXCEL, reason="only meaningful without the excel extra")
def test_excel_without_extra_reports_install_hint(tmp_path: Path) -> None:
    path = tmp_path / "roster.xlsx"
    path.write_bytes(b"not a real workbook")
    cfg = InputRoleConfig(path=str(path), format="excel", required=False)
    result = ingest_role("baseline", cfg)
    assert result.findings[0].rule_id == "ING-002"
    assert "rosterops[excel]" in result.findings[0].message
