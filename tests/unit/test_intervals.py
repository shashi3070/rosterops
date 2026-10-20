from __future__ import annotations

from datetime import date

from rosterops.domain.intervals import (
    Interval,
    OverlapPair,
    effective_end,
    find_overlapping_pairs,
    intersection,
    interval_contains,
    intervals_overlap,
    is_valid_interval,
    normalize_interval_end,
    sort_intervals,
)

D = date


def test_adjacent_half_open_intervals_do_not_overlap() -> None:
    # [2026-10-01, 2026-11-01) then [2026-11-01, ...) are contiguous.
    assert not intervals_overlap(D(2026, 10, 1), D(2026, 11, 1), D(2026, 11, 1), None)
    assert not intervals_overlap(D(2026, 11, 1), D(2026, 12, 1), D(2026, 10, 1), D(2026, 11, 1))


def test_overlapping_intervals_detected_both_directions() -> None:
    a = (D(2026, 10, 1), D(2026, 10, 31))
    b = (D(2026, 10, 15), D(2026, 11, 15))
    assert intervals_overlap(*a, *b)
    assert intervals_overlap(*b, *a)


def test_open_ended_interval_treated_as_unbounded() -> None:
    assert intervals_overlap(D(2026, 1, 1), None, D(2025, 6, 1), D(2025, 7, 1)) is False
    assert intervals_overlap(D(2026, 1, 1), None, D(2025, 6, 1), D(2026, 2, 1)) is True
    assert effective_end(None) == date.max


def test_one_day_gap_is_not_overlap() -> None:
    assert not intervals_overlap(D(2026, 10, 1), D(2026, 10, 10), D(2026, 10, 11), D(2026, 10, 20))


def test_validity_and_zero_length() -> None:
    assert is_valid_interval(D(2026, 10, 1), D(2026, 10, 1))
    assert not is_valid_interval(D(2026, 10, 1), D(2026, 9, 30))
    assert is_valid_interval(D(2026, 10, 1), None)
    # A zero-length interval overlaps nothing.
    assert not intervals_overlap(D(2026, 10, 1), D(2026, 10, 1), D(2026, 9, 1), D(2026, 12, 1))


def test_intersection() -> None:
    result = intersection(D(2026, 10, 1), D(2026, 11, 1), D(2026, 10, 20), D(2026, 12, 1))
    assert result == (D(2026, 10, 20), D(2026, 11, 1))
    assert intersection(D(2026, 10, 1), D(2026, 10, 2), D(2026, 10, 2), D(2026, 10, 3)) is None
    open_result = intersection(D(2026, 1, 1), None, D(2026, 6, 1), D(2026, 7, 1))
    assert open_result == (D(2026, 6, 1), D(2026, 7, 1))


def test_contains_is_half_open() -> None:
    start, end = D(2026, 10, 1), D(2026, 11, 1)
    assert interval_contains(start, end, D(2026, 10, 1))
    assert interval_contains(start, end, D(2026, 10, 31))
    assert not interval_contains(start, end, D(2026, 11, 1))
    assert not interval_contains(start, end, D(2026, 9, 30))


def test_interval_dataclass() -> None:
    iv = Interval(D(2026, 10, 1), D(2026, 11, 1))
    assert iv.is_valid()
    assert iv.contains(D(2026, 10, 31))
    assert not iv.overlaps(Interval(D(2026, 11, 1), D(2026, 12, 1)))
    assert iv.overlaps(Interval(D(2026, 10, 15), None))
    inverted = Interval(D(2026, 11, 1), D(2026, 10, 1))
    assert not inverted.is_valid()


def test_normalize_inclusive_end_adds_one_day() -> None:
    assert normalize_interval_end(D(2026, 10, 1), D(2026, 10, 31), interval_end="inclusive") == (
        D(2026, 10, 1),
        D(2026, 11, 1),
    )
    assert normalize_interval_end(D(2026, 10, 1), D(2026, 10, 31), interval_end="exclusive") == (
        D(2026, 10, 1),
        D(2026, 10, 31),
    )
    assert normalize_interval_end(D(2026, 10, 1), None, interval_end="inclusive") == (
        D(2026, 10, 1),
        None,
    )


def test_sweep_finds_overlaps_and_ignores_adjacent() -> None:
    items = [
        ("a", D(2026, 10, 1), D(2026, 11, 1)),
        ("b", D(2026, 11, 1), D(2026, 12, 1)),  # adjacent to a: no overlap
        ("c", D(2026, 10, 15), D(2026, 10, 20)),  # inside a
        ("d", D(2027, 1, 1), None),  # open-ended, disjoint
        ("e", D(2026, 10, 18), D(2026, 10, 18)),  # zero-length: overlaps nothing
    ]
    pairs = find_overlapping_pairs(items)
    assert [(p.key_a, p.key_b) for p in pairs] == [("a", "c")]
    assert pairs[0].overlap_start == D(2026, 10, 15)
    assert pairs[0].overlap_end == D(2026, 10, 20)


def test_sweep_is_deterministic_under_input_order() -> None:
    items = [
        ("x", D(2026, 1, 1), D(2026, 3, 1)),
        ("y", D(2026, 2, 1), D(2026, 4, 1)),
        ("z", D(2026, 2, 15), D(2026, 2, 20)),
    ]
    expected = [(p.key_a, p.key_b) for p in find_overlapping_pairs(items)]
    shuffled = list(reversed(items))
    assert [(p.key_a, p.key_b) for p in find_overlapping_pairs(shuffled)] == expected


def test_sweep_three_way_overlap() -> None:
    items = [
        ("a", D(2026, 1, 1), D(2026, 12, 31)),
        ("b", D(2026, 2, 1), D(2026, 11, 30)),
        ("c", D(2026, 3, 1), D(2026, 10, 31)),
    ]
    pairs = find_overlapping_pairs(items)
    assert {(p.key_a, p.key_b) for p in pairs} == {("a", "b"), ("a", "c"), ("b", "c")}


def test_sort_intervals_orders_by_start_then_end_then_key() -> None:
    items = [
        ("b", D(2026, 1, 1), None),
        ("a", D(2026, 1, 1), D(2026, 2, 1)),
        ("c", D(2025, 12, 1), D(2026, 1, 1)),
    ]
    ordered = sort_intervals(items)
    assert [key for key, _, _ in ordered] == ["c", "a", "b"]


def test_overlap_pair_type() -> None:
    pair = OverlapPair("a", "b", D(2026, 1, 1), None)
    assert pair.overlap_end is None
