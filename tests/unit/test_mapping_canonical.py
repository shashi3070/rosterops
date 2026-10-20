from __future__ import annotations

import polars as pl

from rosterops.config import InputRoleConfig
from rosterops.io.raw import RawTable
from rosterops.mapping.canonical import DEFAULT_NULL_TOKENS, map_to_canonical


def _table(columns: dict[str, list[object]]) -> RawTable:
    return RawTable(
        frame=pl.DataFrame(columns).with_columns(pl.all().cast(pl.String, strict=False)),
        source_file="in.csv",
        source_sheet=None,
        header_row=0,
        first_data_row=2,
        format="csv",
        source_columns=tuple(columns),
    )


def _run(cfg: InputRoleConfig, columns: dict[str, list[object]], role: str = "baseline"):
    return map_to_canonical(
        role,
        _table(columns),
        cfg,
        source_file="in.csv",
        source_sheet=None,
        first_data_row=2,
    )


def test_default_null_tokens_include_common_markers() -> None:
    assert "" in DEFAULT_NULL_TOKENS
    assert "N/A" in DEFAULT_NULL_TOKENS
    assert "NULL" in DEFAULT_NULL_TOKENS


def test_basic_mapping_and_lineage() -> None:
    cfg = InputRoleConfig(
        columns={"employee_id": "Employee Number", "territory_id": "Home Territory"}
    )
    result = _run(cfg, {"Employee Number": ["007"], "Home Territory": ["T100"]})
    assert not result.failed
    assert result.frame.columns[:2] == ["employee_id", "territory_id"]
    assert result.frame["employee_id"].to_list() == ["007"]
    assert result.frame["source_row"].to_list() == [2]
    assert result.resolved_fields == frozenset({"employee_id", "territory_id"})


def test_unused_columns_reported_not_dropped() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "Employee Number"})
    result = _run(cfg, {"Employee Number": ["007"], "Extra": ["x"]})
    assert result.unused_columns == ("Extra",)


def test_missing_mapped_column_raises_sch_001() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "Employee Number", "territory_id": "Missing"})
    result = _run(cfg, {"Employee Number": ["007"]})
    rules = {f.rule_id for f in result.findings}
    assert "SCH-001" in rules


def test_alias_resolution() -> None:
    cfg = InputRoleConfig(
        aliases={"employee_id": ["Emp ID", "Employee Number"]},
    )
    result = _run(cfg, {"Emp ID": ["007"]})
    assert not result.failed
    assert result.frame["employee_id"].to_list() == ["007"]


def test_alias_case_insensitive() -> None:
    cfg = InputRoleConfig(aliases={"employee_id": ["emp id"]})
    result = _run(cfg, {"EMP ID": ["007"]})
    assert result.frame["employee_id"].to_list() == ["007"]


def test_ambiguous_mapping_raises_sch_005() -> None:
    # Two canonical fields deliberately mapped to the same source column.
    cfg = InputRoleConfig(columns={"employee_id": "ID", "territory_id": "ID"})
    result = _run(cfg, {"ID": ["007"]})
    assert result.failed
    assert any(f.rule_id == "SCH-005" for f in result.findings)


def test_null_tokens_normalized() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "ID"})
    result = _run(cfg, {"ID": ["007", "N/A", "", "NULL"]})
    assert result.frame["employee_id"].to_list() == ["007", None, None, None]


def test_custom_null_tokens_override_defaults() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "ID"}, null_tokens=["UNKNOWN"])
    result = _run(cfg, {"ID": ["007", "UNKNOWN", "N/A"]})
    # With override, only UNKNOWN is null; N/A is preserved verbatim.
    assert result.frame["employee_id"].to_list() == ["007", None, "N/A"]


def test_trimming_applied() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "ID"})
    result = _run(cfg, {"ID": ["  007  "]})
    assert result.frame["employee_id"].to_list() == ["007"]


def test_date_parse_success_and_failure_located() -> None:
    cfg = InputRoleConfig(columns={"employment_start_date": "Start"})
    result = _run(cfg, {"Start": ["2026-01-01", "bad"]})
    assert result.frame["employment_start_date"].to_list()[0].isoformat() == "2026-01-01"
    failures = [f for f in result.findings if f.rule_id == "SCH-002"]
    assert len(failures) == 1
    assert failures[0].source_row == 3
    assert failures[0].source_column == "employment_start_date"


def test_custom_date_format() -> None:
    cfg = InputRoleConfig(
        columns={"employment_start_date": "Start"},
        date_formats={"employment_start_date": ["%d/%m/%Y"]},
    )
    result = _run(cfg, {"Start": ["31/12/2026"]})
    assert result.frame["employment_start_date"].to_list()[0].isoformat() == "2026-12-31"


def test_boolean_parsing() -> None:
    cfg = InputRoleConfig(columns={"is_primary": "Primary"})
    result = _run(cfg, {"Primary": ["yes", "no", "1", "0", "TRUE", "bad"]})
    vals = result.frame["is_primary"].to_list()
    assert vals[:5] == [True, False, True, False, True]
    assert vals[5] is None
    assert any(f.rule_id == "SCH-002" for f in result.findings)


def test_integer_parsing() -> None:
    cfg = InputRoleConfig(columns={"max_assignees": "Max"})
    result = _run(cfg, {"Max": ["3", "4.0", "x"]}, role="territories")
    vals = result.frame["max_assignees"].to_list()
    assert vals == [3, 4, None]
    assert any(f.rule_id == "SCH-002" for f in result.findings)


def test_list_parsing_semicolon() -> None:
    cfg = InputRoleConfig(columns={"allowed_roles": "Roles"})
    result = _run(cfg, {"Roles": ["REP;SENIOR_REP", "REP"]}, role="territories")
    assert result.frame["allowed_roles"].to_list() == [["REP", "SENIOR_REP"], ["REP"]]


def test_required_field_empty_raises_sch_003() -> None:
    cfg = InputRoleConfig(
        columns={"event_id": "EID", "employee_id": "Emp", "effective_date": "Date"}
    )
    result = _run(
        cfg,
        {"EID": ["E1", "E2"], "Emp": ["007", None], "Date": ["2026-01-01", "2026-01-02"]},
        role="transfers",
    )
    failures = [f for f in result.findings if f.rule_id == "SCH-003"]
    assert len(failures) == 1
    assert failures[0].source_row == 3
    assert failures[0].source_column == "employee_id"


def test_categorical_invalid_value_raises_sch_004() -> None:
    cfg = InputRoleConfig(
        columns={"assignment_type": "Type"},
        allowed_values={"assignment_type": ["PRIMARY", "SECONDARY"]},
    )
    result = _run(cfg, {"Type": ["PRIMARY", "BOGUS"]})
    failures = [f for f in result.findings if f.rule_id == "SCH-004"]
    assert len(failures) == 1
    assert failures[0].actual_value == "BOGUS"
    # Value is preserved, never rewritten.
    assert result.frame["assignment_type"].to_list() == ["PRIMARY", "BOGUS"]


def test_value_map_normalizes_known_codes() -> None:
    cfg = InputRoleConfig(
        columns={"employee_status": "Status"},
        value_maps={"employee_status": {"A": "ACTIVE", "T": "TERMINATED"}},
    )
    result = _run(cfg, {"Status": ["A", "T", "Z"]})
    assert result.frame["employee_status"].to_list() == ["ACTIVE", "TERMINATED", "Z"]


def test_trim_collision_raises_id_005() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "ID"})
    result = _run(cfg, {"ID": ["007", " 007", "123"]})
    failures = [f for f in result.findings if f.rule_id == "ID-005"]
    assert len(failures) == 1
    assert "007" in (failures[0].actual_value or "")


def test_no_trim_collision_when_values_distinct() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "ID"})
    result = _run(cfg, {"ID": ["007", "008", "123"]})
    assert not any(f.rule_id == "ID-005" for f in result.findings)


def test_no_row_dropped_on_parse_failure() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "ID", "employment_start_date": "Start"})
    result = _run(cfg, {"ID": ["1", "2", "3"], "Start": ["2026-01-01", "bad", "2026-03-01"]})
    assert result.frame.height == 3


def test_empty_input_produces_empty_frame() -> None:
    cfg = InputRoleConfig(columns={"employee_id": "ID"})
    tbl = RawTable(
        frame=pl.DataFrame({"ID": pl.Series([], dtype=pl.String)}),
        source_file="in.csv",
        source_sheet=None,
        header_row=0,
        first_data_row=2,
        format="csv",
        source_columns=("ID",),
    )
    result = map_to_canonical(
        "baseline", tbl, cfg, source_file="in.csv", source_sheet=None, first_data_row=2
    )
    assert result.frame.height == 0
