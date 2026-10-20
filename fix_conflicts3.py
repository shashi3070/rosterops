with open('src/rosterops/events/reconcile.py') as f:
    c = f.read()
old = '''        if any(ledger.events[i].event_type is EventType.TRANSFER for i in involved):
            ledger.add_finding(
                Finding.from_spec(
                    TRF_006,
                    f"conflicting transfers for employee {employee_id!r} on "
                    f"{_iso(reference)}{policy_note}",
                    employee_id=employee_id,
                    effective_date=reference,
                    source_file=ledger.events[involved[0]].lineage.source_file,
                    source_row=ledger.events[involved[0]].lineage.source_row,
                )
            )


def _conflicting_pairs'''
new = '''        if any(ledger.events[i].event_type is EventType.TRANSFER for i in involved):
            ledger.add_finding(
                Finding.from_spec(
                    TRF_006,
                    f"conflicting transfers for employee {employee_id!r} on "
                    f"{_iso(reference)}{policy_note}",
                    employee_id=employee_id,
                    effective_date=reference,
                    source_file=ledger.events[involved[0]].lineage.source_file,
                    source_row=ledger.events[involved[0]].lineage.source_row,
                )
            )
        for idx in involved:
            ev = ledger.events[idx]
            if ev.status is EventStatus.ACTIVE:
                ledger.events[idx] = ev.with_status(
                    EventStatus.CONFLICTED,
                    "conflicting same-date event blocked until resolved",
                )


def _conflicting_pairs'''
if old in c:
    c2 = c.replace(old, new)
    open('src/rosterops/events/reconcile.py','w').write(c2)
    print('ok')
else:
    print('no')
