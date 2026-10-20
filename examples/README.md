# Examples

A runnable, illustrative scenario (REQUIREMENTS §10): a small field
organization with three reps (E001–E003) and a manager (M001). In October 2026
one rep transfers and is promoted, one takes leave and returns, and one
terminates.

These files are synthetic and **illustrative only** — they show the shape of the
data, not an industry standard.

## Files

| File | Role |
|------|------|
| `config/scenario.yaml` | Runnable configuration (canonical column names) |
| `config/generic_pharma.yaml` | Larger profile showing source-column mapping and Excel inputs |
| `inputs/baseline.csv` | Baseline roster at 2026-09-30 |
| `inputs/transfers.csv` | One transfer (E001: T100 → T400, 2026-10-01) |
| `inputs/promotions.csv` | One promotion (E001 → SENIOR_REP, 2026-10-15) |
| `inputs/leaves.csv` | One leave (E002, 2026-10-05 … 2026-10-12) |
| `inputs/returns.csv` | One return (E002, 2026-10-13) |
| `inputs/terminations.csv` | One termination (E003, 2026-10-20) |
| `inputs/territories.csv` | Territory master (T100–T400 require an owner) |

## Run it (Mode A — process)

```bash
rosterops process \
  --config examples/config/scenario.yaml \
  --baseline examples/inputs/baseline.csv \
  --baseline-date 2026-09-30 \
  --as-of 2026-10-31 \
  --transfers examples/inputs/transfers.csv \
  --promotions examples/inputs/promotions.csv \
  --leaves examples/inputs/leaves.csv \
  --returns examples/inputs/returns.csv \
  --terminations examples/inputs/terminations.csv \
  --territories examples/inputs/territories.csv \
  --output-dir out --overwrite
```

Expected: exit code `0`, `ending_active = 3`, headcount reconciliation
`4 + 0 + 0 - 1 = 3`, and required-owner territories `T100` and `T300` flagged as
vacancies (`TER-005`). Outputs (`final_roster.csv`, `validation_issues.csv`,
`reconciliation.json`, `rosterops_report.xlsx`, …) are written to `out/`.

## Run it (Mode B — validate a snapshot)

Mode B validates a single consolidated snapshot. Point `--snapshot` at
`inputs/baseline.csv` (or any consolidated file) to see structural validation;
movement metrics are reported as `not_available` (`REC-007`).
