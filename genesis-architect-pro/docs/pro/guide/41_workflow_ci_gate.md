# Workflow: Set Up a CI Architecture Gate

Stop architecture regressions at the PR boundary with [`genesis gate`](27_rules_engine.md).

## 1. Define the rules

`.genesis/rules.json`:

```json
{
  "min_architecture_score": 70,
  "allow_circular_dependencies": false,
  "max_critical_anti_patterns": 0,
  "max_drift_score": 30
}
```

A key the gate does not know fails the run as `unknown rule - not evaluated`,
so a typo cannot pass silently. The supported rules are listed in
[the rules engine guide](27_rules_engine.md).

Start lenient, then ratchet thresholds up as the codebase improves — the score
history in `.genesis/` shows the trend.

## 2. Add the job (GitHub Actions)

```yaml
name: architecture-gate
on: [pull_request]
permissions:
  contents: read
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-commit-sha>        # v4
      - uses: actions/setup-python@<full-commit-sha>    # v5
        with: { python-version: "3.12" }
      - run: pip install "git+https://github.com/maioio/genesis-architect.git@<full-commit-sha>#subdirectory=genesis-architect-pro"
      - run: genesis gate --dir .
```

The job only reads the repository, so `contents: read` is all it needs. Replace
each `<full-commit-sha>` with the 40-character commit of the release you want
(the `pip install` line too; `genesis gate` ships only in the standalone Pro
distribution, which is installed from GitHub because it is not on PyPI):
a tag can be moved, a SHA cannot. The gate's own `max_unpinned_actions` rule
checks this.

Exit `1` fails the job and blocks the merge; `0` passes; `2` means a config
error. (Docker is **not** required — the gate is a pip package; Docker is an
internal dev/validation tool only.)

## 3. Read the result

The gate prints which rules passed and which failed, with the facts behind each
decision — gathered read-only from the analysis engines. No false positives from
guesswork: the check is deterministic.
