---
name: repo-polish
description: Run the repo's lint, format-check and test suite, then fix anything that fails. Use before opening a PR or when asked to "polish" or "clean up" the repo.
disable-model-invocation: false
argument-hint: "[path or package, optional]"
---

Run, in order, stopping to fix and re-run on any failure before moving on:

1. `ruff check .` (or the given path) — fix lint violations directly in the
   flagged files; do not add blanket `# noqa` suppressions.
2. `ruff format --check .` — if it reports files that would reformat, run
   `ruff format .` and re-check.
3. `python -m pytest -q` (or scoped to the given path) — fix failing tests or
   the code they exercise; do not weaken an assertion just to make it pass.

Re-run all three once everything is green to confirm no step regressed
another. Report a short pass/fail summary per step, not raw tool output.
