from __future__ import annotations

import re
from pathlib import Path

from rosterops.models import Grain, InputMode, Severity, grain_keys
from rosterops.rules import all_rules

RULE_ROW = re.compile(
    r"^\|\s*([A-Z]{2,3}-\d{3})\s*\|\s*([^|]+?)\s*\|\s*(ERROR|WARNING|INFO)\s*\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)


def _requirements_rows(repo_root: Path) -> dict[str, tuple[str, Severity, frozenset[InputMode]]]:
    text = (repo_root / "REQUIREMENTS.md").read_text(encoding="utf-8")
    section = text.split("## 8. Validation rule catalogue", 1)[1].split("\n## 9.", 1)[0]
    rows: dict[str, tuple[str, Severity, frozenset[InputMode]]] = {}
    for rule_id, name, severity, modes in RULE_ROW.findall(section):
        mode_tokens = modes.split("(", 1)[0]
        mode_set: set[InputMode] = set()
        for token in mode_tokens.split(","):
            token = token.strip()
            if token == "S":
                mode_set.add(InputMode.SNAPSHOT)
            elif token == "P":
                mode_set.add(InputMode.PROCESS)
        rows[rule_id] = (name, Severity(severity.lower()), frozenset(mode_set))
    return rows


def test_every_requirement_rule_is_registered(repo_root: Path) -> None:
    rows = _requirements_rows(repo_root)
    registered = {spec.id for spec in all_rules()}
    assert len(rows) == 86, f"expected 86 rule rows in REQUIREMENTS.md, parsed {len(rows)}"
    missing = set(rows) - registered
    extra = registered - set(rows)
    assert not missing, f"rules documented but not registered: {sorted(missing)}"
    assert not extra, f"rules registered but not documented: {sorted(extra)}"


def test_names_severities_and_modes_match(repo_root: Path) -> None:
    rows = _requirements_rows(repo_root)
    for spec in all_rules():
        name, severity, modes = rows[spec.id]
        assert spec.name == name, f"{spec.id} name mismatch"
        assert spec.default_severity is severity, f"{spec.id} severity mismatch"
        assert spec.modes == modes, f"{spec.id} modes mismatch ({spec.modes} != {modes})"


def test_grain_keys_helper_matches_declaration() -> None:
    assert grain_keys(Grain.EMPLOYEE) == ("employee_id",)
    assert grain_keys(Grain.EMPLOYEE_TERRITORY) == ("employee_id", "territory_id")
    assert grain_keys(Grain.EMPLOYEE_TERRITORY_ASSIGNMENT) == (
        "employee_id",
        "territory_id",
        "assignment_type",
        "effective_from",
    )
    assert grain_keys(Grain.CUSTOM) == ()
    assert grain_keys(Grain.CUSTOM, ["employee_id", "product_code"]) == (
        "employee_id",
        "product_code",
    )
