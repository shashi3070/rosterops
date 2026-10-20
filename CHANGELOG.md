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
- Optional pandas interop (`[pandas]` extra): `to_polars`/`to_pandas` without
  mutating caller frames (decision D11).
