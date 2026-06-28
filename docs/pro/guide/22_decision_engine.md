# Decision Engine

**Pro.** Turns alternatives + evidence into a recommendation — with trade-offs,
confidence, approval gates, and *"what would change this."* It is the brain that
drives the [Thinking Loop](03_thinking_loop.md).

## What it does

The Decision Engine orchestrates a task through the lifecycle
(`INTAKE → PLAN → EXECUTE → GATE → REPORT → APPROVE → COMMIT`), invoking the
registered engines for each phase and gating the consequential transitions.

It is fed by **engine adapters** — thin bridges that connect the real analysis
engines (architecture scorer, anti-pattern detector, recovery, security, the
knowledge graph) to a uniform contract:

```
fn(ctx) -> dict        # may report _confidence and _warnings
```

## Engine registry + ordering

Engines register an `EngineDescriptor` declaring their `id`, `modes`, `requires`
(dependencies), and whether they are optional. The registry:

- rejects duplicate ids and **detects dependency cycles**,
- topologically orders engines so dependencies run first,
- groups independent engines into parallel phases.

Example (from the shipped built-in adapters): `recovery` requires `architecture`,
and `knowledge_graph` requires `antipattern` — so the order is always
`architecture → antipattern → recovery / knowledge_graph`.

```python
from genesis_architect_pro import register_builtin_engines
from genesis_architect_pro.engine_registry import EngineRegistry

reg = EngineRegistry()
register_builtin_engines(reg)
assert reg.validate() == []          # deps satisfied, no cycles
```

## Graceful degradation

If an engine is unavailable or its source is empty, its adapter returns a
**low-confidence, degraded** result with a warning — the runner records it and
continues. Nothing is fabricated, and one failing engine never crashes the run.
Confidence penalties are applied per the spec (optional fail −0.10, required fail
−0.20, degraded −0.05).

## Decision output

A decision records: the choice, the alternatives considered, the evidence behind
it, a confidence level, *"what would change it,"* and whether the stakes are
close enough to warrant committee review. Confidence is never "high" without
supporting evidence (honesty clause).

## Free vs Pro

Decision basics exist in Free; the committee, Evidence-Pack wiring, and the full
engine orchestration are Pro.
