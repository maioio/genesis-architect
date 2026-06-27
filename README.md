# Genesis Architect Pro

The intelligence layer for [Genesis Architect](https://github.com/maioio/genesis-architect).

The free core researches GitHub and scaffolds a working MVP. Pro adds deep codebase analysis,
architecture intelligence, and persistent research memory.

## What Pro includes

| Engine | What it does |
|--------|--------------|
| **Import Graph** | Multi-language dependency graph (Python, JS/TS, Go, Rust) with cycle detection |
| **Architecture Scorer** | 0-100 quality score across 4 dimensions, 6 adaptive profiles |
| **Anti-Pattern Detector** | 7 structural detectors: god-class, hub-file, circular deps, dead code, and more |
| **Fragility Classifier** | STABLE / FRAGILE / VOLATILE per module — driven by git churn + test coverage |
| **Refactoring Planner** | Tier-1/2 refactor steps with CREATE / MODIFY / DELETE / MOVE operations |
| **C4 Generator** | C4 Level 1-3 architecture diagrams (Mermaid, GitHub-native) |
| **Security Templates** | STRIDE threat model + OWASP Top 10 checklist, archetype-aware |
| **Research Orchestrator** | Merges multiple research streams with a quality floor |
| **Pitfall Ranker** | Dedupes, scores, and merges pitfalls from many sources |
| **Video Research** | Builds YouTube/Reddit/IG queries and parses results |
| **Video to Pitfall** | Turns watched videos into real pitfalls in PITFALLS.md |
| **Cross-Session Memory** | Restores project context across sessions |
| **Package Registry** | Validates dependencies against PyPI/npm/crates.io |
| **Recovery Scan** | Full codebase health report: score, drift, anti-patterns, CVE, debt map |

## Install

```bash
pip install genesis-architect-pro
export GENESIS_PRO_LICENSE=<your-key>
```

Pro requires the free `genesis-architect` core (installed automatically as a dependency)
and a valid license key.

## Quick start

```python
from genesis_architect_pro import (
    build_graph,
    score_project,
    detect_all,
    classify_all,
    generate_plan,
    generate_c4_doc,
    generate_security_docs,
)

# Analyse any project path
graph  = build_graph("/path/to/project")
score  = score_project("/path/to/project")
issues = detect_all("/path/to/project")
frags  = classify_all("/path/to/project")
plan   = generate_plan("/path/to/project")

print(f"Architecture score: {score['total']}/100")
print(f"Anti-patterns found: {len(issues.patterns)}")
print(f"Volatile modules: {frags.volatile_count}")
```

## CLI commands (via genesis-architect free core)

```bash
genesis score .                    # architecture score
genesis antipattern .              # detect anti-patterns
genesis recover .                  # full recovery report
genesis harden .                   # STRIDE + OWASP + secrets scan
```

## License

Commercial. Not open source. See LICENSE.
