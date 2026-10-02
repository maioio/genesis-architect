# Workflow: Recover a Legacy Codebase

End-to-end, the way Genesis runs it.

## 1. Point Genesis at the project

```bash
pip install genesis-architect-pro
```

Run the recovery flow (the Decision Engine drives it in `RECOVERY` mode). The
built-in engine adapters run in dependency order:

```
architecture → antipattern → recovery / knowledge_graph
```

## 2. What you get

- An **architecture score** + dimension breakdown.
- An **anti-pattern report** with severity.
- A **drift report** against the intended baseline.
- A **recovery report**: technical-debt map, CVE/security findings, test &
  doc gaps, quick wins, deep refactor plan, and a **phased roadmap**.
- A **Knowledge Graph** linking it all (`.genesis/knowledge/graph.json`).

## 3. Find what to fix first

```python
from genesis_architect_pro import knowledge_graph as kg
g = kg.load_graph(".")
cve = g.query(["cve", "affects", "package", "used_by", "module"])
risk = g.query(["risk", "located_in", "module"])
danger = {p[-1] for p in cve} & {p[-1] for p in risk}   # do-not-touch + CVE
```

## 4. Work the roadmap safely

Genesis proposes phases; the [Governance gate](26_governance.md) holds every
dangerous change for your approval. Each phase adds tests and re-runs the
[`genesis gate`](27_rules_engine.md) before moving on. Decisions and lessons are
written to `.genesis/` so the next session resumes with full context.
