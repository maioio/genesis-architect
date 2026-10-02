# `genesis gate` — The Rules Engine

**Pro.** A deterministic architecture-regression check you can run in CI. It reads
your rules, gathers facts from the analysis engines (read-only), evaluates the
gates, and exits with a status code.

```bash
genesis gate --dir .            # human-readable report
genesis gate --dir . --json     # machine-readable report
```

## Exit codes

| Code | Meaning |
|:----:|---------|
| `0` | All gates passed (or shadow mode, see below) |
| `1` | One or more gates failed (block the merge) |
| `2` | Configuration / execution error |

## How it works

```python
from genesis_architect_pro.rules_engine import run_check
report = run_check(".")          # load_rules → gather_facts → evaluate
```

- **`load_rules`** reads `.genesis/rules.json` (or `rules.yml`).
- **`gather_facts`** pulls read-only signals from the score, anti-pattern, and
  recovery engines.
- **`evaluate`** checks each gate; **`format_report`** renders the result.

## Enforcing vs shadow

- **Enforcing:** the project ships `.genesis/rules.json`. Those rules are the
  policy and a violation exits `1`.
- **Shadow:** no rules file. A small default ruleset (no circular dependencies,
  no CRITICAL anti-patterns, no unpinned CI actions) is evaluated and reported,
  but never fails the run. It shows what a policy would catch without blocking
  anyone who has not opted in.

## Example `rules.json`

```json
{
  "_comment": "Start lenient and ratchet up.",
  "min_architecture_score": 70,
  "allow_circular_dependencies": false,
  "max_critical_anti_patterns": 0,
  "max_drift_score": 30
}
```

Only the rules you list are checked. The full list, with types, is in the
`rules_engine` module docstring. The main ones are:

| Rule | Type | Passes when |
|------|------|-------------|
| `min_architecture_score` | int | score ≥ value |
| `allow_circular_dependencies` | bool | `true`, or there are no import cycles |
| `max_critical_anti_patterns` / `max_high_anti_patterns` | int | count ≤ value |
| `max_unpinned_actions` | int | CI actions on a mutable ref ≤ value |
| `max_drift_score` | number | drift score ≤ value |
| `max_risk_level` | str | risk ≤ value (`none` < `low` < `medium` < `high` < `critical`) |

### History rules

These read `git log` or `.genesis/score_history.jsonl`. They are gathered only
when listed, and with no history they are reported as **skipped**, not passed.

| Rule | Passes when |
|------|-------------|
| `bus_factor_min` (`2` or `"2_per_module"`) | every file changed in the window has at least that many authors |
| `score_not_declining_over` (`"4_weeks"`, `"28_days"`, or an int in weeks) | the score now is ≥ the score at the window start (`score_decline_tolerance` allows a drop) |
| `max_change_coupling` (0..1) | no file pair co-changes above that confidence (`change_coupling_min_cochanges` defaults to 3; test files are exempt by default) |

### Temporal regression rules

These compare the current run against the **last prior run** recorded in
`.genesis/score_history.jsonl` (the record written just before this one, never
the run's own just-appended entry). With no prior run to compare against, the
rule is reported as `INSUFFICIENT_HISTORY` — a distinct, non-failing status,
never a silent `PASS`.

| Rule | Passes when |
|------|-------------|
| `max_score_decline` (number ≥ 0) | `baseline.total - current.total <= value` |
| `max_cycle_count_increase` (int ≥ 0) | `current.cycle_count - baseline.cycle_count <= value` |

### Typos fail

A key the engine does not know fails as `unknown rule - not evaluated`, with
the closest known name as a hint (`did you mean 'min_architecture_score'?`).
A rule value that cannot be parsed also fails. A misspelled policy must not read
as a passing one. Keys that start with `_` or `$` (`_comment`, `$schema`) are
treated as annotations and ignored.

## In CI

```yaml
- run: genesis gate --dir .      # exit 1 fails the job
```

See [Set Up a CI Architecture Gate](41_workflow_ci_gate.md) for a full workflow.

The gate is the **Validation** step of the [Thinking Loop](03_thinking_loop.md)
made enforceable.
