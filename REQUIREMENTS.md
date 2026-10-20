# rosterops — Requirements Specification

**Status:** Approved for implementation (planning complete)
**Version:** 1.0 (draft for v0.1.0 release)
**Package:** `rosterops` — a deterministic, configurable, Polars-based pharma roster
processing and validation engine.

This document is the operative requirements baseline for the `rosterops` package.
It is derived from the master development prompt, incorporates the planning
decisions recorded in §2, and is intentionally written as testable requirements
("The engine SHALL ..."). Implementation progress is tracked in
[`IMPLEMENTATION_PHASES.md`](IMPLEMENTATION_PHASES.md).

---

## 1. Purpose, users, and product promise

### 1.1 Purpose

`rosterops` helps pharmaceutical commercial data teams:

1. Understand what changed in a roster over a period.
2. Reconstruct the expected roster as of a specified effective date.
3. Identify business-rule violations before downstream loads.
4. Reconcile movement counts between a baseline snapshot, an event ledger, and
   a resulting snapshot.

### 1.2 Intended users

- Commercial operations / roster data analysts.
- Data engineers loading roster data into CRM Align–style downstream systems.
- Validation/QA engineers auditing monthly roster movements.
- Developers embedding roster checks in pipelines via a Python API or CLI.

### 1.3 Product promise

Given a baseline roster, optional event files, a configuration file, and an
as-of date, the engine produces a reconstructed roster, a normalized event
ledger, row-level validation findings with source lineage, movement metrics,
vacancy/coverage analysis, and reconciliation results — deterministically and
without network access.

### 1.4 Non-goals (v0.1)

The following are explicitly out of scope:

- Territory design, alignment optimization, or HCP/HCO geographic mapping.
- Any write-back to CRM, HRIS, or production databases (the tool is read-only
  with respect to all inputs; it only writes to its configured output dir).
- Web UI, cloud service, or database server.
- Any LLM or external API dependency during processing.
- Inferring historical events from a single snapshot with false certainty.
- Automatically "fixing" invalid source records.

A future dashboard/API may consume this library; the library must remain
independently useful.

---

## 2. Planning decisions (resolved)

These decisions were made during planning and bind the implementation:

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| D1 | **Canonical roster grain** | **Configurable — no single canonical grain.** The engine operates at the grain declared in configuration (`data.grain`), validated against the actual data. | Duplicate, overlap, and cardinality rules are keyed to the declared grain (§5). A grain-validation rule group (GRN-*) enforces that data matches the declared grain. Headcount is always derived at employee level regardless of grain. |
| D2 | **Excel support** | **Optional extra** `rosterops[excel]`: `fastexcel` for reads (the binding Polars uses for its `calamine` engine), `openpyxl` for Excel workbook writes. CSV and Parquet are always available. | Without the extra, Excel inputs fail with rule `ING-002` and an actionable install hint. Excel report generation is skipped with a documented reason. |
| D3 | **Python support** | **3.10+** (CI matrix 3.10–3.13). | Use `from __future__ import annotations` where useful; no 3.9 shims. |
| D4 | **Repository** | Standalone git repository at `rosterops/`, sibling to other projects under `python_lib/`. | Own CI, changelog, and release history. |

Additional locked-in technical choices (revisitable only with rationale):

| # | Choice | Rationale |
|---|--------|-----------|
| D5 | Tabular engine: **Polars** (lazy where practical) | Required by master prompt; performance and expression API. |
| D6 | Config format: **YAML** parsed with `yaml.safe_load` only; schema-validated with **pydantic v2** | Strict validation, no code execution from config. |
| D7 | CLI: **argparse** (stdlib) with subcommands | Keeps core dependencies minimal. |
| D8 | Core dependencies: `polars`, `pydantic>=2`, `pyyaml` | Everything else optional or dev-only. |
| D9 | Date model: **date-only** for business dates; timestamps preserved with explicit timezone policy if a source supplies them | Pharma roster events are date-effective, not time-of-day effective. |
| D10 | Interval convention: **half-open `[effective_from, effective_to)`**, end-nullable | Eliminates off-by-one overlap bugs; source inclusive ends normalized via config. |
| D11 | **pandas interop is optional** (`rosterops[pandas]`): the API accepts `pandas.DataFrame` inputs and can return pandas frames on request; internals are Polars. | Users on pandas stacks get native ergonomics without making pandas a core dependency. Conversions happen only at the API boundary; conversions never mutate the caller's frame. |

---

## 3. Execution modes

### 3.1 Mode A — `process` (baseline + event files)

The engine SHALL accept:

- **Required:** a baseline roster file and `baseline_date`.
- **Optional (any subset):** transfers, promotions, terminations, leaves,
  return-from-leave, hires, rehires, temporary coverage, organization/role/
  territory/manager master files.
- **Required:** `as_of` date.

Behavior:

1. Load and validate all supplied inputs (§7).
2. Normalize all events into a canonical event ledger (§6).
3. Reject or flag (per policy) events dated on or before `baseline_date`
   (`DAT-006`) — events already reflected in the baseline MUST NOT be
   double-applied.
4. Reconstruct employee, employment, role, and assignment state from the
   baseline plus in-window events, as of `as_of` (§6.3).
5. Validate final state and transition history against the rule catalogue (§8).
6. Compute movement metrics, vacancies/coverage, and reconciliation (§9).
7. Emit typed results and reports (§10).

Omission of any optional file type MUST NOT fail the run. A run with zero event
files is legal (it degenerates to a validated baseline pass-through with
as-of = baseline semantics documented).

### 3.2 Mode B — `validate` (single-file snapshot)

The engine SHALL accept a single consolidated roster file plus `as_of` and
SHALL validate it using all snapshot-applicable rules.

**Hard limitation (must be enforced, not merely documented):** historical
movement counts (transfers, promotions, leave starts/returns, terminations,
hires) are **not derivable** from a single snapshot. Such metrics MUST be
reported as `null` with status `not_available` and a reason string. The engine
MUST NOT fabricate event counts. The only exception is an explicitly
configured two-snapshot comparison (§3.3), whose deltas are labeled
`inferred`, never `historical_event`.

### 3.3 Optional mode — two-snapshot comparison (deferred past MVP; specified now)

Given `--baseline` and `--snapshot`, compute added/removed/changed records by
configured keys (`REC-008`). All resulting movement labels MUST carry
`source: inferred_from_snapshot_diff`.

### 3.4 Optional mode — manifest / directory ingestion (deferred past MVP; specified now)

A YAML manifest maps logical input roles to path patterns under a configured
input root. Rules:

- Multiple files matching a single-file role → fail with an actionable error;
  never pick arbitrarily.
- No unrestricted filesystem traversal; resolution is confined to the
  configured input root.
- Missing optional roles are tolerated; missing required roles fail.

---

## 4. Domain model

Four distinct entities — employees, territories, assignments, events — plus
leave and temporary coverage as separate concepts. These MUST NOT be collapsed
into boolean flags on one table.

### 4.1 Employee

Canonical fields: `employee_id` (key), `employee_status`, `first_name`,
`last_name`, `role_code`, `grade_code`, `manager_id`, `business_unit`,
`country`, `region_id`, `district_id`, `employment_start_date`,
`employment_end_date`.

- Names are optional; stable business identifiers are the join keys.
- Employee IDs are treated as **strings** end-to-end; leading zeros MUST be
  preserved; no numeric coercion of identifiers is permitted.

### 4.2 Territory

Canonical fields: `territory_id` (key), `territory_name`, `region_id`,
`district_id`, `country`, `territory_status`, `requires_primary_owner`,
`max_assignees`, `allowed_roles`, `coverage_required_during_leave`.

Vacancy logic MUST consult the territory master and policy; an unassigned
territory is not automatically a vacancy (TER-005/TER-006).

### 4.3 Assignment

Canonical fields: `employee_id`, `territory_id`, `assignment_type`,
`is_primary`, `effective_from`, `effective_to`, `assignment_status`,
`source_event_id`.

- One employee may hold multiple simultaneous assignments when policy allows.
- Repeated `employee_id` values are NOT duplicates unless they collide on the
  **declared grain key** (§5).

### 4.4 Event

Canonical fields: `event_id`, `event_type`, `employee_id`, `effective_date`,
`recorded_date`, `old_value`, `new_value`, `from_territory_id`,
`to_territory_id`, `old_role_code`, `new_role_code`, `leave_start_date`,
`leave_end_date`, `source_file`, `source_sheet`, `source_row`, `source_system`.

Supported event types: `transfer`, `promotion`, `termination`, `leave_start`,
`leave_return`, `hire`, `rehire`, `temp_coverage`. The internal design MAY use
a typed/polymorphic event schema; either way all eight types MUST be
normalizable from configured inputs.

### 4.5 Leave and availability

Five distinct concepts, never interchangeable:

1. Employment status (employed or not).
2. Assignment status (permanent territory assignment active or not).
3. Leave status (on leave or not, with dated intervals).
4. Temporary coverage (separate dated relationships, §4.6).
5. Field availability (derived: employed ∧ on assignment ∧ not on leave ∧ not
   otherwise unavailable).

Default policy (configurable): leave retains employment status and the home
assignment (`policies.leave.retains_employment_status: true`,
`retains_home_assignment: true`).

### 4.6 Temporary coverage

Separate dated relationships with fields: `coverage_id`,
`covering_employee_id`, `covered_territory_id`, `covered_employee_id`,
`coverage_start_date`, `coverage_end_date`, `coverage_type`,
`is_primary_coverage`, `source_event_id`.

- Temporary coverage MUST NOT permanently modify the covering employee's home
  assignment (COV-005).
- Overlapping coverage capacity is governed by configuration (COV-004).

---

## 5. Data grain configuration (decision D1)

### 5.1 Declaration

Configuration MUST declare the input/working grain:

```yaml
data:
  grain: employee_territory        # see enum below
  grain_keys: []                   # required iff grain == custom
```

Supported grain values:

| Value | Grain key | Typical source shape |
|-------|-----------|----------------------|
| `employee` | `employee_id` | One row per employee; single home territory. |
| `employee_territory` | (`employee_id`, `territory_id`) | Current territory assignments; one row per pair. |
| `employee_territory_assignment` | (`employee_id`, `territory_id`, `assignment_type`, `effective_from`) | Interval-level assignment rows. |
| `custom` | user-supplied `grain_keys` list | Multi-product / multi-organization assignment keys, etc. |

### 5.2 Engine obligations under configurable grain

1. **Grain validation (Group L, GRN-*):** the engine SHALL verify that the
   loaded baseline actually conforms to the declared grain and raise findings
   when it does not (e.g., `grain: employee` but two rows for `E001`).
2. **Duplicate detection** (ID-003, ID-004, REC-006) SHALL key on the
   declared grain, never on `employee_id` alone unless grain is `employee`.
3. **Overlap detection** (DAT-003, TER-002/003/009) SHALL operate at the
   (`employee_id`, `territory_id`, assignment-compatibility) temporal level
   regardless of declared grain.
4. **Headcount** SHALL always be derived by de-duplicating to distinct
   `employee_id` under employment-date semantics — never by counting rows.
5. **Configuration that cannot be honored** (e.g., interval rules requested
   while `effective_from` is unmapped under grain `employee`) MUST produce a
   clear configuration error at validation time, not a silent downgrade.
6. The chosen grain MUST be recorded in `run_metadata.json` and in the
   summary for auditability.

---

## 6. Time and effective-date semantics

### 6.1 Canonical interval convention

All internal intervals are half-open: `[effective_from, effective_to)`.
`effective_to` null/absent = open-ended. Sources with inclusive end dates MUST
be normalized via an explicit per-source setting
(`inputs.<role>.date_semantics.interval_end: exclusive | inclusive`); silent
mixing of conventions is prohibited (DAT-008).

### 6.2 Termination-date semantics

Configuration `dates.termination_date_semantics` SHALL support:

- `last_working_day_inclusive` (default): employee active through the stated
  date; first inactive day = date + 1.
- `first_inactive_day`: employee inactive from the stated date.
- `explicit_effective_end`: the stated date is already the exclusive end.

This conversion MUST be unit-tested for each mode.

### 6.3 As-of reconstruction procedure

1. Validate the baseline snapshot; construct baseline state.
2. Normalize all events to the canonical ledger; dedupe with diagnostics.
3. Filter out events outside `(baseline_date, as_of]` per policy; flag
   out-of-window events (`DAT-006`) rather than applying them.
4. Order in-window events deterministically (effective_date, then configured
   same-date policy, then source_file, source_row as a stable tiebreak of
   last resort — with the applied order recorded).
5. Apply each event to the state effective immediately before it; permitted
   state changes only.
6. Materialize employment episodes, role intervals, assignment intervals,
   leave intervals, and coverage intervals.
7. Validate final state and transition history.
8. Compute metrics from the ledger with explicit counting definitions (§9).

### 6.4 Same-date conflicting events

Conflicts (two transfers to different destinations; termination + transfer;
conflicting promotions; return before leave end; rehire + termination) MUST:

- default: be flagged (`DAT-007`) and NOT resolved by arbitrary row order;
- optionally: be resolved by an explicit configured policy
  (`policies.events.resolve_conflicting_same_date_events: <policy_name>`),
  with the applied policy and order recorded in run metadata.

---

## 7. Inputs, formats, and column mapping

### 7.1 Formats

| Format | Availability | Reader |
|--------|--------------|--------|
| CSV | always | Polars (lazy scan preferred) |
| Parquet | always | Polars |
| XLSX/XLS | extra `[excel]` | `fastexcel` via Polars (`engine="calamine"`) |
| XLSX write (report) | extra `[excel]` | `openpyxl` |

Unsupported extensions MUST fail with `ING-002` listing supported formats.
Missing Excel extra MUST fail with an actionable install message, not a raw
`ImportError`.

### 7.2 Source mapping

Each input role has a mapping block: `path`, `format`, `sheet_name`,
`header_row`, `columns: {canonical: source}`. Requirements:

- Explicit source→canonical mappings; optional alias lists.
- Required-unmapped canonical fields → `SCH-001` (fail that input role).
- Two source columns mapped to one canonical field without an explicit merge
  strategy → `SCH-005`.
- Unused extra columns → warning-level finding, not a failure.
- Configurable null tokens (`""`, `"N/A"`, `"NULL"`, ...).
- Explicit date format lists per mapped date field.
- Configurable categorical normalization tables (status codes, assignment
  types) with invalid values flagged (`SCH-004`), never silently rewritten.
- Trimming policy for text fields; trim-induced identifier collisions flagged
  (`ID-005`), never auto-merged.
- Excel: configurable sheet name and header row; empty workbook/sheet detected
  and reported (`ING-003` context).
- No row may be silently dropped for parse failure; failures become findings
  with file/sheet/row/column lineage.

### 7.3 Lineage

Every loaded row carries `source_file`, `source_sheet` (nullable), `source_row`
(1-based data row or configured header offset), and every derived finding and
derived record references that lineage or a deterministic derivation of it.

---

## 8. Validation rule catalogue

Severity levels: `ERROR` (result marked invalid; blocks exit-code 0),
`WARNING` (review; exit 0 unless `--fail-on-warning`),
`INFO` (measured observation). All severities are configurable per rule;
severity overrides MUST NOT bypass structural failures that make processing
impossible (file unreadable, config invalid).

Modes: **S** = snapshot validation, **P** = process (event reconstruction).

Every rule below MUST be implemented or explicitly listed in the backlog
section of `IMPLEMENTATION_PHASES.md` with a reason. Unimplemented rules MUST
NOT be advertised as available.

### Group A — Input and schema

| ID | Name | Default | Modes |
|----|------|---------|-------|
| ING-001 | Input file exists and is readable | ERROR | S,P |
| ING-002 | File format is supported (incl. missing `[excel]` extra) | ERROR | S,P |
| ING-003 | Expected worksheet exists | ERROR | S,P |
| SCH-001 | Required columns present | ERROR | S,P |
| SCH-002 | Column types are valid (parse failures located by row) | ERROR | S,P |
| SCH-003 | Required fields are populated | ERROR | S,P |
| SCH-004 | Configured categorical values are valid | WARNING | S,P |
| SCH-005 | Source-to-canonical mapping is unambiguous | ERROR | S,P |

### Group B — Identifier and record integrity

| ID | Name | Default | Modes |
|----|------|---------|-------|
| ID-001 | Employee ID is non-null and non-empty | ERROR | S,P |
| ID-002 | Event IDs unique within their namespace | ERROR | P |
| ID-003 | Duplicate baseline records at the declared grain | ERROR | S,P |
| ID-004 | Duplicate assignment key | ERROR | S,P |
| ID-005 | Whitespace/normalization collisions | WARNING | S,P |
| ID-006 | Identifier references resolve (employee known) | ERROR | P |
| ID-007 | Event duplication across files (fingerprint-based) | ERROR | P |

### Group C — Effective dates and temporal integrity

| ID | Name | Default | Modes |
|----|------|---------|-------|
| DAT-001 | Effective start date is valid/parseable | ERROR | S,P |
| DAT-002 | Interval bounds valid (end ≥ start) | ERROR | S,P |
| DAT-003 | Interval overlap detection (incompatible assignments) | ERROR | S,P |
| DAT-004 | Temporal gap detection (coverage-required intervals) | WARNING | S,P |
| DAT-005 | Event occurs after termination | ERROR | P |
| DAT-006 | Event already reflected in baseline (on/before baseline date) | ERROR | P |
| DAT-007 | Same-date conflicting events | ERROR | P |
| DAT-008 | Source and canonical date semantics agree (termination conversion) | ERROR | S,P |

### Group D — Employment lifecycle

| ID | Name | Default | Modes |
|----|------|---------|-------|
| EMP-001 | Hire/rehire has valid identity and effective date | ERROR | P |
| EMP-002 | Hire does not conflict with an active employment episode | ERROR | P |
| EMP-003 | Termination references a valid active episode | ERROR | P |
| EMP-004 | Termination events are not duplicated | ERROR | P |
| EMP-005 | Post-termination events are controlled | ERROR | P |
| EMP-006 | Final status agrees with lifecycle events | ERROR | S,P |
| EMP-007 | Rehire creates a distinct episode; prior end date preserved | ERROR | P |
| EMP-008 | Headcount uses defined employment semantics (leave ≠ termination) | INFO | S,P |

### Group E — Transfers and assignments

| ID | Name | Default | Modes |
|----|------|---------|-------|
| TRF-001 | Transfer references a valid employee | ERROR | P |
| TRF-002 | Transfer source matches the effective assignment | ERROR | P |
| TRF-003 | Transfer source and destination differ | WARNING | P |
| TRF-004 | Destination territory exists | ERROR | P |
| TRF-005 | Transfer date is valid for the employee | ERROR | P |
| TRF-006 | Conflicting transfers are detected | ERROR | P |
| TRF-007 | Assignment state after transfer is consistent | ERROR | P |
| TRF-008 | Transfer counts reconcile (1 event = 1 out + 1 in) | INFO | P |
| TRF-009 | Multiple-territory assignments respect policy | WARNING | S,P |

### Group F — Promotions and role changes

| ID | Name | Default | Modes |
|----|------|---------|-------|
| PRO-001 | Promotion has valid current and new role values | ERROR | P |
| PRO-002 | Role transition permitted (role-transition matrix) | WARNING | P |
| PRO-003 | Promotion event is unique | ERROR | P |
| PRO-004 | Promotion effective date valid for employment | ERROR | P |
| PRO-005 | Promotion state correctly reconstructed | ERROR | P |
| PRO-006 | Promotion counts are event-based; no inference from snapshots | INFO | S |

### Group G — Leaves of absence and return

| ID | Name | Default | Modes |
|----|------|---------|-------|
| LOA-001 | Leave start/end dates valid | ERROR | P |
| LOA-002 | Leave references a valid employment episode | ERROR | P |
| LOA-003 | Duplicate/overlapping incompatible leave detected | ERROR | P |
| LOA-004 | Return-from-leave event is valid | ERROR | P |
| LOA-005 | Leave does not silently terminate employment | ERROR | S,P |
| LOA-006 | Leave after termination is controlled | ERROR | P |
| LOA-007 | Leave coverage requirements satisfied | WARNING | P |
| LOA-008 | Coverage does not create permanent assignment changes | ERROR | P |
| LOA-009 | Leave metrics distinguish starts / returns / currently absent | INFO | P |
| LOA-010 | Open leaves handled without false invalidity | INFO | P |

### Group H — Territory integrity, primaries, vacancies

| ID | Name | Default | Modes |
|----|------|---------|-------|
| TER-001 | Assigned territory exists in master | ERROR | S,P |
| TER-002 | Primary assignment constraints (max primaries/employee) | ERROR | S,P |
| TER-003 | Territory occupancy is valid (no incompatible overlap) | ERROR | S,P |
| TER-004 | Territory role eligibility | WARNING | S,P |
| TER-005 | Required-owner vacancies identified (with interval) | WARNING | S,P |
| TER-006 | Unrequired/unassigned-by-design territories not counted as vacancies | INFO | S,P |
| TER-007 | Vacancy intervals correct | WARNING | P |
| TER-008 | Territory capacity (max assignees) enforced | ERROR | S,P |
| TER-009 | Assignment overlaps follow role/territory policy | ERROR | S,P |

### Group I — Temporary coverage

| ID | Name | Default | Modes |
|----|------|---------|-------|
| COV-001 | Coverage references valid employees and territories | ERROR | P |
| COV-002 | Coverage interval valid | ERROR | P |
| COV-003 | Coverage linked to a valid absence when required | WARNING | P |
| COV-004 | Concurrent coverage within configured capacity | WARNING | P |
| COV-005 | Coverage does not overwrite the home roster | ERROR | P |

### Group J — Manager hierarchy and org structure

| ID | Name | Default | Modes |
|----|------|---------|-------|
| ORG-001 | Manager exists | ERROR | S,P |
| ORG-002 | No self-management | ERROR | S,P |
| ORG-003 | No reporting cycles | ERROR | S,P |
| ORG-004 | Manager effective for the relevant date | WARNING | S,P |
| ORG-005 | Org relationships agree with territory hierarchy | WARNING | S,P |

### Group K — Reconciliation and operational metrics

| ID | Name | Default | Modes |
|----|------|---------|-------|
| REC-001 | Headcount reconciliation: `ending_active = starting_active + hires + rehires − terminations` | ERROR | P (S: `not_available`) |
| REC-002 | Transfer reconciliation (ins/outs by territory) | ERROR | P |
| REC-003 | Leave reconciliation (starts, returns, open) | WARNING | P |
| REC-004 | Assignment reconciliation vs event ledger | ERROR | P |
| REC-005 | Vacancy/active-primary reconciliation | WARNING | S,P |
| REC-006 | Duplicate movement detection across inputs | ERROR | P |
| REC-007 | Movement summary consistency (and `not_available` explanations in S) | ERROR | S,P |
| REC-008 | Snapshot comparison consistency (two-snapshot mode) | WARNING | S |

### Group L — Grain integrity (decision D1)

| ID | Name | Default | Modes |
|----|------|---------|-------|
| GRN-001 | Baseline cardinality conforms to declared grain | ERROR | S,P |
| GRN-002 | Declared grain keys are mapped and populated | ERROR | S,P |
| GRN-003 | Interval-bearing grains have required date columns | ERROR | S,P |

### 8.1 Rules engine requirements

- Per-rule: stable ID, description, default severity, applicability (mode),
  enable/disable flag, severity override, parameters.
- Deterministic finding ordering: (severity rank, rule_id, source_file,
  source_row, entity key).
- Rule-level counts in the summary.
- Rule configuration versioned; unknown rule IDs in config → clear error.
- Findings carry source lineage and human-readable messages; employee names
  MUST NOT appear in summaries where an ID suffices.

---

## 9. Business policy configuration

### 9.1 File structure (validated schema, not free-form YAML)

Top-level sections: `version`, `data` (grain), `dates`, `policies`,
`rules`, `inputs`, `outputs`. Unknown fields MUST error unless
`meta.allow_unknown_fields: true` is set for forward compatibility.

### 9.2 Policies (defaults)

```yaml
version: 1
data:
  grain: employee_territory

dates:
  interval_convention: half_open
  baseline_includes_effective_date: true
  default_date_format: "%Y-%m-%d"
  termination_date_semantics: last_working_day_inclusive

policies:
  allow_multiple_active_territories: true
  max_primary_territories_per_employee: 1
  require_active_manager: true
  allow_unassigned_active_employees: true
  leave:
    retains_employment_status: true
    retains_home_assignment: true
    coverage_required_by_default: false
    allow_overlapping_leave_types: false
  vacancy:
    derive_only_for_required_owner_territories: true
    count_leave_as_vacancy: false
  events:
    reject_events_on_or_before_baseline_date: true
    resolve_conflicting_same_date_events: false
```

### 9.3 Precedence

Built-in defaults < config file < CLI overrides. The fully resolved
configuration MUST be echoed into `run_metadata.json` (redacting file paths
outside the input root if configured).

### 9.4 Safety

- `yaml.safe_load` only; no Python expression evaluation.
- No shell execution, no dynamic imports, no network calls from configuration.
- Rule overrides are auditable policy decisions recorded in run metadata.

### 9.5 Sample profiles

Ship at least one clearly-labeled **example** profile
(`examples/config/generic_pharma.yaml`) documented as illustrative, not an
industry standard.

---

## 10. Reference end-to-end scenario (synthetic)

Fully synthetic; used by integration tests and docs. Baseline 2026-09-30:
E001→T100, E002→T200, E003→T300 (all Active REP; T100/T200/T300/T400 all
require primary owner; T400 initially vacant). Events:

| File | Event | Effect |
|------|-------|--------|
| transfers | TR001: E001, 2026-10-01, T100→T400 | assignment changes; T100 vacant |
| promotions | PR001: E001, 2026-10-15, REP→SENIOR_REP | role interval changes; headcount unchanged |
| leaves | LV001: E002, 2026-10-05 → 2026-10-12 (return inclusive) | 1 leave start, 1 return, 0 on leave at cutoff; assignment retained |
| terminations | TM001: E003, 2026-10-20 (last working day inclusive) | inactive from 10-21; T300 vacant |

Expected summary as of 2026-10-31 (calculated, never hard-coded in engine):

| Metric | Value |
|--------|------:|
| Starting active employees | 3 |
| Ending active employees | 2 |
| Transfer events / ins / outs | 1 / 1 / 1 |
| Promotion events | 1 |
| Leave starts / returns | 1 / 1 |
| Termination events | 1 |
| On leave at cutoff | 0 |
| Required-owner vacant territories | 2 (T100, T300) |

Invalid variants (each must trigger specific rule IDs) are enumerated in
`IMPLEMENTATION_PHASES.md` Phase 8 test matrix.

---

## 11. Outputs and auditability

### 11.1 Typed result object

| Field | Content |
|-------|---------|
| `result.roster` | Reconstructed roster as of `as_of` (canonical columns + grain metadata). |
| `result.assignments` | Resolved assignment intervals (employee, territory, type, primary, `[from, to)`, source). |
| `result.events` | Normalized event ledger with full source lineage. |
| `result.issues` | Findings: `issue_id`, `rule_id`, `category`, `severity`, `message`, `employee_id`, `territory_id`, `event_id`, `effective_date`, `source_file`, `source_sheet`, `source_row`, `source_column`, `actual_value` (safe), `expected_value`, `suggested_action`, stable `issue_key`. |
| `result.summary` | Movement metrics, starting/ending counts, rule counts, reconciliation status, data-completeness stats, `not_available` metrics with reasons. |
| `result.vacancies` | Dated vacancy/coverage results (only when territory master + assignments suffice): vacancy kind ∈ {permanently_unassigned, after_transfer, after_termination, coverage_required, coverage_missing, unassigned_by_design}. |
| `result.reconciliation` | Expected vs actual totals, formulas applied, pass/fail, non-applicability explanations. |
| `result.metadata` | Tool version, config version + resolved hash, input file names + hashes, parameters, grain, timestamps. |

All returned DataFrames are Polars DataFrames; caller-owned inputs MUST NOT be
mutated.

### 11.2 Files written (Mode A)

```text
output/<run>/
├── final_roster.parquet
├── final_roster.csv
├── assignment_intervals.parquet
├── normalized_events.parquet
├── validation_issues.csv
├── movement_summary.csv
├── vacancy_report.csv
├── reconciliation.json
├── run_metadata.json
└── rosterops_report.xlsx        # only with [excel] extra
```

Mode B writes the subset that applies (no event ledger / reconciliation of
movements); unavailable reports are omitted with a documented reason — never
emitted as misleading empty files.

### 11.3 Report safety

- Never write into input folders; refuse output dirs that collide with input
  paths; `--overwrite` required to replace an existing output dir.
- Deterministic outputs: identical inputs + config ⇒ logically identical
  results (run metadata timestamps excluded).
- CSV/JSON/Excel escaping per format; no raw HTML/script injection vectors.
- Excel workbook: sheets `Summary`, `Final_Roster`, `Transfers`,
  `Promotions`, `Terminations`, `Leave_Activity`, `Vacancies`,
  `Validation_Issues`, `Reconciliation`, `Run_Metadata`; size safeguards with
  documented row caps (large data → Parquet/CSV preferred, cap reported).

---

## 12. Python API

```python
from rosterops import RosterEngine, RosterConfig

config = RosterConfig.from_file("config/rosterops.yaml")
engine = RosterEngine(config=config)

result = engine.process(
    baseline="inputs/main_roster.xlsx",
    baseline_date="2026-09-30",
    transfers="inputs/transfers.xlsx",
    promotions="inputs/promotions.xlsx",
    terminations="inputs/terminations.xlsx",
    leaves="inputs/leaves.xlsx",
    as_of="2026-10-31",
)

result = engine.validate_snapshot("inputs/current_roster.csv", as_of="2026-10-31")
result = engine.validate_snapshot(pl.read_parquet("roster.parquet"), as_of=...)
```

Requirements:

- Accept file paths and (where schema-valid) Polars **or pandas** DataFrames;
  DataFrame inputs skip file I/O but still run mapping/validation. pandas
  support requires the optional `rosterops[pandas]` extra; without it, passing a
  pandas frame raises `InputError` with an install hint.
- Return Polars DataFrames by default; `to_pandas=True` (or a pandas-input run)
  can request pandas outputs. Conversions never mutate the caller's frame.
- Synchronous API; documented as such.
- Typed results; `RosterOpsError` hierarchy: `ConfigError`, `InputError`,
  `ReconstructionError` — distinct from business validation findings.
- Business-invalid-but-processable data yields findings, not exceptions.
- Engine independent of web frameworks and databases.

---

## 13. CLI

Commands: `process`, `validate`, `validate-inputs`, `rules list`,
`rules describe <RULE_ID>`, `--help`, `--version`.

Exit codes (stable, documented):

| Code | Meaning |
|------|---------|
| 0 | Completed; no error-severity findings; reconciliation passed (warnings allowed unless `--fail-on-warning`). |
| 1 | Completed; error-severity findings and/or reconciliation failures present. |
| 2 | Could not perform the run: invalid config, unreadable required input, impossible reconstruction, fatal internal error. |

Console report SHALL show: loaded inputs, baseline/as-of dates, rows per input,
event counts by type, starting/ending headcount, assignment counts,
vacancy/coverage metrics (when available), error/warning counts by rule,
reconciliation status, output paths, and a short high-priority findings list —
without dumping full employee rows.

---

## 14. Security, privacy, safety

1. Synthetic data only in repository tests and examples.
2. No network access required or performed during processing.
3. No logging of full employee rows by default; no names in summaries when IDs
   suffice; no credentials or unrelated env vars in logs or metadata.
4. Inputs never modified; outputs confined to the output dir; optional input
   root confinement for path resolution.
5. Config cannot execute code (safe YAML only).
6. No auto-correction of business records; corrections are user actions
   outside the tool.
7. Documented guidance on file permissions and retention for roster data.
8. Report schemas exclude fields not declared in the public report schema.

---

## 15. Performance

- Prefer Polars lazy scans for CSV/Parquet; collect at explicit boundaries
  (row-level findings, Excel reads).
- No per-row Python loops for vectorizable transformations; temporal interval
  logic implemented with sorted interval sweeps / as-of joins, tested
  explicitly (equality joins are insufficient).
- Benchmark suite on synthetic data at increasing sizes (10k / 100k / 1M
  assignment rows): report wall time and peak memory in
  `IMPLEMENTATION_PHASES.md` Phase 8 results. No performance claims without
  measured numbers.
- Public Polars APIs only.

---

## 16. Testing requirements

- **Unit:** readers, mapping, date parsing, leading-zero preservation,
  dedupe, grain validation, interval construction, termination conversion,
  every rule (≥1 positive + ≥1 negative test each), severity config,
  deterministic ordering, safe error messages.
- **Integration:** the §10 scenario end-to-end plus the invalid-variant matrix
  (Phase 8 of the phases doc): unknown employee in transfer; nonexistent
  destination; transfer-source mismatch; same-date conflicting transfers;
  promotion after termination; duplicate termination; leave before
  employment; leave beyond termination; return before leave start; open
  leave; coverage over capacity; two primaries where one allowed; inactive
  territory counted as vacancy; manager self-cycle; two-node hierarchy cycle;
  event on/before baseline; event duplicated across files; snapshot mode
  `not_available` metrics.
- **Property-based (hypothesis):** reapplying an event never silently
  duplicates state; future non-applicable events don't change earlier as-of
  state; valid internal transfer preserves headcount; promotion alone
  preserves headcount; leave round-trip preserves headcount; adjacent
  half-open intervals don't false-overlap; incompatible primary overlaps ARE
  detected; transfer ins/outs reconcile; normalization doesn't mutate source.
- **End-to-end:** clean venv → build wheel → install → run CLI on examples →
  verify outputs, issue IDs, exit codes → run from outside the source tree.
- **Quality gates:** ruff (lint+format), mypy (strict on `src/`), pytest with
  ≥90% statement coverage on `src/rosterops/` core + rules; domain assertions
  prioritized over coverage chasing. CI on 3.10–3.13.

---

## 17. Packaging and developer experience

- `src/` layout; `pyproject.toml` (PEP 621); hatchling or setuptools backend.
- Console entry point `rosterops`.
- Extras: `[excel]`, `[dev]`, `[docs]` (later).
- Pin tested dependency ranges; verify against current Polars/pydantic at
  implementation time.
- Deliverables present before release: `README.md`, `LICENSE` (MIT unless
  directed otherwise), `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`.
- Build both wheel and sdist; verify import and CLI outside the checkout.
- No customer data, no generated outputs committed.
- CI: lint, typecheck, tests across matrix, build check.
- **No PyPI publish, no public repo push without explicit authorization.**

---

## 18. Documentation deliverables

- `README.md`: purpose, users, modes, formats, install, quickstart (both
  modes), sample report, config basics, CLI, limitations, dev/test setup.
- `docs/`: `architecture.md`, `data-model.md`, `rule-catalog.md` (generated or
  cross-checked against code — every documented rule must exist),
  `configuration.md`, `effective-dates.md`, `troubleshooting.md`.
- Explicit separation of generic data-integrity checks from configurable
  organization policies; no claim that sample rules represent "the pharma
  industry standard".

---

## 19. Definition of done

The project is complete when all of the following hold (each item maps to
verifiable evidence in the phases doc):

1. Installable in a clean environment; CLI works from outside the source tree.
2. Multi-file Mode A and single-file Mode B both function per §3.
3. Historical metrics in Mode B are `not_available`, never fabricated.
4. Permanent transfers vs temporary coverage are distinct and validated.
5. Date semantics (§6) implemented and unit-tested per mode.
6. Rule catalogue (§8) implemented or explicitly backlogged with rationale;
   no advertised-but-missing rules.
7. §10 scenario produces the expected roster, counts, and vacancy results.
8. Invalid variants trigger the expected rule IDs.
9. CSV/Parquet/JSON outputs tested; Excel tested when `[excel]` installed.
10. Exit codes match §13; inputs unmodified; no PII leakage in logs/metadata.
11. Measured benchmark results recorded; no fabricated numbers.
12. Docs match implemented behavior; known limitations listed honestly.
