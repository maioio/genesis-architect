# Knowledge Graph Engine

**Pro.** The flagship differentiator: it links the islands of knowledge the other
engines produce into one queryable graph, so Genesis can answer **connective**
questions no single engine can.

## What it does

The other engines produce isolated facts — a CVE here, a Reddit pain point there,
a decision, a god class. The Knowledge Graph connects them:

- *"Which do-not-touch zones have an open CVE?"*
- *"Which decisions does new drift contradict?"*
- *"Did a community warning predict this drift?"*

## Data model

A directed, attributed graph:

```
KnowledgeGraph
  nodes: { id -> { type, label, metadata } }
  edges: [ { src, rel, dst, confidence, evidence_ref? } ]
```

Node types include `module`, `anti_pattern`, `drift`, `cve`, `package`, `risk`,
`decision`, `evidence`, `field_finding`, `test`. Relationship types include
`affects`, `used_by`, `located_in`, `detected_in`, `supports`, `warns_about`,
`covers`.

**Every edge carries a confidence in [0,1]** (honesty clause) and an optional
`evidence_ref`. A link with no basis is low-confidence by construction.

## How it is built

The graph is **additive and deterministic**. Each engine pass appends its
nodes/edges; the graph is the union, persisted to `.genesis/knowledge/graph.json`:

```
1. Architecture pass → module / anti-pattern / drift nodes + edges
2. Security pass      → cve → package → module chains
3. Recovery pass      → risk nodes (incl. do-not-touch) located in modules
4. Decision pass      → decision nodes, evidence → decision, decision → module
5. Field pass         → reddit/youtube findings → warns_about → pattern
```

Passing nothing returns the existing graph unchanged — it never fabricates.

## Worked example: do-not-touch zones with an open CVE

```python
from genesis_architect_pro import knowledge_graph as kg

g = kg.build_from_project(".",
    architecture={"modules": ["net"]},
    security={"cves": [{"id": "CVE-9", "package": "requests",
                        "modules": ["net"]}]},
    risks={"risks": [{"id": "r1", "label": "do-not-touch", "module": "net"}]})

cve_paths  = g.query(["cve", "affects", "package", "used_by", "module"])
risk_paths = g.query(["risk", "located_in", "module"])

danger = {p[-1] for p in cve_paths} & {p[-1] for p in risk_paths}
# -> {"module:net"}  — a frozen module that has a live CVE. Fix it first.
```

## API

```
add_node(id, type, label="", metadata=None)     # idempotent, merges metadata
add_edge(src, rel, dst, confidence=.5, evidence_ref=None)  # de-dups, keeps best
neighbors(id, rel=None, direction="out|in|both")
query(pattern)                                   # multi-hop connective paths
build_from_project(path, architecture=…, security=…, …, persist=True)
load_graph(path) / save_graph(graph, path)
```

## Free vs Pro

Pro-only. Free does not build the knowledge graph.
