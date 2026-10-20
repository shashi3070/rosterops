"""Build the canonical event ledger for a process run.

Orchestrates normalization and post-processing per REQUIREMENTS §6.3:

1. Normalize each ingested event role into :class:`Event` rows.
2. Dedupe across files by fingerprint (``ID-007``).
3. Filter to the ``(baseline_date, as_of]`` window (``DAT-006``).
4. Detect same-date conflicts (``DAT-007``).

Only the event roles (transfers, promotions, terminations, leaves, returns,
hires, rehires, coverage) participate; master/baseline roles are ignored here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from rosterops.config import RosterConfig
from rosterops.events.ledger import EventLedger, ReconstructionWindow
from rosterops.events.normalize import EVENT_ROLE_TYPES, normalize_events
from rosterops.events.reconcile import (
    dedupe_events,
    detect_same_date_conflicts,
    filter_to_window,
)
from rosterops.io.ingest import IngestedInput

__all__ = ["build_ledger", "window_for"]


def window_for(
    config: RosterConfig,
    *,
    baseline_date: date,
    as_of: date,
) -> ReconstructionWindow:
    """Construct the reconstruction window from configuration and dates."""
    return ReconstructionWindow(
        baseline_date=baseline_date,
        as_of=as_of,
        baseline_includes_effective_date=config.dates.baseline_includes_effective_date,
    )


def build_ledger(
    config: RosterConfig,
    ingested: Mapping[str, IngestedInput],
    *,
    baseline_date: date,
    as_of: date,
) -> EventLedger:
    """Build, dedupe, window-filter, and conflict-check the canonical ledger."""
    ledger = EventLedger()
    semantics = config.dates.termination_date_semantics

    for role in EVENT_ROLE_TYPES:
        source = ingested.get(role)
        if source is None:
            continue
        role_ledger = normalize_events(source, termination_semantics=semantics)
        ledger.events.extend(role_ledger.events)
        ledger.findings.extend(role_ledger.findings)

    dedupe_events(ledger)
    if config.policies.events.reject_events_on_or_before_baseline_date:
        filter_to_window(ledger, window_for(config, baseline_date=baseline_date, as_of=as_of))
    detect_same_date_conflicts(
        ledger,
        resolution_policy=_resolution_policy(config),
    )
    return ledger


def _resolution_policy(config: RosterConfig) -> str | None:
    value = config.policies.events.resolve_conflicting_same_date_events
    if isinstance(value, str):
        return value
    return None
