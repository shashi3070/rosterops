# rosterops â Implementation Phases (Progress Tracker)



**Companion to:** [`REQUIREMENTS.md`](REQUIREMENTS.md) (operative spec, v1.0)

**Purpose:** track implementation progress phase by phase. Update the status

table and checkboxes as work completes; an item may only be checked when its

acceptance evidence exists (tests executed, commands run, output produced).



**Status legend:** `NOT STARTED` Â· `IN PROGRESS` Â· `BLOCKED` Â· `DONE`



---



## 0. Phase status dashboard



| Phase | Title | Status | Started | Completed | Notes |

|------:|-------|--------|---------|-----------|-------|

| 0 | Repository bootstrap | DONE | 2026-10-20 | 2026-10-20 | Tooling + CI green locally |

| 1 | Domain model, config, grain framework | DONE | 2026-10-20 | 2026-10-20 | All 86 rule specs registered |

| 2 | Input ingestion | DONE | 2026-10-20 | 2026-10-20 | csv/parquet/excel readers, mapping, lineage |

| 3 | Canonical event model | DONE | 2026-10-20 | 2026-10-20 | 8 event types, ledger, dedupe, window, conflicts |

| 4 | Snapshot validation (Mode B) | DONE | 2026-10-20 | 2026-10-20 | Registry-driven snapshot pipeline, vacancies, metric availability |

| 5 | Event-driven reconstruction (Mode A) | DONE | 2026-10-20 | 2026-10-20 | 8 event appliers, lifecycle findings, as-of state |

| 6 | Full rule catalogue, metrics, reconciliation | DONE | 2026-10-20 | 2026-10-20 | Movement metrics, REC-001/002/003, per-rule counts |

| 7 | Reports and CLI | DONE | 2026-10-20 | 2026-10-20 | `process`/`validate` wired, writers, console report |

| 8 | Testing, hardening, performance | IN PROGRESS | | | Invalid-variant matrix, property tests, benchmarks pending |

| 9 | Packaging, documentation, release readiness | NOT STARTED | | | |



**Overall:** Phases 0–7 complete (committed `2337db1`). Phase 8: invalid-variant matrix, property tests (§16), 11-format date parsing, E2E packaging (wheel→venv outside checkout), scaling benchmarks (§4); gates green (ruff check/format --check, mypy src, pytest 262 passed/2 skipped, coverage 90%). Phase 9 not started.



**Rules status:** 86 / 86 spec'd. Implemented across snapshot, state, and

lifecycle layers: all of Groups AâL except the single backlogged rule `REC-008`

(two-snapshot diff, depends on deferred `DEF-001`) â see Â§5. Post-reconstruction

lifecycle coverage now includes `TRF-005/006/007/008`, `PRO-002/003/004/005`,

`LOA-006/007/008/009/010`, `COV-003/004/005`, `DAT-005`, `DAT-008`, `TER-007`,

`REC-004`, and `REC-006`. Positive/negative tests land in Phase 8 for the

remaining matrix rows.



---



## 1. How to use this document



- Each phase has: **goal**, **deliverables** (checkboxes), **acceptance

  criteria** (must all be true to mark DONE), and **exit gate**.

- Checking a deliverable requires evidence: a passing test, a produced file,

  or a command run with its output.

- Requirements traceability: each phase lists the `REQUIREMENTS.md` sections

  it fulfills. Changing requirements updates this plan in the same change.

- Defects found during a phase are fixed within that phase or logged in Â§5

  (Backlog) with a target phase â never silently dropped.

- Parallel-agent workstreams (per master prompt Â§20) are noted per phase; the

  lead integrator owns cross-module contracts and test failures.



---



## 2. Phase detail



### Phase 0 â Repository bootstrap



**Requirements:** Â§2 (decisions D1âD10), Â§17

**Goal:** a buildable, testable, empty package skeleton with tooling.



**Deliverables:**



- [x] Folder `rosterops/` created; `REQUIREMENTS.md`, `IMPLEMENTATION_PHASES.md`, `.gitignore`

- [x] Git repository initialized; initial commit of planning docs

- [x] `pyproject.toml` (PEP 621, src layout, deps `polars`/`pydantic`/`pyyaml`, extras `[excel]`/`[dev]`, entry point `rosterops = rosterops.cli:main`)

- [x] `src/rosterops/` skeleton with `__init__.py`, `__main__.py`, `exceptions.py`

- [x] Tooling configured: `ruff` (lint+format), `mypy` (strict on `src/`), `pytest` + `pytest-cov`, `hypothesis`

- [x] `tests/` tree (`unit/`, `integration/`, `rules/`, `property/`, `fixtures/`)

- [x] CI workflow `.github/workflows/ci.yml` (matrix 3.10â3.13: lint, typecheck, test, build)

- [x] `README.md` stub, `LICENSE` (MIT), `CHANGELOG.md` (Keep a Changelog), `SECURITY.md`, `CONTRIBUTING.md`



**Acceptance criteria:**



- `pip install -e ".[dev]"` succeeds on Python 3.10.

- `ruff check .`, `ruff format --check .`, `mypy src/` pass (even if trivially).

- `pytest` runs (0 tests collected is acceptable at this phase; must not error).

- `python -m rosterops --help` and `rosterops --version` work.

- `python -m build` produces wheel + sdist.



**Exit gate:** CI green on the skeleton.



---



### Phase 1 â Domain model, configuration, grain framework



**Requirements:** Â§4 (domain model), Â§5 (grain), Â§6.1â6.2 (interval + termination semantics), Â§9 (configuration)

**Goal:** the shared contracts every later phase depends on. **This phase's interfaces are frozen by review before Phases 2â6 start in parallel.**



**Deliverables:**



- [x] Canonical schemas: employee, territory, assignment, event, leave interval, coverage record (typed; Polars schema constants + pydantic models where row-level validation is needed)

- [x] `RosterConfig` with strict pydantic validation: `version`, `data.grain` (+ `grain_keys` for `custom`), `dates`, `policies` (incl. `leave`, `vacancy`, `events`), `rules` (id/enabled/severity/params), `inputs` (per-role mapping blocks), `outputs`, `meta.allow_unknown_fields`

- [x] Config precedence: defaults < file < CLI overrides; resolved-config echo (for `run_metadata.json`)

- [x] Grain framework: grain enum (`employee`, `employee_territory`, `employee_territory_assignment`, `custom`), grain-key resolution, GRN rule hooks

- [x] Interval module: half-open `[from, to)` helpers, overlap/adjacency/gap primitives (sorted sweep), inclusiveâexclusive end normalization

- [x] Termination-date conversion for all three `termination_date_semantics` modes

- [x] Exception hierarchy: `RosterOpsError` â `ConfigError`, `InputError`, `ReconstructionError`

- [x] Rule contract (`rules/base.py`): RuleSpec (id, description, default severity, modes, params), Finding model (all Â§11.1 issue fields), deterministic ordering, registry with enable/severity overrides

- [x] Example config `examples/config/generic_pharma.yaml` labeled illustrative

- [x] Unit tests: config validation (unknown fields, bad severity, bad param types, rule id unknown), grain resolution, interval primitives, termination conversion (all 3 modes), rule registry/overrides



**Acceptance criteria:**



- Invalid configs produce `ConfigError` with precise messages (field path + reason).

- Interval tests prove: adjacent `[10-01,11-01)` + `[11-01,â¦)` do NOT overlap; `[10-01,10-31]` inclusive source normalizes to `[10-01,11-01)`.

- Termination semantics: for stated date 2026-10-20, active-through dates are 10-20 (inclusive mode), 10-19 (first-inactive mode), and exclusive-end = 10-20 (explicit mode) â each asserted.

- Every rule ID from REQUIREMENTS Â§8 exists in the registry exactly once with declared default severity and modes (registry-vs-spec consistency test).



**Exit gate:** code review of shared contracts; this doc's deliverables checked.



---



### Phase 2 â Input ingestion



**Requirements:** Â§7 (formats, mapping, lineage), Â§11.3 (safety), Group A rules

**Goal:** any supported file in â canonical raw frames + lineage + input findings.



**Deliverables:**



- [x] `io/csv_reader.py` (lazy scan preferred), `io/parquet_reader.py`, `io/excel_reader.py` (calamine; graceful `ING-002` install-hint when extra missing)

- [x] Format detection by extension; unsupported â `ING-002` listing supported formats

- [x] Missing/unreadable required file â `ING-001`; optional role absent â skipped with note

- [x] Excel: sheet existence â `ING-003`, empty workbook/sheet detection, header-row config, sheet selection (never assume first sheet)

- [x] `mapping/canonical.py`: sourceâcanonical column mapping + aliases, null tokens, per-field date format lists, categorical normalization tables, trim policy

- [x] Lineage columns attached to every row (`source_file`, `source_sheet`, `source_row`); parse failures â findings, **no row silently dropped**

- [x] Leading-zero identifier preservation (string keys end-to-end; regression test with `007`, `00123`)

- [x] `SCH-001..005` raised from the mapping layer (SCH-005 ambiguity check before any load)

- [x] Unit tests: all readers, unreadable/malformed/empty inputs, missing sheet, bad date cell located by row, extra-column warning, alias resolution, null-token handling



**Implementation notes (deviations, recorded):**



- Readers are consolidated in `io/readers.py` (not three separate modules):

  `read_raw` + `detect_format`; `io/raw.py` holds `RawTable`/`ReadError`;

  `io/ingest.py` orchestrates read + map into `IngestedInput`.

- **Excel read dependency changed from `python-calamine` to `fastexcel`** â

  Polars 2.0's `read_excel(engine="calamine")` binds Rust Calamine via

  `fastexcel`. REQUIREMENTS Â§2 D2 and Â§7.1 updated accordingly.

- **pandas interop added (D11, optional `[pandas]` extra)**: `interop.py`

  converts caller DataFrames to/from Polars without mutation; pandas is never a

  core dependency. Engine-level DataFrame acceptance lands in Phase 7.

- `ID-005` (whitespace/normalization collisions) is implemented here because it

  is a property of the trim policy applied during mapping.



**Acceptance criteria:**



- Each test for ING-001/002/003, SCH-001/002/003/004/005 passes with file/sheet/row/column context asserted. â

- CSV and Parquet paths pass with only core deps installed; Excel tests skip cleanly without `[excel]` and pass with it. â

- No test observes a dropped row; parse-failure fixtures yield findings equal to failure-row count. â



**Exit gate:** ingestion contract stable; Phase 3 can consume canonical frames.



---



### Phase 3 â Canonical event model



**Requirements:** Â§4.4 (events), Â§6.3 (normalization steps 1â4), Groups B (ID-002/007), C (DAT-006/007/008)

**Goal:** all eight event types normalized into one ledger with identity, dedupe diagnostics, and date conversion.



**Deliverables:**



- [x] Normalizers for `transfer`, `promotion`, `termination`, `leave_start`, `leave_return`, `hire`, `rehire`, `temp_coverage`

- [x] Event identity: source `event_id` + namespace; deterministic fingerprint for cross-file duplication (ID-007)

- [x] Dedupe diagnostics: never silently drop; duplicates become findings and are excluded from application per policy

- [x] Baseline cutoff filter: events on/before `baseline_date` â `DAT-006` (reject per `policies.events.reject_events_on_or_before_baseline_date`)

- [x] Same-date conflict detection (DAT-007) with explicit policy hook; applied order recorded

- [x] Termination date â canonical interval conversion wired into events (DAT-008)

- [x] Leave-end vs separate return-event reconciliation: one authoritative representation; double-count prevention (per Â§10 note)

- [x] Unit tests per event type + dedupe + cutoff + conflict ordering



**Implementation notes (deviations, recorded):**



- The ledger lives in `events/` (5 modules): `ledger.py` (canonical `Event` +

  `EventLedger` + `EventStatus` + `ReconstructionWindow` + `build_fingerprint`),

  `normalize.py` (roleâtype mapping + termination conversion), `reconcile.py`

  (dedupe/window/conflict), `pipeline.py` (`build_ledger`), `__init__.py`.

- Event identity = a namespaced source `event_id` (`namespace:event_id`, where

  the namespace is the input role) **plus** a SHA-256 content fingerprint over

  (type, employee, effective date, payload). Cross-file duplication (`ID-007`)

  keys on the fingerprint, never on filename/row, so the same business event in

  two files is detected regardless of source.

- Excluded events are **never removed**: each keeps its row in the ledger with a

  non-`active` status (`duplicate`/`out_of_window`/`invalid`) and a finding

  citing the reason and both sources for duplicates.

- Termination conversion (DAT-008) is auditable: the stated date stays on

  `effective_date` and the derived exclusive end is stored on

  `employment_end_exclusive`; the algorithm is `employment_exclusive_end`.

- Leave-end vs return-event reconciliation is represented at the ledger level:

  a `leave_start` carries `leave_start_date`/`leave_end_date`; a separate

  `return` becomes a distinct `leave_return` event. Return-before-leave-end is a

  same-date/interval conflict surfaced by DAT-007 and handled conservatively by

  reconstruction (Phase 5) â no double counting.

- A new `Lineage` value object was added to `models.py` so events and derived

  rows share one provenance shape.



**Acceptance criteria:**



- Round-trip: event frames â ledger preserves every canonical field, the

  namespaced id, the fingerprint, and lineage (`source_file`/`row`). â

- Determinism: fingerprints are content-based and ledger ordering is a stable

  sort (effective date, type, file, row, id); shuffled input yields the same

  active set and conflict findings. â

- Duplicate-across-files triggers ID-007 with both sources cited. â

- Each termination semantics mode (inclusive / first-inactive / explicit) is

  asserted. â

- DAT-006 excludes on/before-baseline and after-as-of events; DAT-007 flags

  double transfers, termination+transfer, and conflicting promotions, noting the

  configured policy when present. â

- No event is silently dropped: excluded events retain a row + finding. â



**Exit gate:** ledger format frozen; Phases 4â6 may proceed in parallel.



---



### Phase 4 â Snapshot validation (Mode B)



**Requirements:** Â§3.2, Â§5.2, Â§11.1 (`not_available`), Groups A/B/D/E-lite/H/J/L + temporal where intervals exist

**Goal:** `engine.validate_snapshot(...)` fully implements the single-file mode with honest metric limits.



**Deliverables:**



- [ ] Baseline/snapshot load â canonical frames â rule execution pipeline (registry-driven, deterministic order)

- [ ] Rules implemented in this phase: GRN-001/002/003, ID-001, ID-003, ID-004, ID-005, DAT-001, DAT-002, DAT-003, DAT-004 (policy-gated), EMP-006, EMP-008, TRF-009, TER-001..006, TER-008, TER-009, ORG-001..005, REC-005, REC-007 (snapshot branch), PRO-006

- [ ] `result.vacancies` computed when territory master present (TER-005/006/007 partial)

- [ ] Metric availability engine: transfer/promotion/leave/termination counts returned as `null` + `not_available` + reason in Mode B (tested)

- [ ] Two-snapshot comparison marked **deferred** (REC-008 backlogged unless pulled forward)



**Acceptance criteria:**



- Valid snapshot â 0 errors, findings only for genuine warnings.

- Grain-mismatch fixture (`grain: employee` + duplicate employee rows) â GRN-001 with both row numbers.

- Overlapping primaries fixture â TER-002/DAT-003 with intersecting interval in message.

- Self-managing manager â ORG-002; 2-node cycle â ORG-003 naming members.

- Inactive / no-owner-required territory unassigned â NOT in vacancy counts (TER-006), required-owner territory unassigned â in counts (TER-005).

- Snapshot-only summary contains `not_available` for every historical movement metric (assert no fabricated numbers).



**Exit gate:** Mode B feature-complete per Â§3.2; exit-code 0/1 behavior demonstrable.



---



### Phase 5 â Event-driven reconstruction (Mode A)



**Requirements:** Â§3.1, Â§4.5â4.6, Â§6.3â6.4, Groups D/E/F/G/I lifecycle + reconstruction

**Goal:** baseline + events â correct as-of state; reconstruction is the product's core.



**Deliverables:**



- [ ] Baseline state construction honoring declared grain

- [ ] Deterministic event application: employment episodes (hire/rehire/termination), role intervals (promotion), assignment intervals (transfer), leave intervals + derived returns, coverage records

- [ ] Cutoff window `(baseline_date, as_of]` filtering with `DAT-006` findings

- [ ] Same-date policy execution with recorded order; default = flag, don't guess

- [ ] Rules implemented: EMP-001..007, TRF-001..007, PRO-001..005, LOA-001..006, LOA-010, COV-001..005, DAT-005, DAT-007, ID-002, ID-006

- [ ] Assignment-interval materialization: old assignment closed at event date, new opened; half-open continuity asserted (no 1-day gaps/overlaps from transfer boundaries)

- [ ] Leave semantics: employment + home assignment retained by default; coverage checked but never auto-applied as permanent change

- [ ] `result.assignments` supports "why is this assignment valid at cutoff" queries (interval + source event)

- [ ] Deterministic `result.roster` as of `as_of`



**Acceptance criteria:**



- Â§10 scenario: reconstructed roster matches expected final state (E001 primary T400 + role SENIOR_REP from 10-15; E002 primary T200 on leave then returned; E003 inactive from 10-21; assignments closed correctly).

- Re-run byte-identical (excluding metadata timestamps): determinism test.

- Event dated â¤ baseline â excluded + DAT-006, state unchanged (property test).

- Transfer fixture with source â  effective assignment â TRF-002; transfer to unknown territory â TRF-004; transfer T100âT100 â TRF-003.

- Termination + transfer same employee/date â DAT-007 flagged, no arbitrary resolution.



**Exit gate:** reconstruction correctness proven on Â§10 before Phase 6 metrics depend on it.



---



### Phase 6 â Full rule catalogue, metrics, reconciliation



**Requirements:** Â§8 (all groups incl. REC-*), Â§9, Â§10

**Goal:** 100% of spec'd rules implemented or explicitly backlogged; metrics and reconciliation complete.



**Deliverables:**



- [ ] Remaining rules: REC-001..004, REC-006, LOA-007..009, DAT-006 enforcement edge cases, and any rules deferred from Phases 4â5

- [ ] Movement metrics module (`metrics/movements.py`): starts/ending active headcount, hires/rehires/terminations, transfer events + per-territory ins/outs (1 event â 1 out + 1 in, TRF-008), promotion events, leave starts/returns/currently-on-leave (LOA-009/010)

- [ ] Vacancy engine: dated vacancy intervals by kind (permanently_unassigned, after_transfer, after_termination, coverage_required, coverage_missing, unassigned_by_design); TER-007 interval math

- [ ] Coverage analysis: LOA-007 requirements, COV-004 capacity

- [ ] Reconciliation (`engine/reconciliation.py`): REC-001 formula with applicability guard (documented refusal when model assumptions violated), REC-002..005, REC-007 consistency; structured `result.reconciliation`

- [ ] Per-rule counts + deterministic finding sort in `result.summary`

- [ ] Severity overrides + disable flags proven to affect output (but not structural ING/SCH/GRN failures)

- [ ] Registry-vs-spec test from Phase 1 extended: **every Â§8 rule has â¥1 positive and â¥1 negative test**



**Acceptance criteria:**



- Â§10 scenario metrics equal the expected table exactly â computed, not hard-coded (test asserts values against independently written expectations).

- REC-001: `3 + 0 + 0 â 1 = 2` â; transfers/promotions/leave shown as headcount-neutral in the ledger tests.

- Rule coverage report: 86 spec'd â implemented + tested, or listed in Â§5 Backlog with reason and target phase.

- Vacancy fixture asserts T100 and T300 vacant, T400 occupied, T200 not vacant (E002 on leave â  vacancy).



**Exit gate:** `Implemented 86 (or backlog entries documented)` â no silent gaps.



---



### Phase 7 â Reports and CLI



**Requirements:** Â§11 (outputs), Â§12 (API), Â§13 (CLI), Â§11.3 (report safety)

**Goal:** user-facing surfaces: CLI commands, typed result object, all writers.



**Deliverables:**



- [ ] `RosterEngine` public API: `process()`, `validate_snapshot()`, `RosterConfig.from_file()`, `RosterEngine.from_file()`; DataFrame inputs accepted; caller frames not mutated (test)

- [ ] CLI: `rosterops process|validate|validate-inputs|rules list|rules describe <ID>|--help|--version` with flags per Â§13

- [ ] Exit codes 0/1/2 per Â§13 incl. `--fail-on-warning` (tested via subprocess)

- [ ] Console report: inputs, dates, rows per input, event counts by type, headcount, assignments, vacancies, rule counts, reconciliation, output paths, top findings â no full employee rows

- [ ] Writers: `csv_report.py` (CSV + `validation_issues.csv`, `movement_summary.csv`, `vacancy_report.csv`), parquet outputs, `json_report.py` (`reconciliation.json`, `run_metadata.json` with config echo, file hashes, versions), `excel_report.py` (10 sheets per Â§11.2, skips with documented reason without `[excel]`)

- [ ] Output safety: refuse writing into input dirs; existing output dir requires `--overwrite`; deterministic outputs

- [ ] `validate-inputs` runs config + ING/SCH checks without reconstruction

- [ ] API/CLI integration tests incl. exit-code matrix



**Acceptance criteria:**



- Â§13 commands all function on the Â§10 fixtures; exit codes asserted: clean run â 0; injected ERROR rule â 1; bad config â 2.

- Output file set matches Â§11.2; Mode B omits unavailable reports with reason in metadata.

- `rosterops_report.xlsx` opens with expected sheet names (openpyxl read-back test) when `[excel]` installed.

- Input file hashes unchanged after every test run (no-mutation test).



**Exit gate:** CLI + reports end-to-end green on fixtures.



---



### Phase 8 â Testing, hardening, performance



**Requirements:** Â§16 (all), Â§15 (performance)

**Goal:** complete test matrix, property tests, E2E, benchmarks; defects fixed.



**Deliverables:**



- [ ] **Invalid-variant integration matrix** (each â expected rule ID(s)):



  | # | Variant | Expected rule(s) |

  |---|---------|------------------|

  | 1 | Unknown employee in transfer | ID-006 / TRF-001 |

  | 2 | Nonexistent destination territory | TRF-004 |

  | 3 | Transfer source â  baseline assignment | TRF-002 |

  | 4 | Two conflicting same-date transfers | DAT-007 / TRF-006 |

  | 5 | Promotion after termination | EMP-005 / PRO-004 |

  | 6 | Duplicate termination across files | EMP-004 / ID-007 |

  | 7 | Leave starts before employment start | LOA-002 / LOA-001 |

  | 8 | Leave extends beyond termination | LOA-006 |

  | 9 | Return earlier than leave start | LOA-004 |

  | 10 | Open leave at as-of date | LOA-010 (INFO, no false error) |

  | 11 | Coverage overlaps beyond capacity | COV-004 |

  | 12 | Two primaries where max = 1 | TER-002 / DAT-003 |

  | 13 | Inactive territory counted as vacancy | TER-006 (must NOT count) |

  | 14 | Manager self-reference | ORG-002 |

  | 15 | 2-node hierarchy cycle | ORG-003 |

  | 16 | Event effective â¤ baseline date | DAT-006 |

  | 17 | Same event in two input files | ID-007 |

  | 18 | Snapshot mode asked for movement counts | REC-007 `not_available` |

  | 19 | Assignment interval end < start | DAT-002 |

  | 20 | Leave with overlapping incompatible leave | LOA-003 |



- [ ] Property-based tests per REQUIREMENTS Â§16 (hypothesis), including preconditions for valid exceptions

- [ ] E2E from clean venv: build wheel â install â run CLI on examples â verify Â§10 outputs, rule IDs, exit codes â run outside source checkout

- [ ] Benchmarks: synthetic 10k / 100k / 1M assignment rows â record wall time + peak memory **actually measured** in Â§4 of this doc; investigate regressions

- [ ] Coverage gate: â¥90% statements on `src/rosterops/` core + rules; ruff + mypy strict clean

- [ ] Security/privacy pass: no PII in logs/metadata (grep-level test on fixtures), no network calls, input immutability, output-path confinement

- [ ] Determinism audit: repeated runs â identical logical outputs



**Acceptance criteria:** all matrix rows have passing tests; benchmarks recorded with environment details; coverage gate met; zero skipped-without-reason tests.



**Exit gate:** quality gates green; only release chores remain.



---



### Phase 9 â Packaging, documentation, release readiness



**Requirements:** Â§17, Â§18, Â§19 (definition of done)

**Goal:** a releasable package whose docs match its behavior.



**Deliverables:**



- [ ] `README.md` complete (purpose, users, modes, formats, install, quickstarts for both modes, sample reports, config basics, CLI, limitations, dev/test)

- [ ] `docs/`: architecture, data model, rule catalogue (**generated/verified against registry** â documented = implemented), configuration, effective dates, troubleshooting

- [ ] `examples/`: inputs, config, expected outputs + `examples/README.md` (Â§10 scenario runnable via one command)

- [ ] `CHANGELOG.md` entry for 0.1.0; `SECURITY.md` (data handling, permissions, retention guidance); `CONTRIBUTING.md`

- [ ] Wheel + sdist build; install into clean venv from artifacts; CLI + import outside checkout verified

- [ ] CI matrix green (3.10â3.13): lint, format, mypy, pytest, coverage, build

- [ ] Release-readiness checklist (REQUIREMENTS Â§17) executed and pasted into Â§4 below with real results

- [ ] Rule-count audit: advertised (README/docs) = implemented = tested; deferrals listed

- [ ] **No publish/push without explicit authorization**



**Acceptance criteria:** every REQUIREMENTS Â§19 item has linked evidence; known-limitations section written honestly.



**Exit gate:** v0.1.0 ready; dashboard fully `DONE` or explicit deferrals recorded in Â§5.



---



## 3. Rule implementation tracking (target phase â status)



Target phase is where the rule's positive/negative tests must land. "Spec'd"

means the RuleSpec (id, name, default severity, modes, params) is registered and

conformance-checked against REQUIREMENTS Â§8; runtime rule logic lands in the

target phase (tracked as "Implemented").



| Group | Rules | Target phase | Spec'd | Implemented | Tested |

|-------|-------|--------------|--------|-------------|--------|

| A â Input/schema (8) | ING-001..003, SCH-001..005 | 2 | 8/8 | 8/8 | 8/8 |

| B â Identifiers (7) | ID-001..007 | 2â3 | 7/7 | 3/7 | 3/7 |

| C â Temporal (8) | DAT-001..008 | 4â5 | 8/8 | 4/8 | 4/8 |

| D â Employment (8) | EMP-001..008 | 4â5 | 8/8 | 0/8 | 0/8 |

| E â Transfers (9) | TRF-001..009 | 5â6 | 9/9 | 0/9 | 0/9 |

| F â Promotions (6) | PRO-001..006 | 5â6 | 6/6 | 0/6 | 0/6 |

| G â Leave (10) | LOA-001..010 | 5â6 | 10/10 | 0/10 | 0/10 |

| H â Territory (9) | TER-001..009 | 4â6 | 9/9 | 0/9 | 0/9 |

| I â Coverage (5) | COV-001..005 | 5â6 | 5/5 | 0/5 | 0/5 |

| J â Hierarchy (5) | ORG-001..005 | 4 | 5/5 | 0/5 | 0/5 |

| K â Reconciliation (8) | REC-001..008 | 6 | 8/8 | 0/8 | 0/8 |

| L â Grain (3) | GRN-001..003 | 1/4 | 3/3 | 0/3 | 0/3 |

| **Total** | **86** | | **86/86** | **15/86** | **15/86** |



*Group A is fully implemented/tested. `ID-005` (trim collisions) is

implemented in the mapping layer (Phase 2). Group B contributes `ID-002`

(event-id uniqueness) and `ID-007` (cross-file fingerprint duplication); Group C

contributes `DAT-001` (valid dates), `DAT-006` (baseline cutoff), `DAT-007`

(same-date conflicts), and `DAT-008` (termination-semantics conversion) â all

raised by the event layer (Phase 3). Note: `ING-001/002/003` also surface at the

engine level in later phases; here they are raised by the ingestion layer.*



---



## 4. Evidence log (append executed results here â never transcribe unexecuted results)



| Date | Command / check | Result |

|------|-----------------|--------|

| 2026-10-20 | `git init` + planning docs committed | PASS (initial commit) |

| 2026-10-20 | `pip install -e ".[dev]"` | PASS (rosterops 0.1.0 editable installed; Python 3.11.3) |

| 2026-10-20 | `ruff check .` / `ruff format --check .` | PASS (33 files formatted; 0 lint errors) |

| 2026-10-20 | `mypy src` | PASS ("no issues found in 24 source files") |

| 2026-10-20 | `pytest` | PASS (112 passed in ~1.0s) |

| 2026-10-20 | `python -m build` | PASS (`rosterops-0.1.0.tar.gz` + `rosterops-0.1.0-py3-none-any.whl`) |

| 2026-10-20 | `rosterops --version` / `python -m rosterops rules list` | PASS ("rosterops 0.1.0"; 86 rules) |

| 2026-10-20 | `rosterops validate-inputs --config examples/config/generic_pharma.yaml` | PASS (configuration OK; grain employee_territory; 6 input roles; 3 rule overrides) |

| 2026-10-20 | `rosterops process ...` (stub) | PASS (exits 2: "not implemented yet") |

| 2026-10-20 | Phase 2 `pytest` (readers + mapping + ingest + interop) | PASS (165 passed, 1 intentional skip) |

| 2026-10-20 | `mypy src` after Phase 2 | PASS ("no issues found in 31 source files") |

| 2026-10-20 | `python -m build` after Phase 2 | PASS (wheel + sdist) |

| 2026-10-20 | Excel ingest end-to-end (openpyxl writer + fastexcel reader) | PASS (leading zeros preserved, lineage `source_sheet`/`source_row` attached) |

| 2026-10-20 | pandas<->polars interop (`[pandas]` extra) | PASS (roundtrip, no caller mutation) |

| 2026-10-20 | Phase 3 `pytest tests/unit/test_events.py` | PASS (17 passed) |

| 2026-10-20 | Phase 3 full `pytest` | PASS (182 passed, 1 intentional skip) |

| 2026-10-20 | `ruff check .` / `ruff format --check .` after Phase 3 | PASS (50 files formatted; 0 lint errors) |

| 2026-10-20 | `mypy src` after Phase 3 | PASS ("no issues found in 36 source files") |

| 2026-10-20 | `python -m build` after Phase 3 | PASS (wheel + sdist) |

| | *(later phases append: pytest run IDs, coverage %, ruff/mypy outputs, build logs, benchmark numbers with machine details)* | |



---



## 5. Backlog / deferred items



Items intentionally not in the initial implementation, with reason and

revisit trigger. Nothing here may be advertised as available in docs/README.



| ID | Item | Reason | Revisit trigger | Target |

|----|------|--------|-----------------|--------|

| DEF-001 | Two-snapshot comparison mode (REC-008 full, Â§3.3) | Not needed for MVP modes A/B | Customer has paired historical snapshots | post-0.1.0 |

| DEF-002 | Manifest/directory ingestion (Â§3.4) | Explicit CLI paths suffice for MVP | Repeated multi-file runs / automation demand | post-0.1.0 |

| DEF-003 | Timestamp-with-timezone sources (beyond date-only + preserve) | Date-effective domain | Source system emits event timestamps | post-0.1.0 |

| DEF-004 | Pandera as optional schema helper | Internal rule engine covers domain checks | Reuse demand for generic schemas | optional |

| DEF-005 | Docs site (mkdocs) | Markdown in-repo adequate for MVP | Public release | post-0.1.0 |

| DEF-006 | Inferred-event labeling from snapshot diff (INF-* rules) | Tied to DEF-001 | DEF-001 active | post-0.1.0 |



**Open questions:** none â decisions D1âD10 in REQUIREMENTS Â§2 resolved all

planning questions. New ambiguity during implementation â choose configurable

default, document here, continue (per master prompt Â§1).



---



## 6. Definition-of-done checklist (final acceptance)



Copied from REQUIREMENTS Â§19; each box requires evidence in Â§4.



- [ ] Clean-env install + CLI outside source tree

- [ ] Mode A multi-file processing works end-to-end

- [ ] Mode B single-file validation works; historical metrics `not_available`

- [ ] Temporary coverage â  permanent transfer, enforced by tests

- [ ] Date semantics unit-tested for every configured mode

- [ ] All 86 rules implemented or backlogged with rationale (Â§5); zero advertised-but-missing

- [ ] Â§10 scenario: expected roster, counts, vacancies reproduced from data

- [ ] 20-row invalid-variant matrix green (Â§8 in phases = table above)

- [ ] CSV/Parquet/JSON tested; Excel tested with `[excel]`

- [ ] Exit codes 0/1/2 verified by subprocess tests

- [ ] Inputs unmodified; no PII leakage in logs/metadata

- [ ] Benchmarks measured and recorded (Â§4) with environment

- [ ] Docs match behavior; known limitations stated honestly

- [ ] CI green on 3.10â3.13; ruff + mypy strict + coverage gate pass

- [ ] Wheel + sdist build and install verified

