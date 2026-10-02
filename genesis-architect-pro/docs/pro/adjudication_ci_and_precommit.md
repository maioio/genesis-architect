# Adjudication: G-HIGH-08 (GitHub Actions adapter) and G-HIGH-09 (pre-commit hook)

**Date:** 2026-10-02 · **Status:** decided, not implemented · **Source spec:**
[`CAPABILITY_GAP_REPORT.md`](CAPABILITY_GAP_REPORT.md) (G-HIGH-08, G-HIGH-09)

Both items add a capability that acts on the outside world: one posts to a pull
request, the other writes into `.git/hooks`. Under the governance rules in force
for this repo, a new integration needs a record covering value, cost, risk, a
lighter alternative, and a verdict before any code is written. This is that
record. No workflow file and no hook file are added by it.

Status tags: `(verified: <artifact>)` was checked this session against the named
artifact; `[assumed: … - if wrong: …]` is a default, listed again in the ledger
at the end.

---

## G-HIGH-08: GitHub Actions adapter

**As specified:** a `github-action.ts` that reads `GITHUB_EVENT_PATH`, fails the PR
when rules are violated, and posts the report as a PR comment.

### Value

Most of it already exists.

- `genesis gate --dir . [--json]` exits `0` on pass or shadow, `1` when an
  explicit policy fails, `2` on error (verified: `cli/analysis_cmds.py`
  `cmd_gate`, and a run through the `genesis` console entry point on this repo,
  rc 0 in shadow mode).
- A failing exit code is enough to fail a GitHub Actions job and block a merge
  under branch protection. `docs/pro/guide/41_workflow_ci_gate.md` documents a
  `pull_request` workflow that does this (verified: guide 41).
- What the spec adds beyond that is the PR comment and the event parsing.

### Cost

- A TypeScript action inside the Python package, plus building and publishing
  it. The repo's only Node project today is the companion app
  (`companion/app/package.json`); the gate and the CLI are Python
  (verified: `git ls-files`, `pyproject.toml`).
- A second build and release path for a CI convenience, with its own
  dependency tree to keep current.

### Risk

- **Externally visible writes.** Posting a PR comment is an automatic,
  externally visible act and needs `pull-requests: write` on the job token.
- **Fork PRs.** `[assumed: on the pull_request event, PRs from forks get a
  read-only token, so a comment step fails there and the usual workaround is
  pull_request_target, which runs with write access against untrusted code - if
  wrong: the comment works on fork PRs without that event; checked: the first
  real fork PR against a repo using the action]`
- **Noise.** A comment on every push to every PR becomes spam unless the action
  also edits or deduplicates its own comments, which is more code.
- **Supply chain.** A published action is something downstream repos pin and
  trust; it becomes part of their supply chain.

### Lighter alternative

A plain `pull_request` job, documented rather than shipped:

```yaml
on: [pull_request]
permissions:
  contents: read
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-commit-sha>
      - uses: actions/setup-python@<full-commit-sha>
      - run: pip install <genesis-pro-install-source>
      - run: genesis gate --dir .
```

- Read-only token, no comment, no Node.
- The gate's output is in the job log. `[assumed: writing the report to
  $GITHUB_STEP_SUMMARY shows it on the run page without any write permission -
  if wrong: the log is the only place it appears; checked: the first time the
  summary step is added to a real workflow]`

### Verdict

**REJECT as specified.** The fail-the-PR half already exists through the exit
code; the comment half adds a write permission, a fork-PR trap and a second
build and release path for a convenience.

**Done instead, in this branch:** guide 41 now uses `permissions: contents:
read`, shows actions pinned to a full commit SHA, runs `genesis gate --dir .`,
and uses a rules example made of supported keys only.

**Flagged, not changed:**

- Guides 40, 41, 50, 61 and the README tell users to run `pip install
  genesis-architect-pro` (verified: grep of `README.md` and
  `docs/pro/guide`). That name returned HTTP 404 from the PyPI JSON API
  (verified: PyPI JSON API, 2026-10-02). An unclaimed name in install
  instructions can be registered by anyone. Reserving it, or changing the
  documented install source, is the owner's call.
- `.github/workflows/genesis-sync.yml` runs on a weekly cron with `contents`,
  `pull-requests` and `issues` set to `write` (verified: the workflow file).
  Its actions are SHA-pinned. Whether it needs all three write scopes was not
  reviewed here.

---

## G-HIGH-09: pre-commit boundary hook

**As specified:** a project-specific pre-commit hook that runs the rules engine
on staged files only, fails the commit on boundary violations, and reports
exactly which rule and which file.

### Value

Faster feedback than CI, before a commit exists.

### Cost and feasibility

- **"Staged files only" does not fit the engine.** Every rule is a
  project-level aggregate (architecture score, cycle count, anti-pattern
  counts, drift, coupling). `RuleResult` carries `rule, passed, expected,
  actual, message` and no file (verified: `rules_engine.py` `RuleResult`).
  Scoring a subset of files would give a different, meaningless number.
- **"Which file" needs file-level rules.** Naming the file requires boundary
  rules of the form "module A must not import module B", which the engine does
  not have. Adding them is its own capability and needs its own adjudication.
- **Run time.** `python -m genesis_architect_pro.rules_engine .` took 2.1–4.7 s
  on this repo, rc 0 (verified: timed runs earlier in this session). Tolerable
  for a hook, but on every commit.

### Risk

- A hook installer writes into `.git/hooks`, which is a mutating command and
  would have to be dry-run by default with `--apply`.
- `git commit --no-verify` skips the hook, so it cannot be the enforcement
  point. CI is.
- The repo has no `.pre-commit-config.yaml` today (verified: file absent), so
  there is no existing hook framework to plug into.

### Lighter alternative

Document a user-side local hook for the pre-commit framework that runs the
whole-project gate and ignores the file list:

```yaml
- repo: local
  hooks:
    - id: genesis-gate
      name: genesis gate
      entry: genesis gate --dir .
      language: system
      pass_filenames: false
```

### Verdict

**REJECT the hook as specified; DEFER file-level boundary rules** to their own
adjudication. The whole-project gate is already runnable from any hook a user
wants to add, and the requirement that makes this item distinct (staged files,
named file) needs rules the engine does not have.

---

## Found during this adjudication

Reading the rules engine for this record turned up a defect. `evaluate()` only
looked up the key names it knew, so an unknown key was skipped silently. The
example `rules.json` in guides 27 and 41 used `max_cycles`, `max_god_classes`
and `fail_on_drift`; none of them was ever evaluated, and those policies passed
without checking cycles, god classes or drift.

Fixed in this branch: an unknown key now fails as `unknown rule - not
evaluated` with a closest-match hint, a rules file that is not an object fails,
and keys starting with `_` or `$` are treated as annotations. A project whose
rules file carries an unknown key now exits `1` where it used to pass.

---

## Assumptions ledger

| ID | Assumption | Basis | Blast radius if wrong | Where it is checked |
|----|-----------|-------|-----------------------|---------------------|
| A1 | Fork PRs on `pull_request` get a read-only token, pushing a comment step toward `pull_request_target` | Common GitHub Actions guidance; not checked live this session | The comment path is safer than stated; the verdict still holds on cost and noise | First real fork PR against a repo using such an action |
| A2 | `$GITHUB_STEP_SUMMARY` shows a report on the run page with no write permission | Common GitHub Actions guidance; not checked live this session | The report stays in the job log only; the alternative loses a convenience, not its gate | First workflow that writes a summary step |
| A3 | Keys starting with `_` or `$` are annotations | Matches the `_comment` / `$schema` convention; no engine rule uses either prefix | A real rule with such a prefix would be skipped | `test_known_keys_cover_every_key_the_engine_reads` |
| A4 | Unknown keys fail the gate rather than warn | The module's own "a typo must not read as compliance" rule | Projects carrying stale keys fail CI until the key is fixed | First downstream run after this change ships |
| A5 | `max_god_classes` has no supported equivalent | No god-class count rule exists in `KNOWN_RULE_KEYS` | The guide could map it instead of dropping it | Review of the anti-pattern facts the engine gathers |
