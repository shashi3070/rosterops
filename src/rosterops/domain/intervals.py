"""Half-open interval primitives: ``[start, end)`` with a nullable end.

The canonical convention throughout rosterops is half-open intervals where the
start is inclusive, the end is exclusive, and a ``None`` end means open-ended.
All temporal rules must build on these primitives so that adjacent intervals
(``[2026-10-01, 2026-11-01)`` followed by ``[2026-11-01, ...)``) are
contiguous, never overlapping.

The ``find_overlapping_pairs`` sweep is a straightforward reference
implementation used by rules and tests; vectorized Polars equivalents are used
for large frames in later phases.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TypeAlias

__all__ = [
    "Interval",
    "OverlapPair",
    "effective_end",
    "find_overlapping_pairs",
    "intersection",
    "interval_contains",
    "intervals_overlap",
    "is_valid_interval",
    "normalize_interval_end",
    "sort_intervals",
]

#: Sentinel end for open intervals when a concrete date is required.
OPEN_END: date = date.max

KeyedInterval: TypeAlias = tuple[str, date, date | None]


@dataclass(frozen=True, slots=True)
class Interval:
    """A half-open ``[start, end)`` interval; ``end=None`` means open-ended."""

    start: date
    end: date | None = None

    @property
    def effective_end(self) -> date:
        """Concrete end used for comparisons (``date.max`` when open)."""
        return OPEN_END if self.end is None else self.end

    def is_valid(self) -> bool:
        """True when the interval bounds are not inverted."""
        return self.end is None or self.end >= self.start

    def contains(self, day: date) -> bool:
        """True when ``day`` falls inside ``[start, end)``."""
        return self.start <= day < self.effective_end

    def overlaps(self, other: Interval) -> bool:
        """True when two half-open intervals share at least one instant."""
        return intervals_overlap(self.start, self.end, other.start, other.end)


@dataclass(frozen=True, slots=True)
class OverlapPair:
    """A detected overlap between two keyed intervals."""

    key_a: str
    key_b: str
    overlap_start: date
    overlap_end: date | None  # None => open-ended overlap


def effective_end(end: date | None) -> date:
    """Map a nullable interval end to a concrete comparable date."""
    return OPEN_END if end is None else end


def is_valid_interval(start: date, end: date | None) -> bool:
    """Return ``False`` only for inverted bounds (end before start)."""
    return end is None or end >= start


def intervals_overlap(start_a: date, end_a: date | None, start_b: date, end_b: date | None) -> bool:
    """True when half-open ``[start, end)`` intervals intersect in time.

    Adjacent intervals (``end_a == start_b``) do NOT overlap. Zero-length
    intervals (``start == end``) and inverted bounds overlap nothing.
    """
    a_end = effective_end(end_a)
    b_end = effective_end(end_b)
    if start_a >= a_end or start_b >= b_end:
        return False
    return start_a < b_end and start_b < a_end


def intersection(
    start_a: date, end_a: date | None, start_b: date, end_b: date | None
) -> tuple[date, date | None] | None:
    """Return the intersecting sub-interval, or ``None`` when disjoint."""
    start = max(start_a, start_b)
    end = min(effective_end(end_a), effective_end(end_b))
    if start >= end:
        return None
    return (start, None if end == OPEN_END else end)


def interval_contains(start: date, end: date | None, day: date) -> bool:
    """True when ``day`` lies inside ``[start, end)``."""
    return start <= day < effective_end(end)


def normalize_interval_end(
    start: date, end: date | None, *, interval_end: str
) -> tuple[date, date | None]:
    """Convert a source interval end into the canonical exclusive convention.

    ``interval_end="exclusive"`` passes through; ``"inclusive"`` adds one day.
    Returns ``None`` end unchanged (open-ended). Inverted results are returned
    as-is for the caller to flag as ``DAT-002`` — never silently repaired.
    """
    if end is None or interval_end == "exclusive":
        return (start, end)
    return (start, end + timedelta(days=1))


def sort_intervals(items: Iterable[KeyedInterval]) -> list[KeyedInterval]:
    """Stable deterministic ordering: by start, then effective end, then key."""
    return sorted(items, key=lambda item: (item[1], effective_end(item[2]), item[0]))


def find_overlapping_pairs(items: Sequence[KeyedInterval]) -> list[OverlapPair]:
    """Detect all pairwise overlaps among keyed half-open intervals.

    Sweep-line over sorted starts: O(n log n) sorting plus O(n * active)
    comparisons. Zero-length intervals (``start == end``) overlap nothing.
    Open ends are treated as ``date.max``. Output order is deterministic:
    sorted by (start, key_a, key_b).
    """
    parsed = sort_intervals(items)
    active: list[tuple[date, date, str]] = []
    pairs: list[OverlapPair] = []
    for key, start, end in parsed:
        end_eff = effective_end(end)
        if end_eff <= start:
            continue
        active = [a for a in active if a[1] > start]
        for a_start, a_end, a_key in active:
            ov_start = max(a_start, start)
            ov_end = min(a_end, end_eff)
            pairs.append(
                OverlapPair(
                    key_a=a_key,
                    key_b=key,
                    overlap_start=ov_start,
                    overlap_end=None if ov_end == OPEN_END else ov_end,
                )
            )
        active.append((start, end_eff, key))
    pairs.sort(key=lambda p: (p.overlap_start, p.key_a, p.key_b))
    return pairs
