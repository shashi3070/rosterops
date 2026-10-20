from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from rosterops.io.raw import ReadError
from rosterops.io.readers import SUPPORTED_FORMATS, detect_format, read_raw


def test_detect_format_from_extension() -> None:
    assert detect_format(Path("a.csv")) == "csv"
    assert detect_format(Path("a.txt")) == "csv"
    assert detect_format(Path("a.parquet")) == "parquet"
    assert detect_format(Path("a.pq")) == "parquet"
    assert detect_format(Path("a.xlsx")) == "excel"
    assert detect_format(Path("a.xls")) == "excel"
    assert detect_format(Path("a.XLSX")) == "excel"


def test_detect_format_explicit_declaration_wins() -> None:
    assert detect_format(Path("data.bin"), "csv") == "csv"
    assert detect_format(Path("data.csv"), "parquet") == "parquet"


def test_detect_format_unknown_extension_raises_ing_002() -> None:
    with pytest.raises(ReadError) as exc:
        detect_format(Path("data.json"))
    assert exc.value.rule_id == "ING-002"
    assert "supported formats" in (exc.value.hint or "")


def test_detect_format_bad_declaration_raises_ing_002() -> None:
    with pytest.raises(ReadError) as exc:
        detect_format(Path("data.csv"), "json")
    assert exc.value.rule_id == "ING-002"


def test_supported_formats_cover_documented_set() -> None:
    assert set(SUPPORTED_FORMATS.values()) == {"csv", "parquet", "excel"}


def test_read_missing_file_raises_ing_001(tmp_path: Path) -> None:
    with pytest.raises(ReadError) as exc:
        read_raw(tmp_path / "missing.csv")
    assert exc.value.rule_id == "ING-001"
    assert "not found" in exc.value.message


def test_read_directory_raises_ing_001(tmp_path: Path) -> None:
    with pytest.raises(ReadError) as exc:
        read_raw(tmp_path)
    assert exc.value.rule_id == "ING-001"
    assert "not a file" in exc.value.message


def test_read_csv_preserves_leading_zeros_and_strings(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    path.write_text(
        "Employee Number,Home Territory,Notes\n007,T100,keep\n00123,T200,also keep\n",
        encoding="utf-8",
    )
    table = read_raw(path)
    assert table.format == "csv"
    assert table.frame["Employee Number"].to_list() == ["007", "00123"]
    assert table.frame["Employee Number"].dtype == pl.String
    assert table.first_data_row == 2
    assert table.row_number(0) == 2
    assert table.row_number(1) == 3


def test_read_csv_header_row_offset(tmp_path: Path) -> None:
    path = tmp_path / "roster.csv"
    path.write_text(
        "junk line header\nEmployee Number,Home Territory\n007,T100\n",
        encoding="utf-8",
    )
    table = read_raw(path, header_row=1)
    assert table.frame.columns == ["Employee Number", "Home Territory"]
    assert table.first_data_row == 3
    assert table.frame["Employee Number"].to_list() == ["007"]


def test_read_csv_all_strings_not_inferred(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    path.write_text("a,b,c\n1,2.5,2026-01-01\n", encoding="utf-8")
    table = read_raw(path)
    assert all(dtype == pl.String for dtype in table.frame.dtypes)


def test_duplicate_and_blank_headers_normalized(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    path.write_text("id,,id\n1,x,2\n", encoding="utf-8")
    table = read_raw(path)
    assert table.frame.columns == ["id", "column_2", "id_2"]


def test_read_parquet_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "t.parquet"
    pl.DataFrame({"employee_id": ["007", "123"], "territory_id": ["T1", "T2"]}).write_parquet(path)
    table = read_raw(path)
    assert table.format == "parquet"
    assert table.frame["employee_id"].to_list() == ["007", "123"]
    assert all(dtype == pl.String for dtype in table.frame.dtypes)


def test_read_parquet_missing_file_raises_ing_001(tmp_path: Path) -> None:
    with pytest.raises(ReadError) as exc:
        read_raw(tmp_path / "missing.parquet")
    assert exc.value.rule_id == "ING-001"
