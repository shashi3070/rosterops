"""Synthetic scaling benchmark for the roster engine (Phase 8).

Generates Mode B (snapshot) inputs of 10k / 100k / 1M assignment rows and
records wall time and peak Python-allocation memory for a full validate run.
Polars columnar buffers are allocated outside the Python allocator, so the
peak figure is a lower bound; wall time is the primary signal.

Run:

    python benchmarks/bench_scaling.py

Results are printed as a table suitable for pasting into
IMPLEMENTATION_PHASES.md §4.
"""

from __future__ import annotations

import platform
import sys
import time
import tracemalloc
from datetime import date

import polars as pl

from rosterops import RosterConfig, RosterEngine

SIZES = (10_000, 100_000, 1_000_000)
_AS_OF = date(2026, 10, 31)


def _snapshot(rows: int) -> pl.DataFrame:
    start = date(2020, 1, 1)
    employees = [f"E{i:07d}" for i in range(rows)]
    territories = [f"T{i:07d}" for i in range(rows)]
    statuses = ["Active"] * rows
    roles = ["REP"] * rows
    primaries = [True] * rows
    effective = [date(2024, 1, 1)] * rows
    employment_start = [start] * rows
    return pl.DataFrame(
        {
            "employee_id": employees,
            "employee_status": statuses,
            "role_code": roles,
            "territory_id": territories,
            "is_primary": primaries,
            "effective_from": effective,
            "employment_start_date": employment_start,
        },
        infer_schema_length=None,
    )


def _territories(rows: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "territory_id": [f"T{i:07d}" for i in range(rows)],
            "requires_primary_owner": [True] * rows,
            "territory_status": ["active"] * rows,
            "max_assignees": [1] * rows,
        },
        infer_schema_length=None,
    )


def run_one(rows: int) -> tuple[float, float]:
    snap = _snapshot(rows)
    terr = _territories(rows)
    engine = RosterEngine(RosterConfig())
    tracemalloc.start()
    t0 = time.perf_counter()
    engine.validate_snapshot(snap, as_of=_AS_OF, territories=terr)
    wall = time.perf_counter() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return wall, peak / (1024 * 1024)


def main() -> None:
    print(f"python {platform.python_version()} on {platform.platform()}")
    print(f"polars {pl.__version__}")
    print()
    print(f"{'rows':>10} {'wall_s':>10} {'py_peak_mb':>12}")
    for rows in SIZES:
        wall, peak = run_one(rows)
        print(f"{rows:>10} {wall:>10.3f} {peak:>12.1f}")


if __name__ == "__main__":
    sys.exit(main())
