# Engine Adapters — Prototype v1 (ARCHIVED)

**Status:** Superseded. Historical reference only. **Do not import or use in production code.**

## What this was

`engine_adapters.py` (the "P-D" wiring) bridged 5 real engines (architecture,
antipattern, recovery, security, knowledge_graph) to the Genesis Decision Engine
runner's `fn(ctx) -> dict` contract, with `register_builtin_engines()`.

## Why it was archived

It was **superseded by the production GDE wiring**:
`gde_engine_adapters.py` + `gde_engine_registration.py`, which:

- wraps **8** production engines (import_graph, architecture_scorer,
  antipattern_detector, fragility_classifier, recovery_report,
  refactoring_planner, c4_generator, security_templates),
- is **registered into the default registry** and driven by
  `GenesisDecisionEngine.run()` (this prototype was standalone and not wired in),
- is covered by `tests/test_gde_production_wiring.py`.

The one capability this prototype had that the production wiring lacked — the
**Knowledge Graph adapter** — was **ported forward** into its own additive module
`gde_knowledge_graph_adapter.py` (registers `knowledge_graph` into the live GDE,
depending on `antipattern_detector`). So nothing of value was lost.

## Rules

- Do not import this package from production code. It lives outside the importable
  `src/` tree and is excluded from test discovery (`testpaths = ["tests"]`).
- Treat as read-only history.

## Contents

```
engine_adapters.py            the original 5-engine adapters + register_builtin_engines
test_engine_adapters.py       the original tests
```
