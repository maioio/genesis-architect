# Governance Foundation — Prototype v1 (ARCHIVED)

**Status:** Superseded. Historical reference only. **Do not import or use in production code.**

## What this was

This was the original **Governance Foundation** prototype (the "P1" foundation):
an orchestration skeleton that drives a task through the lifecycle
`INTAKE → PLAN → EXECUTE → GATE → REPORT → APPROVE → COMMIT`, with:

- a lifecycle state machine (`orchestrator.py`)
- an engine registry + `Engine` Protocol contract (`registry.py`, `contracts.py`)
- an approval-gate framework with the *dangerous-always-gated* rule (`gates.py`)
- a deterministic decision engine skeleton (`decision.py`)
- core types (`types.py`)
- its test suite (`test_governance_foundation.py`, 19 tests)

## Why it was archived

It has been **superseded by the Genesis Decision Engine (`gde_*`)**, the active
governance architecture (`gde_types.py`, `engine_registry.py`, `gde_session.py`).
The `gde_*` implementation is more complete: a richer type system, full lifecycle
stages, session persistence (`.genesis/gde_session.json` + an append-only decision
log), and a substantially larger test suite.

This prototype and `gde_*` were built in parallel and ended up covering the same
ground. To keep a single active implementation, this version was retired here
rather than deleted, so the design history is preserved.

## Rules

- **Do not import this package from production code.** It is intentionally outside
  the importable `src/` tree and is excluded from test discovery
  (`testpaths = ["tests"]`).
- Treat the contents as read-only history. Useful patterns worth porting to
  `gde_*` (e.g. the `Engine` Protocol contract and the dangerous-always-gated
  policy) should be re-implemented there, not imported from here.

## Contents

```
governance/                     the original package
  __init__.py
  types.py
  contracts.py
  registry.py
  gates.py
  decision.py
  orchestrator.py
test_governance_foundation.py   the original 19-test suite
```
