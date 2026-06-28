# Architecture Engine

Core architecture analysis (basic level in **Free**, full depth in **Pro**).

## Capabilities

- **Import graph** — multi-language dependency graph (Python, JS, TS, Go, Rust),
  cycle detection, layer mapping, dark-module (orphan) detection, fan-in/out.
- **Architecture score (0–100)** — Modularity, Coupling, Cohesion, Layering, with
  a cycle penalty. Free uses a basic profile; Pro adds 6 adaptive profiles
  (`default`, `frontend-spa`, `backend-monolith`, `microservices`,
  `data-pipeline`, `library`). Score history is tracked over time.
- **Anti-pattern detection** — structural anti-patterns (God Class, etc.) via
  pure graph analysis (no LLM). Free ships the core set; Pro adds the full set
  with severity ranking.
- **C4 diagrams** — Context/Container/Component views.
- **Drift detection (Pro)** — compares the live structure against the intended
  architecture baseline (ADRs) and flags divergence.

## Worked example

```python
from genesis_architect_pro.architecture_scorer import score_project, score_label
s = score_project(".")
print(s["total"], score_label(round(s["total"])))   # e.g. 82 GOOD
print({k: s[k] for k in ("modularity", "coupling", "cohesion", "layering")})
```

The Architecture Engine feeds the [Knowledge Graph](25_knowledge_graph.md)
(module + anti-pattern + drift nodes) and the [Recovery Engine](21_recovery_engine.md).
