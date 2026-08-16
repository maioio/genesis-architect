# Genesis Architect Pro — v8.0.0

The intelligence layer for [Genesis Architect](https://github.com/maioio/genesis-architect).

The free core researches GitHub and scaffolds a working MVP. Pro adds deep codebase analysis,
a cross-source Knowledge Graph, and the Genesis Decision Engine — a 7-mode, 13-engine pipeline
that routes any plain-English instruction to the right analysis without an LLM guess.

## Codebase Intelligence Engines

| Engine | What it does |
|--------|--------------|
| **Import Graph** | Multi-language dependency graph (Python, JS/TS, Go, Rust) with cycle detection |
| **Architecture Scorer** | 0–100 quality score across 4 dimensions, 6 adaptive profiles, trend history |
| **Anti-Pattern Detector** | 7 structural detectors: god-class, hub-file, circular deps, dead code, and more |
| **Fragility Classifier** | STABLE / FRAGILE / VOLATILE per module — driven by git churn + test coverage |
| **Refactoring Planner** | Tier-1/2 refactor steps with projected score impact |
| **C4 Generator** | C4 Level 1–3 architecture diagrams (Mermaid, GitHub-native) |
| **Security Templates** | STRIDE threat model + OWASP Top 10 checklist, archetype-aware |
| **Knowledge Graph** | Links code, CVEs, risks, and decisions into one queryable graph |

## Genesis Decision Engine (GDE)

Routes any plain-English instruction across 7 modes and 13 engines, with a static gate policy:

| Mode | Engines | What happens |
|------|---------|--------------|
| `recovery` | 5 | Import graph → score → anti-patterns → fragility → recovery report |
| `research` | 3 | Source registry → field intelligence (Reddit Answers) → evidence pack |
| `refactor` | 5 | Import graph → score → anti-patterns → refactoring plan |
| `gate` | 5 | Import graph → score → anti-patterns → fragility → security gate |
| `build` | 1 | Delegates to genesis-architect free core scaffolder |
| `document` | 3 | Import graph → C4 diagrams + security templates |
| `committee` | 5 | Full analysis pass → multi-perspective synthesis + divergence report |

### Gate policy

Two gates can never be bypassed:
- `PLAN_WRITE` — hard block on any write targeting `planned.json`
- `RULES_FAIL` — hard block on rules engine hard failure

All other gates (CONFIDENCE_LOW, DRIFT_CRITICAL, SECURITY_RISK, WRITE_SCOPE, DEGRADED_MODE) are soft blocks, overridable with `--yes`.

## Install

```bash
pip install genesis-architect-pro
```

## CLI

```bash
# Full 7-stage pipeline: classify → plan → execute → gate → report → approve → commit
genesis decide "diagnose the project and identify drift"

# Classify only (no execution)
genesis decide --classify-only "generate C4 diagrams"

# Auto-approve all writes (CI mode)
genesis decide --yes "run a full recovery scan"

# Analysis without committing any files
genesis decide --no-commit "check compliance and security"

# Print decision log
genesis explain
```

## Python API

```python
from genesis_architect_pro import GenesisDecisionEngine
from pathlib import Path

gde = GenesisDecisionEngine(project_dir=Path("."))

# Full pipeline
report = gde.run("diagnose the project and identify drift")
print(f"Mode: {report.mode.value}")
print(f"Confidence: {report.overall_confidence:.2f}")
print(f"Gate: {report.gate_report.overall.value}")

# APPROVE + COMMIT
request = gde.approve(report)          # inspect pending writes
decision = request.auto_approve()      # or build ApprovalDecision manually
result = gde.commit(report, decision)  # atomic tmp → rename writes
```

## Direct engine access

```python
from genesis_architect_pro import (
    build_graph, score_project, detect_all,
    classify_all, generate_plan, generate_c4_doc,
    generate_security_docs,
)

graph  = build_graph("/path/to/project")
score  = score_project("/path/to/project")
issues = detect_all("/path/to/project")
frags  = classify_all("/path/to/project")
plan   = generate_plan("/path/to/project")
```

## License

AGPL-3.0. Fully open source — no license key, no gate. See LICENSE.
