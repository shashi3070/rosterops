# rosterops

**A deterministic, configurable, Polars-based pharma roster processing and
validation engine.**

`rosterops` ingests a baseline roster (or a single snapshot) plus optional
movement files — transfers, promotions, terminations, leave, hires/rehires,
temporary coverage — normalizes them into a canonical model, reconstructs the
expected roster as of a requested date, applies configurable business rules,
and returns validated Polars DataFrames with audit-ready reports.

It is a local-first data-processing library and CLI. It never writes back to a
CRM, HR system, or database, requires no network access, and never fabricates
historical events from a single snapshot.

## Status

**Early development (Phases 0–3 complete).** Currently available:

- Strict versioned configuration (`RosterConfig`) with grain, date, policy,
  input-mapping, and rule-override sections.
- Canonical domain schemas (employee, territory, assignment, event, coverage).
- Half-open interval and effective-date primitives.
- Registry of all 86 validation rule specifications (`rosterops rules list`).
- **Input ingestion**: CSV/Parquet (always) and Excel (optional `[excel]`)
  readers with format detection, source→canonical column mapping, aliases, null
  tokens, per-field date formats, categorical checks, trim policy, and per-row
  lineage — Group A rules (`ING-*`, `SCH-*`) implemented.
- **Canonical event ledger**: all eight event types (transfer, promotion,
  termination, leave start/return, hire, rehire, temp coverage) normalized with
  namespaced identity, content fingerprints (cross-file dedupe `ID-007`),
  baseline cutoff (`DAT-006`), same-date conflict detection (`DAT-007`), and
  auditable termination-semantics conversion (`DAT-008`).
- Optional pandas interop (`[pandas]`): convert caller DataFrames to/from Polars.
- CLI scaffold: `--version`, `rules list`, `rules describe`, `validate-inputs`
  (configuration check only).

Not yet implemented: reconstruction, full rule execution, metrics, reports, and
the `process`/`validate` commands. See
[`IMPLEMENTATION_PHASES.md`](IMPLEMENTATION_PHASES.md) for the full tracker
and [`REQUIREMENTS.md`](REQUIREMENTS.md) for the operative specification.

## Install

```bash
pip install -e ".[dev]"          # development
pip install -e ".[excel]"        # with Excel read/write support
pip install -e ".[pandas]"       # with pandas interop
```

Requires Python 3.10+. Core dependencies: `polars`, `pydantic`, `PyYAML`.

## Quick look

```bash
rosterops --help
rosterops --version
rosterops rules list
rosterops rules describe TRF-002
rosterops validate-inputs --config examples/config/generic_pharma.yaml
```

```python
from rosterops import RosterConfig

config = RosterConfig.from_file("examples/config/generic_pharma.yaml")
print(config.data.grain)
```

## Documentation

- [`REQUIREMENTS.md`](REQUIREMENTS.md) — operative requirements: modes,
  domain model, effective-date semantics, the 86-rule catalogue, outputs,
  security, testing.
- [`IMPLEMENTATION_PHASES.md`](IMPLEMENTATION_PHASES.md) — phase-by-phase
  progress tracker with acceptance criteria, test matrices, and backlog.

## Development

```bash
ruff check . && ruff format --check .
mypy src
pytest
```

## License

MIT — see [LICENSE](LICENSE).
