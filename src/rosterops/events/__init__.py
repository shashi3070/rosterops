"""Canonical event model: normalization, ledger identity, and window logic."""

from __future__ import annotations

from rosterops.events.ledger import (
    Event,
    EventLedger,
    EventStatus,
    ReconstructionWindow,
    build_fingerprint,
    empty_window,
)
from rosterops.events.normalize import EVENT_ROLE_TYPES, normalize_events
from rosterops.events.pipeline import build_ledger, window_for
from rosterops.events.reconcile import (
    dedupe_events,
    detect_same_date_conflicts,
    event_conflicts,
    filter_to_window,
)

__all__ = [
    "EVENT_ROLE_TYPES",
    "Event",
    "EventLedger",
    "EventStatus",
    "ReconstructionWindow",
    "build_fingerprint",
    "build_ledger",
    "dedupe_events",
    "detect_same_date_conflicts",
    "empty_window",
    "event_conflicts",
    "filter_to_window",
    "normalize_events",
    "window_for",
]
