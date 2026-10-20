"""Date parsing and effective-date semantics.

Covers scalar date parsing under configured formats, termination-date
semantics conversion (``DAT-008`` territory), and reconstruction-window
filtering of events relative to the baseline cutoff.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from rosterops.models import TerminationDateSemantics

__all__ = [
    "DEFAULT_DATE_FORMATS",
    "employment_exclusive_end",
    "event_in_reconstruction_window",
    "is_employed_on",
    "parse_date",
]

DEFAULT_DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d",)


def parse_date(value: object, formats: tuple[str, ...] | list[str] | None = None) -> date | None:
    """Parse ``value`` into a ``date`` using the configured formats in order.

    Returns ``None`` when the value cannot be parsed — callers turn failures
    into ``SCH-002``/``DAT-001`` findings; rows are never silently dropped.
    Supported inputs: ``date``, ``datetime`` (tz-aware values are converted to
    UTC before taking the date), and ``str`` (whitespace-trimmed, tried
    against each format). Everything else returns ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).date()
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in formats or DEFAULT_DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None
    return None


def employment_exclusive_end(
    stated: date | None, semantics: TerminationDateSemantics
) -> date | None:
    """Convert a source termination date to the canonical exclusive interval end.

    - ``last_working_day_inclusive``: active through the stated date, so the
      first inactive day is stated + 1.
    - ``first_inactive_day``: inactive from the stated date, so the exclusive
      end is the stated date.
    - ``explicit_effective_end``: the stated date is already the exclusive end.
    """
    if stated is None:
        return None
    if semantics is TerminationDateSemantics.LAST_WORKING_DAY_INCLUSIVE:
        return stated + timedelta(days=1)
    return stated


def is_employed_on(
    stated_termination: date | None,
    semantics: TerminationDateSemantics,
    query: date,
) -> bool:
    """True when employment has not ended on ``query`` given termination semantics."""
    end = employment_exclusive_end(stated_termination, semantics)
    if end is None:
        return True
    return query < end


def event_in_reconstruction_window(
    effective: date | None,
    baseline_date: date,
    as_of: date,
    *,
    baseline_includes_effective_date: bool,
) -> bool:
    """Decide whether an event applies to the ``(baseline_date, as_of]`` window.

    When ``baseline_includes_effective_date`` is true, events dated exactly on
    the baseline date are already reflected in the baseline and must be
    excluded (``DAT-006``); otherwise the window starts at the baseline date
    inclusive. Events after ``as_of`` are future-dated and excluded. An
    unparseable (``None``) effective date never applies.
    """
    if effective is None:
        return False
    if baseline_includes_effective_date:
        if effective <= baseline_date:
            return False
    elif effective < baseline_date:
        return False
    return effective <= as_of
