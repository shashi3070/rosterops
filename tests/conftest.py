from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root (contains REQUIREMENTS.md and examples/)."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def example_config_path(repo_root: Path) -> Path:
    """Path to the shipped illustrative configuration profile."""
    return repo_root / "examples" / "config" / "generic_pharma.yaml"


@pytest.fixture()
def scenario_frames() -> dict[str, pl.DataFrame]:
    """REQUIREMENTS §10 scenario as canonical, in-memory frames.

    Three active REPs (E001..E003) on T100/T200/T300 at baseline 2026-09-30.
    In October: E001 transfers T100->T400 (10-01) then promotes to SENIOR_REP
    (10-15); E002 takes leave 10-05..10-12 and returns 10-13; E003 terminates
    10-20. Four required-owner territories (T100..T400).
    """
    return {
        "baseline": pl.DataFrame(
            [
                {
                    "employee_id": "E001",
                    "employee_status": "Active",
                    "role_code": "REP",
                    "territory_id": "T100",
                    "is_primary": True,
                    "employment_start_date": date(2020, 1, 1),
                },
                {
                    "employee_id": "E002",
                    "employee_status": "Active",
                    "role_code": "REP",
                    "territory_id": "T200",
                    "is_primary": True,
                    "employment_start_date": date(2020, 1, 1),
                },
                {
                    "employee_id": "E003",
                    "employee_status": "Active",
                    "role_code": "REP",
                    "territory_id": "T300",
                    "is_primary": True,
                    "employment_start_date": date(2020, 1, 1),
                },
            ]
        ),
        "territories": pl.DataFrame(
            [
                {"territory_id": "T100", "requires_primary_owner": True},
                {"territory_id": "T200", "requires_primary_owner": True},
                {"territory_id": "T300", "requires_primary_owner": True},
                {"territory_id": "T400", "requires_primary_owner": True},
            ]
        ),
        "transfers": pl.DataFrame(
            [
                {
                    "event_id": "TR001",
                    "employee_id": "E001",
                    "effective_date": date(2026, 10, 1),
                    "from_territory_id": "T100",
                    "to_territory_id": "T400",
                }
            ]
        ),
        "promotions": pl.DataFrame(
            [
                {
                    "event_id": "PR001",
                    "employee_id": "E001",
                    "effective_date": date(2026, 10, 15),
                    "old_role_code": "REP",
                    "new_role_code": "SENIOR_REP",
                }
            ]
        ),
        "leaves": pl.DataFrame(
            [
                {
                    "event_id": "LV001",
                    "employee_id": "E002",
                    "leave_start_date": date(2026, 10, 5),
                    "leave_end_date": date(2026, 10, 12),
                }
            ]
        ),
        "returns": pl.DataFrame(
            [{"event_id": "RT001", "employee_id": "E002", "effective_date": date(2026, 10, 13)}]
        ),
        "terminations": pl.DataFrame(
            [{"event_id": "TM001", "employee_id": "E003", "effective_date": date(2026, 10, 20)}]
        ),
    }


@pytest.fixture()
def scenario_result(scenario_frames: dict[str, pl.DataFrame]):
    """Processed §10 scenario at as_of 2026-10-31."""
    from rosterops import RosterConfig, RosterEngine

    return RosterEngine(RosterConfig()).process(
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
