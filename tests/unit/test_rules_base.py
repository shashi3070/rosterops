from __future__ import annotations

import pytest

from rosterops.exceptions import RosterOpsError
from rosterops.models import InputMode, Severity
from rosterops.rules import (
    Finding,
    RuleSpec,
    all_rule_ids,
    all_rules,
    get_rule,
    has_rule,
    severity_rank,
    sort_and_number,
    sort_findings,
)
from rosterops.rules.base import register_rule

EXPECTED_RULE_COUNT = 86


def test_registry_contains_all_86_rules() -> None:
    assert len(all_rule_ids()) == EXPECTED_RULE_COUNT
    assert len(all_rules()) == EXPECTED_RULE_COUNT
    ids = [spec.id for spec in all_rules()]
    assert ids == sorted(ids)  # deterministic ordering


def test_every_spec_is_complete() -> None:
    for spec in all_rules():
        assert spec.id and spec.name and spec.description
        assert spec.modes, spec.id
        assert spec.default_severity in Severity
        assert spec.group
        assert spec.mode_labels


def test_get_rule_and_has_rule() -> None:
    spec = get_rule("TRF-002")
    assert spec.group == "transfer"
    assert spec.default_severity is Severity.ERROR
    assert has_rule("TRF-002") is True
    assert has_rule("NOPE-001") is False
    with pytest.raises(KeyError, match="TRF-002"):
        get_rule("TRF-002X")  # wrong format, not registered


def test_duplicate_registration_rejected() -> None:
    with pytest.raises(RosterOpsError, match="duplicate"):
        register_rule(
            id="ING-001",
            name="x",
            description="y",
            default_severity=Severity.ERROR,
            modes=frozenset({InputMode.SNAPSHOT}),
            group="input",
        )


def test_malformed_rule_id_rejected() -> None:
    with pytest.raises(RosterOpsError, match="malformed"):
        register_rule(
            id="lowercase-1",
            name="x",
            description="y",
            default_severity=Severity.ERROR,
            modes=frozenset({InputMode.SNAPSHOT}),
            group="input",
        )


def test_unknown_group_rejected() -> None:
    with pytest.raises(RosterOpsError, match="unknown group"):
        register_rule(
            id="ZZZ-001",
            name="x",
            description="y",
            default_severity=Severity.ERROR,
            modes=frozenset({InputMode.SNAPSHOT}),
            group="weather",
        )


def test_empty_modes_rejected() -> None:
    with pytest.raises(RosterOpsError, match="at least one mode"):
        register_rule(
            id="ZZZ-002",
            name="x",
            description="y",
            default_severity=Severity.ERROR,
            modes=frozenset(),
            group="input",
        )


def test_severity_rank_orders_errors_first() -> None:
    assert severity_rank(Severity.ERROR) < severity_rank(Severity.WARNING)
    assert severity_rank(Severity.WARNING) < severity_rank(Severity.INFO)


def test_finding_issue_key_is_stable_and_content_sensitive() -> None:
    base = dict(
        rule_id="TRF-002",
        severity=Severity.ERROR,
        message="source mismatch",
        category="transfer",
        employee_id="E001",
        source_file="transfers.xlsx",
        source_row=5,
    )
    first = Finding(**base)
    second = Finding(**base)
    assert first.issue_key == second.issue_key
    assert len(first.issue_key) == 16
    changed = Finding(**{**base, "message": "different message"})
    assert changed.issue_key != first.issue_key


def test_finding_from_spec_uses_defaults() -> None:
    spec = get_rule("ID-005")
    finding = Finding.from_spec(spec, "collision between 'E001' and ' E001 '", employee_id="E001")
    assert finding.rule_id == "ID-005"
    assert finding.severity is Severity.WARNING  # spec default
    assert finding.category == "identifier"  # spec group
    assert finding.issue_key


def test_sort_findings_orders_by_severity_rule_file_row() -> None:
    def f(rule: str, sev: Severity, file: str, row: int) -> Finding:
        return Finding(
            rule_id=rule, severity=sev, message="m", category="x", source_file=file, source_row=row
        )

    findings = [
        f("TRF-002", Severity.ERROR, "a.xlsx", 3),
        f("ID-005", Severity.WARNING, "a.xlsx", 1),
        f("TRF-001", Severity.ERROR, "b.xlsx", 1),
        f("TRF-002", Severity.ERROR, "a.xlsx", 1),
        f("REC-003", Severity.INFO, "a.xlsx", 1),
    ]
    ordered = sort_findings(findings)
    # Explicit ordering check: severity first, then rule_id, then file, then row.
    assert [x.rule_id for x in ordered] == [
        "TRF-001",  # error, rule before file
        "TRF-002",  # error, row 1
        "TRF-002",  # error, row 3
        "ID-005",  # warning
        "REC-003",  # info
    ]
    trf_errors = [x for x in ordered if x.rule_id == "TRF-002"]
    assert [x.source_row for x in trf_errors] == [1, 3]


def test_sort_and_number_assigns_sequential_ids() -> None:
    findings = [
        Finding(rule_id="B-000", severity=Severity.INFO, message="m", category="x"),
        Finding(rule_id="A-000", severity=Severity.ERROR, message="m", category="x"),
    ]
    numbered = sort_and_number(findings)
    assert [f.issue_id for f in numbered] == ["ISS-000001", "ISS-000002"]
    assert numbered[0].rule_id == "A-000"  # error first
    # Originals untouched.
    assert findings[0].issue_id == ""


def test_finding_to_row_has_contract_columns() -> None:
    row = Finding(
        rule_id="SCH-003",
        severity=Severity.ERROR,
        message="missing employee_id",
        category="input",
        employee_id="E001",
        source_file="roster.xlsx",
        source_sheet="Roster",
        source_row=7,
        source_column="Employee Number",
    ).to_row()
    expected = {
        "issue_id",
        "issue_key",
        "rule_id",
        "category",
        "severity",
        "message",
        "employee_id",
        "territory_id",
        "event_id",
        "effective_date",
        "source_file",
        "source_sheet",
        "source_row",
        "source_column",
        "actual_value",
        "expected_value",
        "suggested_action",
    }
    assert set(row) == expected
    assert row["source_row"] == 7
    assert row["severity"] == "error"


def test_rules_with_declared_params() -> None:
    spec = get_rule("TER-005")
    assert spec.params == {"grace_days": int}


def test_spec_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    spec = get_rule("ORG-001")
    with pytest.raises(FrozenInstanceError):
        spec.name = "changed"  # type: ignore[misc]


def test_rule_spec_mode_labels_sorted() -> None:
    spec = RuleSpec(
        id="ZZZ-003",
        name="n",
        description="d",
        default_severity=Severity.INFO,
        modes=frozenset({InputMode.PROCESS, InputMode.SNAPSHOT}),
        group="input",
    )
    assert spec.mode_labels == ("process", "snapshot")
