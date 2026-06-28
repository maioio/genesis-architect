# Recovery Engine

**Pro.** Point Genesis at a legacy codebase and get a full project-intelligence
report — not just a graph, but a plan for what to fix and in what order.

## What it produces

- Service + dependency graph and architecture score
- **Drift report** — divergence from intended architecture
- Anti-pattern report (full set + severity)
- CVE / security report (via the [Security Engine](23_security_engine.md))
- **Technical-debt map** and **stale / risky module** list
- Test-gap and documentation-gap reports
- GitHub issue / PR / commit insights (deep git intelligence)
- **Quick wins**, a **deep refactor plan**, and **do-not-touch-yet risk zones**
- A **phased recovery roadmap**

## Worked example

```python
from genesis_architect_pro.recovery_report import generate_report_for_project
report = generate_report_for_project(".")
# report.architecture_health, report.drift_summary, report.recommendations, …
```

## Do-not-touch zones

The Recovery Engine marks modules that are too risky to change yet. Combined with
the [Knowledge Graph](25_knowledge_graph.md), Genesis can answer the question that
matters most during recovery: *which do-not-touch zone also has an open CVE?* —
the place you must fix first despite the risk.

## Free vs Pro

Recovery is **Pro-only** — one of the two headline upgrade reasons (with
Developer Field Intelligence).
