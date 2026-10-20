from __future__ import annotations

from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from rosterops.domain.dates import event_in_reconstruction_window, parse_date
from rosterops.domain.intervals import (
    find_overlapping_pairs,
    intervals_overlap,
    normalize_interval_end,
)

DAY = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


@given(a=DAY, b=DAY, c=DAY, d=DAY)
def test_overlap_is_symmetric(a: date, b: date, c: date, d: date) -> None:
    assert intervals_overlap(a, b, c, d) == intervals_overlap(c, d, a, b)


@given(start=DAY, end=DAY)
def test_adjacent_intervals_never_overlap(start: date, end: date) -> None:
    # [start, end) followed by [end, ...) must be contiguous, not overlapping.
    if start < end:
        assert not intervals_overlap(start, end, end, None)
        assert not intervals_overlap(end, None, start, end)


@given(start=DAY, delta=st.integers(min_value=1, max_value=365))
def test_inclusive_end_converts_without_gap_or_overlap(start: date, delta: int) -> None:
    end_inclusive = start + timedelta(days=delta)
    s2, e2 = normalize_interval_end(start, end_inclusive, interval_end="inclusive")
    assert e2 == end_inclusive + timedelta(days=1)
    # The day after the inclusive end is outside; the inclusive end itself is inside.
    assert not intervals_overlap(s2, e2, e2, e2 + timedelta(days=30))
    assert intervals_overlap(s2, e2, end_inclusive, end_inclusive + timedelta(days=1))


@given(start=DAY, end=DAY)
def test_normalize_exclusive_passthrough(start: date, end: date) -> None:
    assert normalize_interval_end(start, end, interval_end="exclusive") == (start, end)


def _brute_force_pairs(items: list[tuple[str, date, date | None]]) -> set[frozenset[str]]:
    expected: set[frozenset[str]] = set()
    for i, (ka, sa, ea) in enumerate(items):
        a_eff = ea if ea is not None else date.max
        for kb, sb, eb in items[i + 1 :]:
            b_eff = eb if eb is not None else date.max
            if sa < b_eff and sb < a_eff:
                expected.add(frozenset({ka, kb}))
    return expected


@given(
    items=st.lists(
        st.tuples(
            st.builds(lambda n: f"k{n}", st.integers(min_value=0, max_value=9)),
            DAY,
            st.one_of(DAY, st.none()),
        ),
        min_size=0,
        max_size=8,
        unique_by=lambda item: item[0],
    )
)
@settings(max_examples=60)
def test_sweep_matches_brute_force(items: list[tuple[str, date, date | None]]) -> None:
    # Invalid (inverted/zero-length) intervals are filtered by callers upstream;
    # here we verify the sweep agrees with an O(n^2) reference on valid input.
    usable = [(k, s, e) for k, s, e in items if e is None or e > s]
    sweep = {frozenset({p.key_a, p.key_b}) for p in find_overlapping_pairs(usable)}
    assert sweep == _brute_force_pairs(usable)


@given(baseline=DAY, offset=st.integers(min_value=-60, max_value=60))
@settings(max_examples=100)
def test_reconstruction_window_boundaries(baseline: date, offset: int) -> None:
    as_of = baseline + timedelta(days=30)
    event_day = baseline + timedelta(days=offset)
    in_window = event_in_reconstruction_window(
        event_day, baseline, as_of, baseline_includes_effective_date=True
    )
    # Window is strictly after baseline and up to as_of inclusive.
    assert in_window == (baseline < event_day <= as_of)


@given(text=st.text(alphabet="0123456789-", min_size=0, max_size=20))
def test_parse_date_never_raises(text: str) -> None:
    parse_date(text)  # returns None or a date; never raises
