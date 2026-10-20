from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from rosterops.domain.dates import (
    DEFAULT_DATE_FORMATS,
    employment_exclusive_end,
    event_in_reconstruction_window,
    is_employed_on,
    parse_date,
)
from rosterops.models import TerminationDateSemantics as Sem

D = date


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-31", D(2026, 10, 31)),
        ("  2026-10-31  ", D(2026, 10, 31)),
        ("", None),
        ("   ", None),
        ("31/10/2026", D(2026, 10, 31)),
        ("2026/10/31", D(2026, 10, 31)),
        ("31.10.2026", D(2026, 10, 31)),
        ("20261031", D(2026, 10, 31)),
        ("31 Oct 2026", D(2026, 10, 31)),
        ("2026-13-45", None),
        ("not-a-date", None),
        (None, None),
        (True, None),
        (12345, None),
        (D(2026, 1, 2), D(2026, 1, 2)),
        (datetime(2026, 10, 31, 23, 59), D(2026, 10, 31)),
        (datetime(2026, 10, 31, 1, 0, tzinfo=timezone.utc), D(2026, 10, 31)),
    ],
)
def test_parse_date(raw: object, expected: date | None) -> None:
    assert parse_date(raw) == expected


def test_parse_date_format_order_and_custom_formats() -> None:
    formats = ("%d/%m/%Y", "%Y-%m-%d")
    assert parse_date("05/10/2026", formats) == D(2026, 10, 5)
    # First matching format wins.
    assert parse_date("2026-10-05", formats) == D(2026, 10, 5)
    assert DEFAULT_DATE_FORMATS[0] == "%Y-%m-%d"


def test_parse_date_offset_timezone_converted_to_utc() -> None:
    late = datetime(2026, 11, 1, 0, 30, tzinfo=timezone(timedelta(hours=2)))
    # 2026-11-01 00:30 +02:00 == 2026-10-31 22:30 UTC
    assert parse_date(late) == D(2026, 10, 31)


@pytest.mark.parametrize(
    ("semantics", "expected_end"),
    [
        (Sem.LAST_WORKING_DAY_INCLUSIVE, D(2026, 10, 21)),
        (Sem.FIRST_INACTIVE_DAY, D(2026, 10, 20)),
        (Sem.EXPLICIT_EFFECTIVE_END, D(2026, 10, 20)),
    ],
)
def test_termination_exclusive_end(semantics: Sem, expected_end: date) -> None:
    assert employment_exclusive_end(D(2026, 10, 20), semantics) == expected_end


def test_termination_none_means_open() -> None:
    for semantics in Sem:
        assert employment_exclusive_end(None, semantics) is None
        assert is_employed_on(None, semantics, D(2030, 1, 1)) is True


def test_is_employed_on_edges() -> None:
    stated = D(2026, 10, 20)
    inclusive = Sem.LAST_WORKING_DAY_INCLUSIVE
    # Active through the last working day, inactive the next day.
    assert is_employed_on(stated, inclusive, D(2026, 10, 20)) is True
    assert is_employed_on(stated, inclusive, D(2026, 10, 21)) is False

    first_inactive = Sem.FIRST_INACTIVE_DAY
    assert is_employed_on(stated, first_inactive, D(2026, 10, 19)) is True
    assert is_employed_on(stated, first_inactive, D(2026, 10, 20)) is False


def test_reconstruction_window_excludes_events_on_or_before_baseline() -> None:
    baseline, as_of = D(2026, 9, 30), D(2026, 10, 31)
    kwargs = {"baseline_date": baseline, "as_of": as_of, "baseline_includes_effective_date": True}
    assert event_in_reconstruction_window(D(2026, 9, 30), **kwargs) is False  # already in baseline
    assert event_in_reconstruction_window(D(2026, 9, 29), **kwargs) is False
    assert event_in_reconstruction_window(D(2026, 10, 1), **kwargs) is True
    assert event_in_reconstruction_window(D(2026, 10, 31), **kwargs) is True  # as_of inclusive
    assert event_in_reconstruction_window(D(2026, 11, 1), **kwargs) is False  # future
    assert event_in_reconstruction_window(None, **kwargs) is False


def test_reconstruction_window_when_baseline_excludes_its_own_date() -> None:
    kwargs = {
        "baseline_date": D(2026, 9, 30),
        "as_of": D(2026, 10, 31),
        "baseline_includes_effective_date": False,
    }
    assert event_in_reconstruction_window(D(2026, 9, 30), **kwargs) is True
    assert event_in_reconstruction_window(D(2026, 9, 29), **kwargs) is False
