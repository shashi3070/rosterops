# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Planning baseline: `REQUIREMENTS.md` (86-rule catalogue, modes A/B, domain
  model, effective-date semantics) and `IMPLEMENTATION_PHASES.md` tracker.
- Package skeleton (src layout, hatchling build, CLI entry point, py.typed).
- Strict versioned configuration layer (`RosterConfig`) with policy, grain,
  input-mapping, and rule-override schemas.
- Canonical domain schemas and enumerations (employee, territory, assignment,
  event, coverage; grain and severity definitions).
- Half-open interval primitives and effective-date helpers (termination-date
  semantics, reconstruction-window filtering).
- Rule registry: 86 stable rule specifications with default severities, mode
  applicability, and parameter declarations; deterministic finding model.
- `rosterops rules list` / `rosterops rules describe` CLI commands.
- Tooling: ruff, mypy (strict), pytest + coverage, hypothesis, CI workflow
  matrix for Python 3.10–3.13.
- Input ingestion layer: `read_raw`/`detect_format` for CSV (always),
  Parquet (always), and Excel (optional `[excel]` extra via `fastexcel`);
  graceful `ING-001/002/003` handling with actionable install hints.
- Source→canonical mapping (`mapping/canonical.py`): explicit mappings,
  aliases, configurable null tokens, per-field date formats, categorical value
  maps/validation, list parsing, trim policy, and per-row lineage
  (`source_file`/`source_sheet`/`source_row`). Implements `SCH-001..005` and
  `ID-005`; no row is ever silently dropped.
- Leading-zero identifier preservation (string keys end-to-end).
- Canonical event ledger (`events/`): all eight event types normalized into a
  single model with namespaced identity plus content fingerprints, cross-file
  duplicate detection (`ID-007`), baseline-window cutoff (`DAT-006`), same-date
  conflict detection with an explicit policy hook (`DAT-007`), and auditable
  termination-date-semantics conversion (`DAT-008`). Excluded events are never
  dropped — they retain a row with a status and finding. Duplicate movements
  surface as `REC-006` (and `PRO-003` for promotions); conflicting transfers as
  `TRF-006`.
- `Lineage` value object shared by loaded and derived records.
- Rule engine (`engine/`): grain enforcement (`GRN-001..003`), baseline state
  reconstruction with half-open intervals, snapshot (Mode B) and process
  (Mode A) rule scoping, movement metrics, vacancy derivation, event
  reconciliation (`REC-001..004`), and a deterministic finding sort with stable
  issue keys/ids. Post-reconstruction lifecycle rules cover transfers
  (`TRF-005/006/007/008`), promotions (`PRO-002/003/004/005`), leave
  (`LOA-006/007/009/010`), coverage (`COV-003/004/005`), events after
  termination (`DAT-005`), vacancy intervals (`TER-007`), and the `LOA-008`
  guard.
- Result writers (`outputs/`): the full Mode A output set and a Mode B subset
  that omits unavailable artefacts with reasons; safety checks refuse to write
  into input folders unless `overwrite` is set; Excel via `openpyxl`, plus a
  console report.
- Public API (`RosterEngine.process` / `.validate`) and a wired CLI
  (`rosterops process`, `rosterops validate`) with documented exit codes.
- Optional pandas interop (`[pandas]` extra): `to_polars`/`to_pandas` without
  mutating caller frames (decision D11).