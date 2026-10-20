# Contributing to rosterops

## Development setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
```

## Quality gates (run before submitting changes)

```bash
ruff check .
ruff format --check .
mypy src
pytest                        # unit + rules + property + integration
```

CI runs the same gates on Python 3.10–3.13.

## Guidelines

- Requirements live in `REQUIREMENTS.md`; progress in `IMPLEMENTATION_PHASES.md`.
  A behavior change updates both in the same change.
- Every rule needs a stable ID, at least one positive and one negative test,
  and documentation that matches the code. Never advertise an unimplemented rule.
- Domain decisions (date semantics, grain, policy defaults) are configuration,
  not hard-coded facts. When ambiguity appears, pick a configurable default,
  document it, and log it in the phases tracker backlog.
- Use synthetic data only in tests and examples. Never commit real roster data.
- Findings must carry source lineage (file, sheet, row, column) wherever known.
