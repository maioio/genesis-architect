# Workflow: Set Up a CI Architecture Gate

Stop architecture regressions at the PR boundary with [`genesis gate`](27_rules_engine.md).

## 1. Define the rules

`.genesis/rules.json`:

```json
{
  "min_architecture_score": 70,
  "max_cycles": 0,
  "max_critical_anti_patterns": 0,
  "fail_on_drift": true
}
```

Start lenient, then ratchet thresholds up as the codebase improves — the score
history in `.genesis/` shows the trend.

## 2. Add the job (GitHub Actions)

```yaml
name: architecture-gate
on: [pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install genesis-architect-pro
      - run: python -m genesis_architect_pro.rules_engine .
        env:
          GENESIS_PRO_LICENSE: ${{ secrets.GENESIS_PRO_LICENSE }}
```

Exit `1` fails the job and blocks the merge; `0` passes; `2` means a config
error. (Docker is **not** required — the gate is a pip package; Docker is an
internal dev/validation tool only.)

## 3. Read the result

The gate prints which rules passed and which failed, with the facts behind each
decision — gathered read-only from the analysis engines. No false positives from
guesswork: the check is deterministic.
