"""Top-level engine orchestration for both modes (REQUIREMENTS §3, §6.3).

Mode A (``process``): baseline + events -> reconstructed roster as of ``as_of``.
Mode B (``validate``): single snapshot -> validated snapshot with honest metric
limits.

The orchestrator wires: load -> baseline state -> grain validation -> ledger +
event application (Mode A only) -> rule execution -> metrics/vacancies/
reconciliation -> materialization -> deterministic finding ordering -> metadata.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

import polars as pl

from rosterops.config import RosterConfig
from rosterops.domain.dates import parse_date
from rosterops.engine.baseline import build_baseline_state, validate_grain
from rosterops.engine.context import EngineContext
from rosterops.engine.lifecycle_rules import run_lifecycle_rules
from rosterops.engine.load import SourceSpec, load_inputs
from rosterops.engine.metrics import compute_movement_metrics, snapshot_metric_availability
from rosterops.engine.reconciliation import build_reconciliation
from rosterops.engine.reconstruction import (
    apply_events,
    materialize_assignments,
    materialize_events_frame,
)
from rosterops.engine.result import RosterResult, RunMetadata
from rosterops.engine.roster import materialize_roster
from rosterops.engine.snapshot_rules import run_snapshot_rules, run_state_rules
from rosterops.engine.vacancies import compute_vacancies
from rosterops.events.ledger import EventLedger, EventStatus
from rosterops.events.pipeline import build_ledger
from rosterops.exceptions import InputError
from rosterops.models import EventType
from rosterops.rules.base import sort_and_number
from rosterops.version import __version__

__all__ = ["process_run", "validate_run"]


def process_run(
    config: RosterConfig,
    sources: dict[str, SourceSpec],
    *,
    baseline_date: str | date,
    as_of: str | date,
) -> RosterResult:
    """Execute a Mode A run (baseline + events -> as-of reconstruction)."""
    baseline_dt = _require_date(baseline_date, "baseline_date")
    as_of_dt = _require_date(as_of, "as_of")

    loaded = load_inputs(config, sources)
    ctx = EngineContext(config=config, mode="process", as_of=as_of_dt, baseline_date=baseline_dt)
    ctx.findings.extend(loaded.findings)
    ctx.frames = loaded.frames

    baseline_frame = loaded.frames.get("baseline")
    if baseline_frame is None:
        raise InputError("mode A requires a baseline input")

    ctx.findings.extend(validate_grain(baseline_frame, config))
    ctx.state = build_baseline_state(baseline_frame)

    ledger = build_ledger(
        config,
        loaded.ingested,
        baseline_date=baseline_dt,
        as_of=as_of_dt,
    )
    ctx.findings.extend(ledger.findings)
    applied_order = apply_events(ctx, ledger)

    # Snapshot-style structural rules still apply to the reconstructed state.
    _run_process_state_rules(ctx, ledger)

    metrics = compute_movement_metrics(ledger, ctx.state, baseline_date=baseline_dt, as_of=as_of_dt)
    vacancies = compute_vacancies(
        ctx.state,
        ctx.frames.get("territories"),
        config,
        as_of=as_of_dt,
        event_kinds=_vacancy_kinds(ctx, ledger),
    )
    reconciliation = build_reconciliation(
        ctx, ledger, metrics.values, baseline_date=baseline_dt, as_of=as_of_dt
    )

    findings = tuple(sort_and_number(ctx.findings))
    result = RosterResult(
        mode="process",
        as_of=as_of_dt.isoformat(),
        baseline_date=baseline_dt.isoformat(),
        roster=materialize_roster(ctx, as_of_dt),
        assignments=materialize_assignments(ctx),
        events=materialize_events_frame(ledger),
        issues=pl.DataFrame(),
        vacancies=vacancies,
        summary={
            "grain": config.data.grain.value,
            "metrics": metrics.to_dict(),
            "active_employees": len(ctx.state.active_employee_ids(as_of_dt)),
        },
        reconciliation=reconciliation,
        metadata=_metadata(
            config,
            mode="process",
            loaded=loaded,
            as_of=as_of_dt.isoformat(),
            baseline_date=baseline_dt.isoformat(),
            applied_order=applied_order,
        ),
        findings=findings,
    )
    result.issues = result.issues_frame(findings)
    return result


def validate_run(
    config: RosterConfig,
    sources: dict[str, SourceSpec],
    *,
    as_of: str | date,
) -> RosterResult:
    """Execute a Mode B run (single snapshot validation)."""
    as_of_dt = _require_date(as_of, "as_of")
    loaded = load_inputs(config, sources)
    ctx = EngineContext(config=config, mode="snapshot", as_of=as_of_dt, baseline_date=None)
    ctx.findings.extend(loaded.findings)
    ctx.frames = loaded.frames

    snapshot = loaded.frames.get("snapshot")
    if snapshot is None:
        snapshot = loaded.frames.get("baseline")
    if snapshot is None:
        raise InputError("mode B requires a snapshot input")

    ctx.findings.extend(validate_grain(snapshot, config))
    ctx.state = build_baseline_state(snapshot)
    run_snapshot_rules(ctx)

    metrics = snapshot_metric_availability(ctx.state, as_of=as_of_dt)
    vacancies = compute_vacancies(ctx.state, ctx.frames.get("territories"), config, as_of=as_of_dt)

    findings = tuple(sort_and_number(ctx.findings))
    result = RosterResult(
        mode="snapshot",
        as_of=as_of_dt.isoformat(),
        roster=materialize_roster(ctx, as_of_dt),
        assignments=materialize_assignments(ctx),
        issues=pl.DataFrame(),
        vacancies=vacancies,
        summary={
            "grain": config.data.grain.value,
            "metrics": metrics.to_dict(),
            "active_employees": len(ctx.state.active_employee_ids(as_of_dt)),
        },
        reconciliation=(),
        metadata=_metadata(
            config, mode="snapshot", loaded=loaded, as_of=as_of_dt.isoformat(), baseline_date=None
        ),
        findings=findings,
    )
    result.issues = result.issues_frame(findings)
    return result


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _require_date(value: str | date, name: str) -> date:
    if isinstance(value, date):
        return value
    parsed = parse_date(value)
    if parsed is None:
        raise InputError(f"{name} is not a valid ISO date: {value!r}")
    return parsed


def _run_process_state_rules(ctx: EngineContext, ledger: EventLedger) -> None:
    """Apply state-based structural rules to the reconstructed state."""
    run_state_rules(ctx)
    run_lifecycle_rules(ctx, ledger)


def _vacancy_kinds(ctx: EngineContext, ledger: EventLedger) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for event in ledger.events:
        if event.status is not EventStatus.ACTIVE:
            continue
        if event.event_type is EventType.TRANSFER and event.from_territory_id:
            kinds.setdefault(event.from_territory_id, "after_transfer")
        if event.event_type is EventType.TERMINATION:
            for a in ctx.state.assignments.get(event.employee_id, []):
                if a.territory_id:
                    kinds.setdefault(a.territory_id, "after_termination")
    return kinds


def _metadata(
    config: RosterConfig,
    *,
    mode: str,
    loaded: object,
    as_of: str,
    baseline_date: str | None,
    applied_order: tuple[str, ...] = (),
) -> RunMetadata:
    resolved = config.resolved_dict()
    config_hash = hashlib.sha256(repr(sorted(resolved.items())).encode("utf-8")).hexdigest()[:16]
    input_files = tuple(getattr(loaded, "input_files", ()))
    conflict_policy = config.policies.events.resolve_conflicting_same_date_events
    policy = conflict_policy if isinstance(conflict_policy, str) else None
    return RunMetadata(
        tool_version=__version__,
        mode=mode,
        grain=config.data.grain.value,
        as_of=as_of,
        baseline_date=baseline_date,
        config_hash=config_hash,
        input_files=input_files,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        applied_event_order=applied_order,
        conflict_policy=policy,
    )
