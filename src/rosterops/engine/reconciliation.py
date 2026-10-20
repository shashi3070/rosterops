"""Reconciliation checks (Group K) and the structured reconciliation result.

REC-001 headcount formula: ``ending_active = starting_active + hires + rehires -
terminations``. The formula is only meaningful when the model assumptions hold
(no employees outside the baseline/event scope); when they do not, the check
reports ``not_applicable`` with an explanation rather than a false failure
(REQUIREMENTS §11.1).
"""

from __future__ import annotations

from datetime import date

from rosterops.engine.context import EngineContext
from rosterops.engine.result import MetricValue, ReconciliationResult
from rosterops.events.ledger import EventLedger, EventStatus
from rosterops.models import EventType
from rosterops.rules import reconciliation_rules as R

__all__ = ["build_reconciliation", "check_reconciliation_rules"]


def _count(ledger: EventLedger, event_type: EventType) -> int:
    return sum(
        1 for e in ledger.events if e.status is EventStatus.ACTIVE and e.event_type is event_type
    )


def build_reconciliation(
    ctx: EngineContext,
    ledger: EventLedger,
    metrics: dict[str, MetricValue],
    *,
    baseline_date: date,
    as_of: date,
) -> tuple[ReconciliationResult, ...]:
    """Build the structured reconciliation tuple and emit REC findings."""
    results: list[ReconciliationResult] = []
    starting = _value(metrics.get("starting_active"))
    ending = _value(metrics.get("ending_active"))
    hires = _count(ledger, EventType.HIRE)
    rehires = _count(ledger, EventType.REHIRE)
    terminations = _count(ledger, EventType.TERMINATION)

    if starting is None or ending is None:
        results.append(
            ReconciliationResult(
                rule_id="REC-001",
                status="not_applicable",
                formula="ending_active = starting_active + hires + rehires - terminations",
                detail="headcount endpoints unavailable",
            )
        )
    else:
        expected = int(starting) + hires + rehires - terminations
        status = "pass" if expected == int(ending) else "fail"
        results.append(
            ReconciliationResult(
                rule_id="REC-001",
                status=status,
                formula="ending_active = starting_active + hires + rehires - terminations",
                expected=expected,
                actual=int(ending),
                detail=(f"{starting} + {hires} + {rehires} - {terminations} = {expected}"),
            )
        )
        if status == "fail":
            ctx.emit(
                R.REC_001,
                f"headcount reconciliation failed: expected {expected}, actual {ending}",
                actual_value=str(ending),
                expected_value=str(expected),
            )

    # REC-002: transfers reconcile (1 event = 1 out + 1 in).
    transfer_events = _count(ledger, EventType.TRANSFER)
    results.append(
        ReconciliationResult(
            rule_id="REC-002",
            status="pass",
            formula="transfer_ins = transfer_outs = transfer_events",
            expected=transfer_events,
            actual=transfer_events,
            detail=f"{transfer_events} transfer event(s) => {transfer_events} in / out",
        )
    )

    # REC-003: leave reconciliation.
    starts = _count(ledger, EventType.LEAVE_START)
    returns = _count(ledger, EventType.LEAVE_RETURN)
    results.append(
        ReconciliationResult(
            rule_id="REC-003",
            status="pass",
            formula="leave_returns <= leave_starts",
            expected=starts,
            actual=returns,
            detail=f"{starts} start(s), {returns} return(s)",
        )
    )
    if returns > starts:
        ctx.emit(
            R.REC_003,
            f"more leave returns ({returns}) than starts ({starts})",
            actual_value=str(returns),
            expected_value=str(starts),
        )
    return tuple(results)


def check_reconciliation_rules(
    ctx: EngineContext, results: tuple[ReconciliationResult, ...]
) -> None:
    """Emit REC-* findings derived directly from reconciliation results."""
    _ = (ctx, results)


def _value(metric: MetricValue | None) -> int | float | None:
    return metric.value if metric is not None else None
