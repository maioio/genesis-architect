# Decision consistency

**Measured.** Not measured as a property. What exists is unit testing of the deterministic gate
logic that decisions pass through.

**Covered by tests.**

| Behavior | Tests |
|---|---|
| Gate thresholds and gate outcomes | `tests/test_gde_step5_gate_engine.py` |
| Intent classification | `tests/test_gde_step2_intent_classifier.py` |
| Planning and runner behavior | `tests/test_gde_step3_planner.py`, `tests/test_gde_step4_runner.py` |
| End-to-end entry point | `tests/test_gde_step6_entry_point.py` |

**Reproduce.**

```bash
GENESIS_NO_AUTO_INSTALL=1 pytest tests/test_gde_step2_intent_classifier.py tests/test_gde_step3_planner.py tests/test_gde_step4_runner.py tests/test_gde_step5_gate_engine.py tests/test_gde_step6_entry_point.py -q
```

**Expected.** All pass. For the tested inputs the gate outcome is deterministic.

**Gap.** No experiment repeats the same question, or runs it across model versions, and compares
the decisions. Any LLM-backed step can vary between runs. Treat run-to-run consistency of those
steps as unproven.
