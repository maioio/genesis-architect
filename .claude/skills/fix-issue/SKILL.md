---
name: fix-issue
description: Fix a GitHub issue end to end -- read it, reproduce, patch, add a regression test, verify, and open a PR. Use when given an issue number or URL in this repo.
disable-model-invocation: false
argument-hint: "<issue-number-or-url>"
---

Given an issue number or URL in this repository:

1. `gh issue view <issue>` to read the report in full, including comments.
2. Reproduce the problem locally before changing anything -- write a failing
   test if one doesn't already exist that captures it.
3. Make the smallest change that fixes the root cause, not just the symptom.
4. Run `python -m pytest -q` and `ruff check .` and confirm both are clean.
5. Commit referencing the issue (`Fixes #<issue>` in the body), push a branch
   named `fix/<issue-number>-<short-slug>`, and `gh pr create` linking the
   issue.
6. Report what changed and link the PR. Do not merge -- that is the owner's
   call.
