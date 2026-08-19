---
applyTo: "custom_components/**,tests/**"
---

# TDD Red/Green/Refactor — Mandatory Agent Workflow

When adding or modifying any unit of code in `custom_components/` or `tests/`, you MUST follow the full red/green/refactor cycle. Do not skip or compress stages.

## Stage 1 — RED (Write failing tests first)

1. Identify the single unit to implement (one function, method, entity class, or coordinator method).
2. Write 1–3 tests that describe the expected behavior. Do **not** write any implementation code yet.
3. Run the tests and **confirm they fail**:
   ```bash
   pytest tests/<relevant_file>.py -x -v --tb=short
   ```
4. Verify the failure is for the right reason:
   - `ImportError` → module/function does not exist yet ✓
   - `AttributeError` → class/attribute does not exist yet ✓
   - `AssertionError` → wrong value returned ✓
   - Syntax error or unrelated crash → fix the test first ✗
5. If the tests **pass** without any implementation, the test is wrong — fix it until it fails correctly.
6. **Do NOT commit at RED.** The pre-commit hook blocks failing commits by design. This is correct.

## Stage 2 — GREEN (Write minimum implementation)

1. Write the smallest amount of implementation code that makes the failing tests pass.
2. No extra features, no edge-case handling beyond what the tests require.
3. Run the tests and **confirm they pass**:
   ```bash
   pytest tests/<relevant_file>.py -x -v --tb=short
   ```
4. If tests still fail, fix the implementation — do **not** modify the tests to force them to pass.

## Stage 3 — REFACTOR (Clean up)

1. Improve code quality: naming, structure, type hints, duplication.
2. Do **not** change observable behavior.
3. After every change, rerun:
   ```bash
   pytest tests/<relevant_file>.py -x -v --tb=short
   ```
   Tests must stay green after each individual change.

## Commit — After REFACTOR

Run the full suite and coverage check, then commit:

```bash
pytest tests/ --cov=custom_components.omada_open_api --cov-report=term-missing
git add <changed_files>
git commit -m "feat: <description> (TDD)"
```

Commit message **must** end with `(TDD)`. Examples:
- `feat: add gateway WAN sensor (TDD)`
- `fix: handle token expiry edge case (TDD)`
- `refactor: extract pagination helper (TDD)`

## Key Rules

- **Never write implementation before tests.** RED always comes first.
- **One unit per TDD cycle.** Complete RED→GREEN→REFACTOR before starting the next unit.
- **1–3 tests per cycle.** Never batch large test additions — defeats TDD discipline.
- **Pre-commit hook blocks RED commits by design.** Do not use `--no-verify` to bypass it.
- **Coverage must not drop.** The baseline in `.coverage-threshold` is enforced automatically.
