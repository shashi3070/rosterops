"""Movement metrics and availability (REQUIREMENTS §9, §10).

Movement metrics (transfers, promotions, leave starts/returns, terminations,
hires/rehires) are computed from the event ledger, never inferred from a
snapshot. In Mode B they are returned as ``not_available`` with a reason
(REQUIREMENTS §3.2) — the engine never fabricates event counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from rosterops.engine.result import MetricValue
from rosterops.engine.state import BaselineState
from rosterops.events.ledger import EventLedger, EventStatus
from rosterops.models import EventType

__all__ = [
    "MovementMetrics",
    "compute_movement_metrics",
    "snapshot_metric_availability",
]

#: Movement metrics that cannot be derived from a single snapshot.
_UNAVAILABLE_IN_SNAPSHOT: tuple[tuple[str, str], ...] = (
    ("transfer_events", "transfers are historical events not present in a snapshot"),
    ("transfer_ins", "transfer ins are historical events not present in a snapshot"),
    ("transfer_outs", "transfer outs are historical events not present in a snapshot"),
    ("promotion_events", "promotions are historical events not present in a snapshot"),
    ("leave_starts", "leave starts are historical events not present in a snapshot"),
    ("leave_returns", "leave returns are historical events not present in a snapshot"),
    ("termination_events", "terminations are historical events not present in a snapshot"),
    ("hire_events", "hires are historical events not present in a snapshot"),
    ("rehire_events", "rehires are historical events not present in a snapshot"),
)


@dataclass(frozen=True, slots=True)
class MovementMetrics:
    """Movement metric set; each value carries availability + reason."""

    values: dict[str, MetricValue]

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {key: mv.to_dict() for key, mv in self.values.items()}

    def get(self, key: str) -> MetricValue:
        return self.values[key]


def compute_movement_metrics(
    ledger: EventLedger,
    state: BaselineState,
    *,
    baseline_date: date,
    as_of: date,
) -> MovementMetrics:
    """Compute Mode A movement metrics from the ledger and reconstructed state."""
    active = [e for e in ledger.events if e.status is EventStatus.ACTIVE]
    by_type: dict[EventType, int] = {}
    for event in active:
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1

    transfer_events = by_type.get(EventType.TRANSFER, 0)
    values: dict[str, MetricValue] = {
        "starting_active": MetricValue.available(len(state.active_employee_ids(baseline_date))),
        "ending_active": MetricValue.available(len(state.active_employee_ids(as_of))),
        "transfer_events": MetricValue.available(transfer_events),
        "transfer_ins": MetricValue.available(transfer_events),
        "transfer_outs": MetricValue.available(transfer_events),
        "promotion_events": MetricValue.available(by_type.get(EventType.PROMOTION, 0)),
        "leave_starts": MetricValue.available(by_type.get(EventType.LEAVE_START, 0)),
        "leave_returns": MetricValue.available(by_type.get(EventType.LEAVE_RETURN, 0)),
        "termination_events": MetricValue.available(by_type.get(EventType.TERMINATION, 0)),
        "hire_events": MetricValue.available(by_type.get(EventType.HIRE, 0)),
        "rehire_events": MetricValue.available(by_type.get(EventType.REHIRE, 0)),
        "on_leave_at_cutoff": MetricValue.available(
            sum(1 for eid in state.employee_ids() if state.on_leave(eid, as_of))
        ),
    }
    return MovementMetrics(values=values)


def snapshot_metric_availability(state: BaselineState, *, as_of: date) -> MovementMetrics:
    """Mode B metrics: headcount is derivable; movements are ``not_available``."""
    values: dict[str, MetricValue] = {
        "ending_active": MetricValue.available(len(state.active_employee_ids(as_of))),
        "starting_active": MetricValue.not_available(
            "a single snapshot has no baseline to compare against"
        ),
    }
    for key, reason in _UNAVAILABLE_IN_SNAPSHOT:
        values[key] = MetricValue.not_available(reason)
    values["on_leave_at_cutoff"] = MetricValue.not_available(
        "on-leave status is not derivable from a snapshot without leave events"
    )
    return MovementMetrics(values=values)
