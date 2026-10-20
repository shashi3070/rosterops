# rosterops — Implementation Phases (Progress Tracker)

**Companion to:** [`REQUIREMENTS.md`](REQUIREMENTS.md) (operative spec, v1.0)
**Purpose:** track implementation progress phase by phase. Update the status
table and checkboxes as work completes; an item may only be checked when its
acceptance evidence exists (tests executed, commands run, output produced).

**Status legend:** `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · `DONE`

---

## 0. Phase status dashboard

| Phase | Title | Status | Started | Completed | Notes |
|------:|-------|--------|---------|-----------|-------|
| 0 | Repository bootstrap | NOT STARTED | | | |
| 1 | Domain model, config, grain framework | NOT STARTED | | | |
| 2 | Input ingestion | NOT STARTED | | | |
| 3 | Canonical event model | NOT STARTED | | | |
| 4 | Snapshot validation (Mode B) | NOT STARTED | | | |
| 5 | Event-driven reconstruction (Mode A) | NOT STARTED | | | |
| 6 | Full rule catalogue, metrics, reconciliation | NOT STARTED | | | |
| 7 | Reports and CLI | NOT STARTED | | | |
| 8 | Testing, hardening, performance | NOT STARTED | | | |
| 9 | Packaging, documentation, release readiness | NOT STARTED | | | |

**Overall:** planning docs created; implementation not started.

**Rules status:** implemented 0 / 84 spec'd; backlogged 0; see §3.

---

## 1. How to use this document

- Each phase has: **goal**, **deliverables** (checkboxes), **acceptance
  criteria** (must all be true to mark DONE), and **exit gate**.
- Checking a deliverable requires evidence: a passing test, a produced file,
  or a command run with its output.
- Requirements traceability: each phase lists the `REQUIREMENTS.md` sections
  it fulfills. Changing requirements updates this plan in the same change.
- Defects found during a phase are fixed within that phase or logged in §5
  (Backlog) with a target phase — never silently dropped.
- Parallel-agent workstreams (per master prompt §20) are noted per phase; the
  lead integrator owns cross-module contracts and test failures.

---

## 2. Phase detail

### Phase 0 — Repository bootstrap

**Requirements:** §2 (decisions D1–D10), §17
**Goal:** a buildable, testable, empty package skeleton with tooling.

**Deliverables:**

- [x] Folder `rosterops/` created; `REQUIREMENTS.md`, `IMPLEMENTATION_PHASES.md`, `.gitignore`
- [x] Git repository initialized; initial commit of planning docs
- [ ] `pyproject.toml` (PEP 621, src layout, deps `polars`/`pydantic`/`pyyaml`, extras `[excel]`/`[dev]`, entry point `rosterops = rosterops.cli:main`)
- [ ] `src/rosterops/` skeleton with `__init__.py`, `__main__.py`, `exceptions.py`
- [ ] Tooling configured: `ruff` (lint+format), `mypy` (strict on `src/`), `pytest` + `pytest-cov`, `hypothesis`
- [ ] `tests/` tree (`unit/`, `integration/`, `rules/`, `property/`, `fixtures/`)
- [ ] CI workflow `.github/workflows/ci.yml` (matrix 3.10–3.13: lint, typecheck, test, build)
- [ ] `README.md` stub, `LICENSE` (MIT), `CHANGELOG.md` (Keep a Changelog), `SECURITY.md`, `CONTRIBUTING.md`

**Acceptance criteria:**

- `pip install -e ".[dev]"` succeeds on Python 3.10.
- `ruff check .`, `ruff format --check .`, `mypy src/` pass (even if trivially).
- `pytest` runs (0 tests collected is acceptable at this phase; must not error).
- `python -m rosterops --help` and `rosterops --version` work.
- `python -m build` produces wheel + sdist.

**Exit gate:** CI green on the skeleton.

---

### Phase 1 — Domain model, configuration, grain framework

**Requirements:** §4 (domain model), §5 (grain), §6.1–6.2 (interval + termination semantics), §9 (configuration)
**Goal:** the shared contracts every later phase depends on. **This phase's interfaces are frozen by review before Phases 2–6 start in parallel.**

**Deliverables:**

- [ ] Canonical schemas: employee, territory, assignment, event, leave interval, coverage record (typed; Polars schema constants + pydantic models where row-level validation is needed)
- [ ] `RosterConfig` with strict pydantic validation: `version`, `data.grain` (+ `grain_keys` for `custom`), `dates`, `policies` (incl. `leave`, `vacancy`, `events`), `rules` (id/enabled/severity/params), `inputs` (per-role mapping blocks), `outputs`, `meta.allow_unknown_fields`
- [ ] Config precedence: defaults < file < CLI overrides; resolved-config echo (for `run_metadata.json`)
- [ ] Grain framework: grain enum (`employee`, `employee_territory`, `employee_territory_assignment`, `custom`), grain-key resolution, GRN rule hooks
- [ ] Interval module: half-open `[from, to)` helpers, overlap/adjacency/gap primitives (sorted sweep), inclusive→exclusive end normalization
- [ ] Termination-date conversion for all three `termination_date_semantics` modes
- [ ] Exception hierarchy: `RosterOpsError` → `ConfigError`, `InputError`, `ReconstructionError`
- [ ] Rule contract (`rules/base.py`): RuleSpec (id, description, default severity, modes, params), Finding model (all §11.1 issue fields), deterministic ordering, registry with enable/severity overrides
- [ ] Example config `examples/config/generic_pharma.yaml` labeled illustrative
- [ ] Unit tests: config validation (unknown fields, bad severity, bad param types, rule id unknown), grain resolution, interval primitives, termination conversion (all 3 modes), rule registry/overrides

**Acceptance criteria:**

- Invalid configs produce `ConfigError` with precise messages (field path + reason).
- Interval tests prove: adjacent `[10-01,11-01)` + `[11-01,…)` do NOT overlap; `[10-01,10-31]` inclusive source normalizes to `[10-01,11-01)`.
- Termination semantics: for stated date 2026-10-20, active-through dates are 10-20 (inclusive mode), 10-19 (first-inactive mode), and exclusive-end = 10-20 (explicit mode) — each asserted.
- Every rule ID from REQUIREMENTS §8 exists in the registry exactly once with declared default severity and modes (registry-vs-spec consistency test).

**Exit gate:** code review of shared contracts; this doc's deliverables checked.

---

### Phase 2 — Input ingestion

**Requirements:** §7 (formats, mapping, lineage), §11.3 (safety), Group A rules
**Goal:** any supported file in → canonical raw frames + lineage + input findings.

**Deliverables:**

- [ ] `io/csv_reader.py` (lazy scan preferred), `io/parquet_reader.py`, `io/excel_reader.py` (calamine; graceful `ING-002` install-hint when extra missing)
- [ ] Format detection by extension; unsupported → `ING-002` listing supported formats
- [ ] Missing/unreadable required file → `ING-001`; optional role absent → skipped with note
- [ ] Excel: sheet existence → `ING-003`, empty workbook/sheet detection, header-row config, sheet selection (never assume first sheet)
- [ ] `mapping/canonical.py`: source→canonical column mapping + aliases, null tokens, per-field date format lists, categorical normalization tables, trim policy
- [ ] Lineage columns attached to every row (`source_file`, `source_sheet`, `source_row`); parse failures → findings, **no row silently dropped**
- [ ] Leading-zero identifier preservation (string keys end-to-end; regression test with `007`, `00123`)
- [ ] `SCH-001..005` raised from the mapping layer (SCH-005 ambiguity check before any load)
- [ ] Unit tests: all readers, unreadable/malformed/empty inputs, missing sheet, bad date cell located by row, extra-column warning, alias resolution, null-token handling

**Acceptance criteria:**

- Each test for ING-001/002/003, SCH-001/002/003/004/005 passes with file/sheet/row/column context asserted.
- CSV and Parquet paths pass with only core deps installed; Excel tests skip cleanly without `[excel]` and pass with it.
- No test observes a dropped row; parse-failure fixtures yield findings equal to failure-row count.

**Exit gate:** ingestion contract stable; Phase 3 can consume canonical frames.

---

### Phase 3 — Canonical event model

**Requirements:** §4.4 (events), §6.3 (normalization steps 1–4), Groups B (ID-002/007), C (DAT-006/007/008)
**Goal:** all eight event types normalized into one ledger with identity, dedupe diagnostics, and date conversion.

**Deliverables:**

- [ ] Normalizers for `transfer`, `promotion`, `termination`, `leave_start`, `leave_return`, `hire`, `rehire`, `temp_coverage`
- [ ] Event identity: source `event_id` + namespace; deterministic fingerprint for cross-file duplication (ID-007)
- [ ] Dedupe diagnostics: never silently drop; duplicates become findings and are excluded from application per policy
- [ ] Baseline cutoff filter: events on/before `baseline_date` → `DAT-006` (reject per `policies.events.reject_events_on_or_before_baseline_date`)
- [ ] Same-date conflict detection (DAT-007) with explicit policy hook; applied order recorded
- [ ] Termination date → canonical interval conversion wired into events (DAT-008)
- [ ] Leave-end vs separate return-event reconciliation: one authoritative representation; double-count prevention (per §10 note)
- [ ] Unit tests per event type + dedupe + cutoff + conflict ordering

**Acceptance criteria:**

- Round-trip test: fixture event files → ledger equals expected canonical ledger exactly (including lineage fields).
- Same fixture shuffled row order → identical ledger and identical conflict findings (determinism test).
- Duplicate-across-files test triggers ID-007 with both sources cited.

**Exit gate:** ledger format frozen; Phases 4–6 may proceed in parallel.

---

### Phase 4 — Snapshot validation (Mode B)

**Requirements:** §3.2, §5.2, §11.1 (`not_available`), Groups A/B/D/E-lite/H/J/L + temporal where intervals exist
**Goal:** `engine.validate_snapshot(...)` fully implements the single-file mode with honest metric limits.

**Deliverables:**

- [ ] Baseline/snapshot load → canonical frames → rule execution pipeline (registry-driven, deterministic order)
- [ ] Rules implemented in this phase: GRN-001/002/003, ID-001, ID-003, ID-004, ID-005, DAT-001, DAT-002, DAT-003, DAT-004 (policy-gated), EMP-006, EMP-008, TRF-009, TER-001..006, TER-008, TER-009, ORG-001..005, REC-005, REC-007 (snapshot branch), PRO-006
- [ ] `result.vacancies` computed when territory master present (TER-005/006/007 partial)
- [ ] Metric availability engine: transfer/promotion/leave/termination counts returned as `null` + `not_available` + reason in Mode B (tested)
- [ ] Two-snapshot comparison marked **deferred** (REC-008 backlogged unless pulled forward)

**Acceptance criteria:**

- Valid snapshot → 0 errors, findings only for genuine warnings.
- Grain-mismatch fixture (`grain: employee` + duplicate employee rows) → GRN-001 with both row numbers.
- Overlapping primaries fixture → TER-002/DAT-003 with intersecting interval in message.
- Self-managing manager → ORG-002; 2-node cycle → ORG-003 naming members.
- Inactive / no-owner-required territory unassigned → NOT in vacancy counts (TER-006), required-owner territory unassigned → in counts (TER-005).
- Snapshot-only summary contains `not_available` for every historical movement metric (assert no fabricated numbers).

**Exit gate:** Mode B feature-complete per §3.2; exit-code 0/1 behavior demonstrable.

---

### Phase 5 — Event-driven reconstruction (Mode A)

**Requirements:** §3.1, §4.5–4.6, §6.3–6.4, Groups D/E/F/G/I lifecycle + reconstruction
**Goal:** baseline + events → correct as-of state; reconstruction is the product's core.

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

- §10 scenario: reconstructed roster matches expected final state (E001 primary T400 + role SENIOR_REP from 10-15; E002 primary T200 on leave then returned; E003 inactive from 10-21; assignments closed correctly).
- Re-run byte-identical (excluding metadata timestamps): determinism test.
- Event dated ≤ baseline → excluded + DAT-006, state unchanged (property test).
- Transfer fixture with source ≠ effective assignment → TRF-002; transfer to unknown territory → TRF-004; transfer T100→T100 → TRF-003.
- Termination + transfer same employee/date → DAT-007 flagged, no arbitrary resolution.

**Exit gate:** reconstruction correctness proven on §10 before Phase 6 metrics depend on it.

---

### Phase 6 — Full rule catalogue, metrics, reconciliation

**Requirements:** §8 (all groups incl. REC-*), §9, §10
**Goal:** 100% of spec'd rules implemented or explicitly backlogged; metrics and reconciliation complete.

**Deliverables:**

- [ ] Remaining rules: REC-001..004, REC-006, LOA-007..009, DAT-006 enforcement edge cases, and any rules deferred from Phases 4–5
- [ ] Movement metrics module (`metrics/movements.py`): starts/ending active headcount, hires/rehires/terminations, transfer events + per-territory ins/outs (1 event ⇒ 1 out + 1 in, TRF-008), promotion events, leave starts/returns/currently-on-leave (LOA-009/010)
- [ ] Vacancy engine: dated vacancy intervals by kind (permanently_unassigned, after_transfer, after_termination, coverage_required, coverage_missing, unassigned_by_design); TER-007 interval math
- [ ] Coverage analysis: LOA-007 requirements, COV-004 capacity
- [ ] Reconciliation (`engine/reconciliation.py`): REC-001 formula with applicability guard (documented refusal when model assumptions violated), REC-002..005, REC-007 consistency; structured `result.reconciliation`
- [ ] Per-rule counts + deterministic finding sort in `result.summary`
- [ ] Severity overrides + disable flags proven to affect output (but not structural ING/SCH/GRN failures)
- [ ] Registry-vs-spec test from Phase 1 extended: **every §8 rule has ≥1 positive and ≥1 negative test**

**Acceptance criteria:**

- §10 scenario metrics equal the expected table exactly — computed, not hard-coded (test asserts values against independently written expectations).
- REC-001: `3 + 0 + 0 − 1 = 2` ✓; transfers/promotions/leave shown as headcount-neutral in the ledger tests.
- Rule coverage report: 84 spec'd → implemented + tested, or listed in §5 Backlog with reason and target phase.
- Vacancy fixture asserts T100 and T300 vacant, T400 occupied, T200 not vacant (E002 on leave ≠ vacancy).

**Exit gate:** `Implemented 84 (or backlog entries documented)` — no silent gaps.

---

### Phase 7 — Reports and CLI

**Requirements:** §11 (outputs), §12 (API), §13 (CLI), §11.3 (report safety)
**Goal:** user-facing surfaces: CLI commands, typed result object, all writers.

**Deliverables:**

- [ ] `RosterEngine` public API: `process()`, `validate_snapshot()`, `RosterConfig.from_file()`, `RosterEngine.from_file()`; DataFrame inputs accepted; caller frames not mutated (test)
- [ ] CLI: `rosterops process|validate|validate-inputs|rules list|rules describe <ID>|--help|--version` with flags per §13
- [ ] Exit codes 0/1/2 per §13 incl. `--fail-on-warning` (tested via subprocess)
- [ ] Console report: inputs, dates, rows per input, event counts by type, headcount, assignments, vacancies, rule counts, reconciliation, output paths, top findings — no full employee rows
- [ ] Writers: `csv_report.py` (CSV + `validation_issues.csv`, `movement_summary.csv`, `vacancy_report.csv`), parquet outputs, `json_report.py` (`reconciliation.json`, `run_metadata.json` with config echo, file hashes, versions), `excel_report.py` (10 sheets per §11.2, skips with documented reason without `[excel]`)
- [ ] Output safety: refuse writing into input dirs; existing output dir requires `--overwrite`; deterministic outputs
- [ ] `validate-inputs` runs config + ING/SCH checks without reconstruction
- [ ] API/CLI integration tests incl. exit-code matrix

**Acceptance criteria:**

- §13 commands all function on the §10 fixtures; exit codes asserted: clean run → 0; injected ERROR rule → 1; bad config → 2.
- Output file set matches §11.2; Mode B omits unavailable reports with reason in metadata.
- `rosterops_report.xlsx` opens with expected sheet names (openpyxl read-back test) when `[excel]` installed.
- Input file hashes unchanged after every test run (no-mutation test).

**Exit gate:** CLI + reports end-to-end green on fixtures.

---

### Phase 8 — Testing, hardening, performance

**Requirements:** §16 (all), §15 (performance)
**Goal:** complete test matrix, property tests, E2E, benchmarks; defects fixed.

**Deliverables:**

- [ ] **Invalid-variant integration matrix** (each → expected rule ID(s)):

  | # | Variant | Expected rule(s) |
  |---|---------|------------------|
  | 1 | Unknown employee in transfer | ID-006 / TRF-001 |
  | 2 | Nonexistent destination territory | TRF-004 |
  | 3 | Transfer source ≠ baseline assignment | TRF-002 |
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
  | 16 | Event effective ≤ baseline date | DAT-006 |
  | 17 | Same event in two input files | ID-007 |
  | 18 | Snapshot mode asked for movement counts | REC-007 `not_available` |
  | 19 | Assignment interval end < start | DAT-002 |
  | 20 | Leave with overlapping incompatible leave | LOA-003 |

- [ ] Property-based tests per REQUIREMENTS §16 (hypothesis), including preconditions for valid exceptions
- [ ] E2E from clean venv: build wheel → install → run CLI on examples → verify §10 outputs, rule IDs, exit codes → run outside source checkout
- [ ] Benchmarks: synthetic 10k / 100k / 1M assignment rows — record wall time + peak memory **actually measured** in §4 of this doc; investigate regressions
- [ ] Coverage gate: ≥90% statements on `src/rosterops/` core + rules; ruff + mypy strict clean
- [ ] Security/privacy pass: no PII in logs/metadata (grep-level test on fixtures), no network calls, input immutability, output-path confinement
- [ ] Determinism audit: repeated runs → identical logical outputs

**Acceptance criteria:** all matrix rows have passing tests; benchmarks recorded with environment details; coverage gate met; zero skipped-without-reason tests.

**Exit gate:** quality gates green; only release chores remain.

---

### Phase 9 — Packaging, documentation, release readiness

**Requirements:** §17, §18, §19 (definition of done)
**Goal:** a releasable package whose docs match its behavior.

**Deliverables:**

- [ ] `README.md` complete (purpose, users, modes, formats, install, quickstarts for both modes, sample reports, config basics, CLI, limitations, dev/test)
- [ ] `docs/`: architecture, data model, rule catalogue (**generated/verified against registry** — documented = implemented), configuration, effective dates, troubleshooting
- [ ] `examples/`: inputs, config, expected outputs + `examples/README.md` (§10 scenario runnable via one command)
- [ ] `CHANGELOG.md` entry for 0.1.0; `SECURITY.md` (data handling, permissions, retention guidance); `CONTRIBUTING.md`
- [ ] Wheel + sdist build; install into clean venv from artifacts; CLI + import outside checkout verified
- [ ] CI matrix green (3.10–3.13): lint, format, mypy, pytest, coverage, build
- [ ] Release-readiness checklist (REQUIREMENTS §17) executed and pasted into §4 below with real results
- [ ] Rule-count audit: advertised (README/docs) = implemented = tested; deferrals listed
- [ ] **No publish/push without explicit authorization**

**Acceptance criteria:** every REQUIREMENTS §19 item has linked evidence; known-limitations section written honestly.

**Exit gate:** v0.1.0 ready; dashboard fully `DONE` or explicit deferrals recorded in §5.

---

## 3. Rule implementation tracking (target phase → status)

Target phase is where the rule's positive/negative tests must land.

| Group | Rules | Target phase | Implemented | Tested |
|-------|-------|--------------|-------------|--------|
| A — Input/schema (8) | ING-001..003, SCH-001..005 | 2 | 0/8 | 0/8 |
| B — Identifiers (7) | ID-001..007 | 2–3 | 0/7 | 0/7 |
| C — Temporal (8) | DAT-001..008 | 4–5 | 0/8 | 0/8 |
| D — Employment (8) | EMP-001..008 | 4–5 | 0/8 | 0/8 |
| E — Transfers (9) | TRF-001..009 | 5–6 | 0/9 | 0/9 |
| F — Promotions (6) | PRO-001..006 | 5–6 | 0/6 | 0/6 |
| G — Leave (10) | LOA-001..010 | 5–6 | 0/10 | 0/10 |
| H — Territory (9) | TER-001..009 | 4–6 | 0/9 | 0/9 |
| I — Coverage (5) | COV-001..005 | 5–6 | 0/5 | 0/5 |
| J — Hierarchy (5) | ORG-001..005 | 4 | 0/5 | 0/5 |
| K — Reconciliation (8) | REC-001..008 | 6 | 0/8 | 0/8 |
| L — Grain (3) | GRN-001..003 | 1/4 | 0/3 | 0/3 |
| **Total** | **84** | | **0/84** | **0/84** |

---

## 4. Evidence log (append executed results here — never transcribe unexecuted results)

| Date | Command / check | Result |
|------|-----------------|--------|
| 2026-10-20 | `git init` + planning docs committed | PASS (initial commit) |
| | *(later phases append: pytest run IDs, coverage %, ruff/mypy outputs, build logs, benchmark numbers with machine details)* | |

---

## 5. Backlog / deferred items

Items intentionally not in the initial implementation, with reason and
revisit trigger. Nothing here may be advertised as available in docs/README.

| ID | Item | Reason | Revisit trigger | Target |
|----|------|--------|-----------------|--------|
| DEF-001 | Two-snapshot comparison mode (REC-008 full, §3.3) | Not needed for MVP modes A/B | Customer has paired historical snapshots | post-0.1.0 |
| DEF-002 | Manifest/directory ingestion (§3.4) | Explicit CLI paths suffice for MVP | Repeated multi-file runs / automation demand | post-0.1.0 |
| DEF-003 | Timestamp-with-timezone sources (beyond date-only + preserve) | Date-effective domain | Source system emits event timestamps | post-0.1.0 |
| DEF-004 | Pandera as optional schema helper | Internal rule engine covers domain checks | Reuse demand for generic schemas | optional |
| DEF-005 | Docs site (mkdocs) | Markdown in-repo adequate for MVP | Public release | post-0.1.0 |
| DEF-006 | Inferred-event labeling from snapshot diff (INF-* rules) | Tied to DEF-001 | DEF-001 active | post-0.1.0 |

**Open questions:** none — decisions D1–D10 in REQUIREMENTS §2 resolved all
planning questions. New ambiguity during implementation → choose configurable
default, document here, continue (per master prompt §1).

---

## 6. Definition-of-done checklist (final acceptance)

Copied from REQUIREMENTS §19; each box requires evidence in §4.

- [ ] Clean-env install + CLI outside source tree
- [ ] Mode A multi-file processing works end-to-end
- [ ] Mode B single-file validation works; historical metrics `not_available`
- [ ] Temporary coverage ≠ permanent transfer, enforced by tests
- [ ] Date semantics unit-tested for every configured mode
- [ ] All 84 rules implemented or backlogged with rationale (§5); zero advertised-but-missing
- [ ] §10 scenario: expected roster, counts, vacancies reproduced from data
- [ ] 20-row invalid-variant matrix green (§8 in phases = table above)
- [ ] CSV/Parquet/JSON tested; Excel tested with `[excel]`
- [ ] Exit codes 0/1/2 verified by subprocess tests
- [ ] Inputs unmodified; no PII leakage in logs/metadata
- [ ] Benchmarks measured and recorded (§4) with environment
- [ ] Docs match behavior; known limitations stated honestly
- [ ] CI green on 3.10–3.13; ruff + mypy strict + coverage gate pass
- [ ] Wheel + sdist build and install verified
