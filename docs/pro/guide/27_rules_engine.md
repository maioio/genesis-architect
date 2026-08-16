# `genesis gate` — The Rules Engine

**Pro.** A deterministic architecture-regression check you can run in CI. It reads
your rules, gathers facts from the analysis engines (read-only), evaluates the
gates, and exits with a status code.

## Exit codes

| Code | Meaning |
|:----:|---------|
| `0` | All gates passed |
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

## Example `rules.json`

```json
{
  "min_architecture_score": 70,
  "max_cycles": 0,
  "max_critical_anti_patterns": 0,
  "max_god_classes": 2,
  "fail_on_drift": true
}
```

## In CI

```yaml
- run: pip install genesis-architect-pro
- run: python -m genesis_architect_pro.rules_engine .    # exit 1 fails the job
```

The gate is the **Validation** step of the [Thinking Loop](03_thinking_loop.md)
made enforceable.
