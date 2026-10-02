# Genesis Architect Pro v8.0.0

The intelligence layer for [Genesis Architect](https://github.com/maioio/genesis-architect).

> [!NOTE]
> **There is no paid tier any more.** Since genesis-architect v8.0.0 the Pro engines also ship,
> free, inside the main package as `genesis_architect.pro`, under AGPL-3.0. For most people
> `pip install genesis-architect` is all they need. This directory holds the standalone Pro
> distribution, where Pro development continues, so it can run slightly ahead of the copy in
> the main package (today: one extra engine, Supply Chain Audit, and one extra gate,
> `RESEARCH_EVIDENCE_UNKNOWN`). It is not published to PyPI; see [Install](#install).

Genesis Architect researches GitHub and scaffolds a working MVP. The Pro layer adds deep
codebase analysis, a cross-source Knowledge Graph, and the Genesis Decision Engine: a 7-mode,
19-engine pipeline that routes any plain-English instruction to the right analysis without an
LLM guess.

## Codebase Intelligence Engines

| Engine | What it does |
|--------|--------------|
| **Import Graph** | Multi-language dependency graph (Python, JS/TS, Go, Rust) with cycle detection |
| **Architecture Scorer** | 0-100 quality score across 4 dimensions, 6 adaptive profiles, trend history |
| **Anti-Pattern Detector** | 7 structural detectors: god-class, hub-file, circular deps, dead code, and more |
| **Fragility Classifier** | STABLE / FRAGILE / VOLATILE per module, driven by git churn + test coverage |
| **Refactoring Planner** | Tier-1/2 refactor steps with projected score impact |
| **C4 Generator** | C4 Level 1-3 architecture diagrams (Mermaid, GitHub-native) |
| **Security Templates** | STRIDE threat model + OWASP Top 10 checklist, archetype-aware |
| **Knowledge Graph** | Links code, CVEs, risks, and decisions into one queryable graph |

## Genesis Decision Engine (GDE)

Routes any plain-English instruction across 7 modes and 19 engines, with a static gate policy:

| Mode | Engines | What runs |
|------|---------|-----------|
| `recovery` | 8 | Import graph, architecture score, anti-patterns, fragility, git churn, supply chain audit, recovery report |
| `research` | 5 | Source registry, research outline, field intelligence (Reddit Answers), evidence pack |
| `refactor` | 7 | Import graph, architecture score, anti-patterns, fragility, git churn, refactoring plan |
| `gate` | 10 | Import graph, architecture score, anti-patterns, fragility, git churn, import audit, supply chain audit, rules engine, security templates |
| `build` | 2 | Build scaffold (delegates to the genesis-architect scaffolder) |
| `document` | 4 | Import graph, C4 architecture diagrams, security templates |
| `committee` | 6 | Import graph, architecture score, anti-patterns, fragility, multi-perspective committee analysis |

Every mode also runs the Red-Team Self-Critique engine, which is included in the counts above.
Each mode has at most one required engine: the import graph, or the scaffolder in `build` mode
(`research` has none). The rest are optional, so a failing optional engine degrades the report
instead of aborting it.

### Gate policy

15 gates. Two can never be bypassed:
- `PLAN_WRITE`: hard block on any write targeting `planned.json`
- `RULES_FAIL`: hard block on a rules engine hard failure

The other 13 are overridable with `--yes`:
- **Stop and ask (7):** `CONFIDENCE_LOW`, `DRIFT_CRITICAL`, `SECURITY_RISK`, `POLICY_VIOLATION`,
  `COMMIT_CONFLICT`, `RED_TEAM_CRITICAL`, `RESEARCH_COVERAGE_LOW`
- **Warn only (6):** `WRITE_SCOPE`, `REQUIRED_FAILED`, `DEGRADED_MODE`, `NO_ENGINES`,
  `RESEARCH_STALE`, `RESEARCH_EVIDENCE_UNKNOWN`

Which gates a session evaluates depends on its mode.

## Install

```bash
# The engines, free, from PyPI (most people need only this)
pip install genesis-architect

# This standalone Pro distribution (8.0.0), straight from this repository
pip install "git+https://github.com/maioio/genesis-architect.git#subdirectory=genesis-architect-pro"

# With optional extras, e.g. the full Pro feature set
pip install "genesis-architect-pro[pro] @ git+https://github.com/maioio/genesis-architect.git#subdirectory=genesis-architect-pro"
```

The standalone distribution pulls in `genesis-architect` as a dependency. Available extras:
`tui`, `companion`, `streaming`, `voice`, `committee`, `mcp`, `companion-full`, `pro`, `dev`.

## CLI

```bash
# Which command runs which engine: the authoritative list
genesis engines

# Full 7-stage pipeline: classify → plan → execute → gate → report → approve → commit
genesis decide "diagnose the project and identify drift"

# Classify only (no execution)
genesis decide --classify-only "generate C4 diagrams"

# Auto-approve all writes (CI mode)
genesis decide --yes "run a full recovery scan"

# Analysis without committing any files
genesis decide --no-commit "check compliance and security"

# Third-party dependencies per module, plus their advisories
genesis deps .
genesis deps --package httpx --ecosystem pypi

# Restorable research/build context from a previous session
genesis memory --sessions

# Print decision log
genesis explain
```

Every command above takes `--json` for machine-readable output. On `decide`,
`recover` and `harden`, `--json` implies `--no-commit`: a piped consumer cannot
answer the approval prompt, so those runs are analysis-only.

`genesis engines` is generated from the capability map, and a test fails if any
module in the package is neither mapped to a command nor declared internal, so
the list above cannot quietly drift from what actually ships. The tables in this
README are a summary; `genesis engines` is the source of truth.

### Research

```bash
# Print the collection contract: full JSON schema, one filled example per stream
genesis research "a Python HTTP client library"

# Merge, rank and summarise pre-collected streams
genesis research "<topic>" --json-data research_data.json

# Feed a /watch analysis back in as cited PITFALLS.md entries
genesis research "<topic>" --absorb watch-output.txt

# Force the research floor's unit when the vision has no repo corpus
genesis research "<topic>" --json-data data.json --domain non-code
```

The research floor is a gate, not a suggestion: it reports thin research rather
than presenting it as sufficient. What adapts is the unit it counts: repos for
a software vision, authoritative sources for a vision with no repo corpus.

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

## License and commercial use

Dual-licensed. There is no license key and no feature gate.

1. **Open source (AGPL-3.0):** You are free to use, modify and distribute this software for
   personal or open-source projects, provided that you release your modifications, and any
   software that integrates it, under the same AGPL-3.0 license. See [LICENSE](LICENSE).

2. **Commercial license:** To use this software in a closed-source commercial product, or under
   terms without the AGPL-3.0 copyleft requirements, a commercial license is required.

For commercial licensing inquiries, contact: maio.eshet@gmail.com
