"""Unit tests for the canonical event model (Phase 3)."""

from __future__ import annotations

from datetime import date

import polars as pl

from rosterops.config import RosterConfig
from rosterops.events import (
    EVENT_ROLE_TYPES,
    EventStatus,
    build_fingerprint,
    build_ledger,
    dedupe_events,
    detect_same_date_conflicts,
    empty_window,
    event_conflicts,
    filter_to_window,
    normalize_events,
    window_for,
)
from rosterops.events.ledger import Event, EventLedger, ReconstructionWindow
from rosterops.io.ingest import IngestedInput
from rosterops.models import EventType, Lineage, TerminationDateSemantics

_LAST_WORKING = TerminationDateSemantics.LAST_WORKING_DAY_INCLUSIVE


def _ingested(role: str, rows: list[dict[str, object]]) -> IngestedInput:
    frame = pl.DataFrame(rows, infer_schema_length=None)
    return IngestedInput(role=role, frame=frame, findings=(), source_file=f"{role}.csv")


def _event(
    event_type: EventType,
    employee_id: str = "E1",
    effective: date | None = date(2026, 1, 10),
    **kwargs: object,
) -> Event:
    return Event(
        event_type=event_type,
        employee_id=employee_id,
        effective_date=effective,
        fingerprint=build_fingerprint(event_type, employee_id, effective),
        **kwargs,  # type: ignore[arg-type]
    )


def test_all_event_roles_map_to_known_types() -> None:
    assert set(EVENT_ROLE_TYPES.values()) == set(EventType)


def test_transfer_normalization_preserves_payload_and_lineage() -> None:
    ledger = normalize_events(
        _ingested(
            "transfers",
            [
                {
                    "event_id": "T-1",
                    "employee_id": "007",
                    "effective_date": date(2026, 2, 1),
                    "from_territory_id": "T100",
                    "to_territory_id": "T200",
                    "source_row": 5,
                }
            ],
        ),
        termination_semantics=_LAST_WORKING,
    )
    assert len(ledger) == 1
    event = ledger.events[0]
    assert event.event_type is EventType.TRANSFER
    assert event.employee_id == "007"  # leading zeros preserved
    assert event.from_territory_id == "T100"
    assert event.to_territory_id == "T200"
    assert event.namespaced_id == "transfers:T-1"
    assert event.lineage.source_row == 5
    assert event.status is EventStatus.ACTIVE


def test_termination_semantics_conversion_is_auditable() -> None:
    stated = date(2026, 3, 31)
    inclusive = normalize_events(
        _ingested(
            "terminations",
            [{"event_id": "X", "employee_id": "E1", "effective_date": stated}],
        ),
        termination_semantics=TerminationDateSemantics.LAST_WORKING_DAY_INCLUSIVE,
    ).events[0]
    assert inclusive.effective_date == stated
    assert inclusive.employment_end_exclusive == date(2026, 4, 1)

    first_inactive = normalize_events(
        _ingested(
            "terminations",
            [{"event_id": "Y", "employee_id": "E1", "effective_date": stated}],
        ),
        termination_semantics=TerminationDateSemantics.FIRST_INACTIVE_DAY,
    ).events[0]
    assert first_inactive.employment_end_exclusive == stated

    explicit = normalize_events(
        _ingested(
            "terminations",
            [{"event_id": "Z", "employee_id": "E1", "effective_date": stated}],
        ),
        termination_semantics=TerminationDateSemantics.EXPLICIT_EFFECTIVE_END,
    ).events[0]
    assert explicit.employment_end_exclusive == stated


def test_leave_normalization_uses_leave_start_date() -> None:
    ledger = normalize_events(
        _ingested(
            "leaves",
            [
                {
                    "event_id": "L-1",
                    "employee_id": "E1",
                    "leave_start_date": date(2026, 5, 1),
                    "leave_end_date": date(2026, 6, 1),
                }
            ],
        ),
        termination_semantics=_LAST_WORKING,
    )
    event = ledger.events[0]
    assert event.event_type is EventType.LEAVE_START
    assert event.leave_start_date == date(2026, 5, 1)
    assert event.leave_end_date == date(2026, 6, 1)


def test_missing_employee_id_marks_invalid_with_finding() -> None:
    ledger = normalize_events(
        _ingested("transfers", [{"event_id": "T-9", "effective_date": date(2026, 1, 1)}]),
        termination_semantics=_LAST_WORKING,
    )
    assert ledger.events[0].status is EventStatus.INVALID
    assert any(f.rule_id == "DAT-001" for f in ledger.findings)


def test_duplicate_event_id_within_namespace_flags_id_002() -> None:
    ledger = normalize_events(
        _ingested(
            "transfers",
            [
                {"event_id": "DUP", "employee_id": "E1", "effective_date": date(2026, 1, 1)},
                {"event_id": "DUP", "employee_id": "E2", "effective_date": date(2026, 1, 2)},
            ],
        ),
        termination_semantics=_LAST_WORKING,
    )
    id_002 = [f for f in ledger.findings if f.rule_id == "ID-002"]
    assert len(id_002) == 1
    assert id_002[0].event_id == "DUP"


def test_duplicate_promotion_flags_pro_003_and_rec_006() -> None:
    ledger = normalize_events(
        _ingested(
            "promotions",
            [
                {
                    "event_id": "P-1",
                    "employee_id": "E1",
                    "effective_date": date(2026, 1, 1),
                    "new_role_code": "SENIOR_REP",
                },
                {
                    "event_id": "P-2",
                    "employee_id": "E1",
                    "effective_date": date(2026, 1, 1),
                    "new_role_code": "SENIOR_REP",
                },
            ],
        ),
        termination_semantics=_LAST_WORKING,
    )
    dedupe_events(ledger)
    assert any(f.rule_id == "PRO-003" for f in ledger.findings)
    assert any(f.rule_id == "REC-006" for f in ledger.findings)


def test_duplicate_transfer_flags_rec_006_not_pro_003() -> None:
    ledger = normalize_events(
        _ingested(
            "transfers",
            [
                {
                    "event_id": "T-1",
                    "employee_id": "E1",
                    "effective_date": date(2026, 1, 1),
                    "to_territory_id": "T2",
                },
                {
                    "event_id": "T-2",
                    "employee_id": "E1",
                    "effective_date": date(2026, 1, 1),
                    "to_territory_id": "T2",
                },
            ],
        ),
        termination_semantics=_LAST_WORKING,
    )
    dedupe_events(ledger)
    assert any(f.rule_id == "REC-006" for f in ledger.findings)
    assert not any(f.rule_id == "PRO-003" for f in ledger.findings)


def test_dat008_fires_when_explicit_end_disagrees() -> None:
    ledger = normalize_events(
        _ingested(
            "terminations",
            [
                {
                    "event_id": "X",
                    "employee_id": "E1",
                    "effective_date": date(2026, 3, 31),
                    "employment_end_exclusive": date(2026, 3, 30),
                }
            ],
        ),
        termination_semantics=TerminationDateSemantics.LAST_WORKING_DAY_INCLUSIVE,
    )
    assert any(f.rule_id == "DAT-008" for f in ledger.findings)


def test_dat008_silent_when_explicit_end_agrees() -> None:
    ledger = normalize_events(
        _ingested(
            "terminations",
            [
                {
                    "event_id": "X",
                    "employee_id": "E1",
                    "effective_date": date(2026, 3, 31),
                    "employment_end_exclusive": date(2026, 4, 1),
                }
            ],
        ),
        termination_semantics=TerminationDateSemantics.LAST_WORKING_DAY_INCLUSIVE,
    )
    assert not any(f.rule_id == "DAT-008" for f in ledger.findings)


def test_conflicting_transfer_emits_trf_006() -> None:
    ledger = EventLedger(
        events=[
            _event(EventType.TRANSFER, employee_id="E1", to_territory_id="T2"),
            _event(EventType.TRANSFER, employee_id="E1", to_territory_id="T3"),
        ]
    )
    detect_same_date_conflicts(ledger, resolution_policy=None)
    assert any(f.rule_id == "TRF-006" for f in ledger.findings)


def test_termination_transfer_conflict_emits_trf_006() -> None:
    ledger = EventLedger(
        events=[
            _event(EventType.TRANSFER, employee_id="E1", to_territory_id="T2"),
            _event(EventType.TERMINATION, employee_id="E1"),
        ]
    )
    detect_same_date_conflicts(ledger, resolution_policy=None)
    assert any(f.rule_id == "TRF-006" for f in ledger.findings)


def test_fingerprint_is_source_independent() -> None:
    a = build_fingerprint(EventType.TRANSFER, "E1", date(2026, 1, 1), to_territory_id="T2")
    b = build_fingerprint(EventType.TRANSFER, "E1", date(2026, 1, 1), to_territory_id="T2")
    c = build_fingerprint(EventType.TRANSFER, "E1", date(2026, 1, 1), to_territory_id="T3")
    assert a == b
    assert a != c


def test_dedupe_across_files_marks_later_occurrence() -> None:
    ledger = EventLedger(
        events=[
            _event(EventType.TRANSFER, to_territory_id="T2", lineage=Lineage(source_file="w1.csv")),
            _event(EventType.TRANSFER, to_territory_id="T2", lineage=Lineage(source_file="w2.csv")),
        ]
    )
    dedupe_events(ledger)
    assert ledger.events[0].status is EventStatus.ACTIVE
    assert ledger.events[1].status is EventStatus.DUPLICATE
    assert any(f.rule_id == "ID-007" for f in ledger.findings)


def test_window_filter_marks_on_or_before_baseline_and_after_as_of() -> None:
    window = ReconstructionWindow(baseline_date=date(2026, 1, 1), as_of=date(2026, 3, 1))
    ledger = EventLedger(
        events=[
            _event(EventType.TRANSFER, effective=date(2026, 1, 1)),  # on baseline
            _event(EventType.TRANSFER, effective=date(2026, 2, 1)),  # in window
            _event(EventType.TRANSFER, effective=date(2026, 4, 1)),  # after as_of
        ]
    )
    filter_to_window(ledger, window)
    statuses = [e.status for e in ledger.events]
    assert statuses == [
        EventStatus.OUT_OF_WINDOW,
        EventStatus.ACTIVE,
        EventStatus.OUT_OF_WINDOW,
    ]
    assert sum(1 for f in ledger.findings if f.rule_id == "DAT-006") == 2


def test_empty_window_rejects_everything() -> None:
    assert not empty_window().contains(date(2026, 1, 1))


def test_event_conflicts_rules() -> None:
    t1 = _event(EventType.TRANSFER, to_territory_id="T2")
    t2 = _event(EventType.TRANSFER, to_territory_id="T3")
    t3 = _event(EventType.TRANSFER, to_territory_id="T2")
    term = _event(EventType.TERMINATION)
    pro1 = _event(EventType.PROMOTION, new_role_code="R2")
    pro2 = _event(EventType.PROMOTION, new_role_code="R3")

    assert event_conflicts(t1, t2)  # different destinations
    assert not event_conflicts(t1, t3)  # same destination
    assert event_conflicts(term, t1)  # termination + transfer
    assert event_conflicts(pro1, pro2)  # conflicting promotions
    assert not event_conflicts(pro1, _event(EventType.PROMOTION, new_role_code="R2"))


def test_same_date_conflicts_flagged_without_policy() -> None:
    ledger = EventLedger(
        events=[
            _event(EventType.TRANSFER, employee_id="E1", to_territory_id="T2"),
            _event(EventType.TERMINATION, employee_id="E1"),
        ]
    )
    detect_same_date_conflicts(ledger, resolution_policy=None)
    dat_007 = [f for f in ledger.findings if f.rule_id == "DAT-007"]
    assert len(dat_007) == 1
    assert "no resolution policy" in dat_007[0].message


def test_same_date_conflicts_note_policy_when_configured() -> None:
    ledger = EventLedger(
        events=[
            _event(EventType.TRANSFER, employee_id="E1", to_territory_id="T2"),
            _event(EventType.TERMINATION, employee_id="E1"),
        ]
    )
    detect_same_date_conflicts(ledger, resolution_policy="effective_then_source")
    dat_007 = [f for f in ledger.findings if f.rule_id == "DAT-007"]
    assert len(dat_007) == 1
    assert "effective_then_source" in dat_007[0].message


def test_same_date_non_conflicting_events_not_flagged() -> None:
    ledger = EventLedger(
        events=[
            _event(EventType.TRANSFER, employee_id="E1", to_territory_id="T2"),
            _event(EventType.PROMOTION, employee_id="E1", new_role_code="R9"),
        ]
    )
    detect_same_date_conflicts(ledger, resolution_policy=None)
    assert not any(f.rule_id == "DAT-007" for f in ledger.findings)


def test_invalid_events_skipped_by_conflict_and_window_checks() -> None:
    ledger = EventLedger(
        events=[
            _event(EventType.TRANSFER, employee_id="E1", to_territory_id="T2"),
            _event(
                EventType.TRANSFER,
                employee_id="E1",
                to_territory_id="T3",
                status=EventStatus.INVALID,
            ),
        ]
    )
    detect_same_date_conflicts(ledger, resolution_policy=None)
    assert not any(f.rule_id == "DAT-007" for f in ledger.findings)


def test_build_ledger_end_to_end_dedupes_windows_and_flags() -> None:
    config = RosterConfig()
    ingested = {
        "transfers": IngestedInput(
            role="transfers",
            frame=pl.DataFrame(
                [
                    {
                        "event_id": "T-1",
                        "employee_id": "E1",
                        "effective_date": date(2026, 6, 1),
                        "to_territory_id": "T2",
                        "source_row": 2,
                    },
                    {
                        "event_id": "T-2",
                        "employee_id": "E1",
                        "effective_date": date(2026, 6, 1),
                        "to_territory_id": "T3",
                        "source_row": 3,
                    },
                ],
                infer_schema_length=None,
            ),
            findings=(),
            source_file="week1.csv",
        ),
        "terminations": IngestedInput(
            role="terminations",
            frame=pl.DataFrame(
                [
                    {
                        "event_id": "X-1",
                        "employee_id": "E2",
                        "effective_date": date(2026, 1, 1),  # on baseline -> DAT-006
                    }
                ],
                infer_schema_length=None,
            ),
            findings=(),
            source_file="term.csv",
        ),
    }
    ledger = build_ledger(config, ingested, baseline_date=date(2026, 1, 1), as_of=date(2026, 7, 1))
    # Two conflicting transfers on the same date -> DAT-007.
    assert any(f.rule_id == "DAT-007" for f in ledger.findings)
    # Baseline-dated termination is out of window -> DAT-006.
    assert any(f.rule_id == "DAT-006" for f in ledger.findings)
    assert len(ledger.active_events()) == 0  # conflicts blocked


def test_window_for_uses_config_baseline_semantics() -> None:
    config = RosterConfig()
    window = window_for(config, baseline_date=date(2026, 1, 1), as_of=date(2026, 2, 1))
    assert window.baseline_date == date(2026, 1, 1)
    assert window.baseline_includes_effective_date
