"""Property-based tests for the engine (REQUIREMENTS Â§16).

Each property is phrased so it holds for *all* generated inputs (not just
happy-path fixtures): the strategies generate dates, optional events, and
employee pools, and the invariants are stated over whatever the engine returns.
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from rosterops import RosterConfig, RosterEngine

DAY = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))
_BASELINE = date(2026, 1, 1)
_AS_OF = date(2026, 6, 30)


def _baseline(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "employee_id": f"E{i:03d}",
                "employee_status": "Active",
                "role_code": "REP",
                "territory_id": f"T{i:03d}",
                "is_primary": True,
                "employment_start_date": date(2019, 1, 1),
            }
            for i in range(n)
        ],
        infer_schema_length=None,
    )


def _engine() -> RosterEngine:
    return RosterEngine(RosterConfig())


# --------------------------------------------------------------------------- #
# normalization does not mutate the caller's frame
# --------------------------------------------------------------------------- #
@given(n=st.integers(min_value=1, max_value=6), day=DAY)
@settings(max_examples=50, deadline=None)
def test_process_does_not_mutate_source_frames(n: int, day: date) -> None:
    baseline = _baseline(n)
    transfers = pl.DataFrame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E000",
                "effective_date": day,
                "from_territory_id": "T000",
                "to_territory_id": "T999",
            }
        ],
        infer_schema_length=None,
    )
    baseline_before = baseline.clone()
    transfers_before = transfers.clone()
    _engine().process(
        baseline=baseline,
        baseline_date=_BASELINE,
        as_of=_AS_OF,
        transfers=transfers,
    )
    assert baseline.equals(baseline_before)
    assert transfers.equals(transfers_before)


# --------------------------------------------------------------------------- #
# reapplying an event never silently duplicates it
# --------------------------------------------------------------------------- #
@given(n=st.integers(min_value=2, max_value=6))
@settings(max_examples=30, deadline=None)
def test_duplicate_event_never_silently_duplicates_state(n: int) -> None:
    baseline = _baseline(n)
    # Same transfer twice (identical content, different ids): must dedupe.
    transfers = pl.DataFrame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E000",
                "effective_date": date(2026, 3, 1),
                "from_territory_id": "T000",
                "to_territory_id": "T001",
            },
            {
                "event_id": "TR2",
                "employee_id": "E000",
                "effective_date": date(2026, 3, 1),
                "from_territory_id": "T000",
                "to_territory_id": "T001",
            },
        ],
        infer_schema_length=None,
    )
    result = _engine().process(
        baseline=baseline,
        baseline_date=_BASELINE,
        as_of=_AS_OF,
        transfers=transfers,
    )
    # Only one active transfer should ever be applied to state.
    assert result.summary["metrics"]["transfer_events"]["value"] == 1
    assert "ID-007" in {f.rule_id for f in result.findings}


# --------------------------------------------------------------------------- #
# future non-applicable events don't change earlier as-of state
# --------------------------------------------------------------------------- #
@given(n=st.integers(min_value=2, max_value=6))
@settings(max_examples=30, deadline=None)
def test_future_event_does_not_change_earlier_as_of(n: int) -> None:
    baseline = _baseline(n)
    # Transfer dated after the first as_of; the early run must ignore it.
    transfers = pl.DataFrame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E000",
                "effective_date": date(2026, 8, 1),
                "from_territory_id": "T000",
                "to_territory_id": "T001",
            }
        ],
        infer_schema_length=None,
    )
    early = _engine().process(
        baseline=baseline,
        baseline_date=_BASELINE,
        as_of=date(2026, 6, 30),
        transfers=transfers,
    )
    later = _engine().process(
        baseline=baseline,
        baseline_date=_BASELINE,
        as_of=date(2026, 12, 31),
        transfers=transfers,
    )
    assert early.summary["metrics"]["transfer_events"]["value"] == 0
    assert later.summary["metrics"]["transfer_events"]["value"] == 1


# --------------------------------------------------------------------------- #
# valid internal transfer preserves headcount
# --------------------------------------------------------------------------- #
@given(n=st.integers(min_value=2, max_value=8))
@settings(max_examples=40, deadline=None)
def test_valid_transfer_preserves_headcount(n: int) -> None:
    baseline = _baseline(n)
    transfers = pl.DataFrame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E000",
                "effective_date": date(2026, 3, 1),
                "from_territory_id": "T000",
                "to_territory_id": "T001",
            }
        ],
        infer_schema_length=None,
    )
    result = _engine().process(
        baseline=baseline,
        baseline_date=_BASELINE,
        as_of=_AS_OF,
        transfers=transfers,
    )
    assert result.summary["metrics"]["starting_active"]["value"] == n
    assert result.summary["metrics"]["ending_active"]["value"] == n


# --------------------------------------------------------------------------- #
# promotion alone preserves headcount
# --------------------------------------------------------------------------- #
@given(n=st.integers(min_value=1, max_value=8))
@settings(max_examples=40, deadline=None)
def test_promotion_preserves_headcount(n: int) -> None:
    baseline = _baseline(n)
    promotions = pl.DataFrame(
        [
            {
                "event_id": "PR1",
                "employee_id": "E000",
                "effective_date": date(2026, 3, 1),
                "old_role_code": "REP",
                "new_role_code": "SENIOR_REP",
            }
        ],
        infer_schema_length=None,
    )
    result = _engine().process(
        baseline=baseline,
        baseline_date=_BASELINE,
        as_of=_AS_OF,
        promotions=promotions,
    )
    assert result.summary["metrics"]["ending_active"]["value"] == n


# --------------------------------------------------------------------------- #
# leave round-trip preserves headcount
# --------------------------------------------------------------------------- #
@given(
    n=st.integers(min_value=1, max_value=8),
    start=st.dates(min_value=date(2026, 2, 1), max_value=date(2026, 5, 1)),
    length=st.integers(min_value=1, max_value=30),
)
@settings(max_examples=50, deadline=None)
def test_leave_round_trip_preserves_headcount(n: int, start: date, length: int) -> None:
    baseline = _baseline(n)
    end = start + timedelta(days=length)
    leaves = pl.DataFrame(
        [
            {
                "event_id": "LV1",
                "employee_id": "E000",
                "leave_start_date": start,
                "leave_end_date": end,
            }
        ],
        infer_schema_length=None,
    )
    returns = pl.DataFrame(
        [{"event_id": "RT1", "employee_id": "E000", "effective_date": end + timedelta(days=1)}],
        infer_schema_length=None,
    )
    result = _engine().process(
        baseline=baseline,
        baseline_date=_BASELINE,
        as_of=_AS_OF,
        leaves=leaves,
        returns=returns,
    )
    assert result.summary["metrics"]["starting_active"]["value"] == n
    assert result.summary["metrics"]["ending_active"]["value"] == n


# --------------------------------------------------------------------------- #
# transfer ins/outs reconcile (one event => one out + one in)
# --------------------------------------------------------------------------- #
@given(
    n=st.integers(min_value=2, max_value=8),
    day=st.dates(min_value=date(2026, 2, 1), max_value=date(2026, 5, 1)),
)
@settings(max_examples=40, deadline=None)
def test_transfer_ins_outs_reconcile(n: int, day: date) -> None:
    baseline = _baseline(n)
    transfers = pl.DataFrame(
        [
            {
                "event_id": "TR1",
                "employee_id": "E000",
                "effective_date": day,
                "from_territory_id": "T000",
                "to_territory_id": "T001",
            }
        ],
        infer_schema_length=None,
    )
    result = _engine().process(
        baseline=baseline,
        baseline_date=_BASELINE,
        as_of=_AS_OF,
        transfers=transfers,
    )
    rec = {r.rule_id: r for r in result.reconciliation}
    assert rec["REC-002"].status == "pass"
