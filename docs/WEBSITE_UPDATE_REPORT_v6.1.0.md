# Genesis Architect PRO — v6.1.0 Update Report
> For the website agent: update the Pro page/pricing section to reflect these new capabilities.

---

## Version bump
- **Was:** v5.4.1
- **Now:** v6.1.0

---

## What was added

### Part A — 8 New Codebase Intelligence Engines (v6.0.0)

These are brand-new capabilities that did not exist in any previous version.
All are available to Pro license holders via `pip install genesis-architect-pro`.

#### 1. Import Graph
Builds a multi-language dependency graph from source code.
- Supported languages: Python, JavaScript, TypeScript, Go, Rust
- Detects circular dependencies (import cycles)
- Maps each file to an architectural layer (presentation / domain / application / infrastructure / shared / test)
- Identifies "dark modules" — files no other module imports (orphans)
- Computes fan-in and fan-out per module

#### 2. Architecture Scorer
Gives any codebase a 0–100 architecture quality score.
- 4 dimensions: Modularity, Coupling, Cohesion, Layering
- 6 adaptive profiles: `default`, `frontend-spa`, `backend-monolith`, `microservices`, `data-pipeline`, `library`
- Score label: EXCELLENT / GOOD / FAIR / POOR / CRITICAL
- Persists score history in `.genesis/score_history.jsonl` — shows trend over time
- Penalty system for circular dependencies

#### 3. Anti-Pattern Detector
Detects 7 structural anti-patterns automatically — no LLM, pure graph analysis.

| Anti-Pattern | What it means |
|---|---|
| God Class | One file imports 15+ modules — does too much |
| Hub File | One file is imported by 10+ modules — everything depends on it |
| Circular Dependency | Two or more modules import each other |
| Dead Code | File with no importers and not an entry point |
| Feature Envy | >65% of a module's imports come from one external module |
| Leaky Abstraction | Low-layer module imports from a high-layer module |
| Shotgun Surgery | A utility imported by 8+ modules — one change breaks everything |

Each finding includes: severity (CRITICAL / HIGH / MEDIUM / LOW), affected files, and a concrete suggested fix.

#### 4. Git Churn Analyzer
Analyzes git history to classify how risky each module is.
- Counts commits, fix-commits, and fix ratio per file
- Classifies each module: HIGH / MEDIUM / LOW / STALE churn
- Uses fix-keyword detection: fix, bug, patch, hotfix, regression, revert, crash, etc.
- Configurable time window (default: last 90 days)

#### 5. Fragility Classifier
Combines anti-pattern data + git churn + test existence to classify every module:

| Status | Meaning |
|---|---|
| VOLATILE | CRITICAL anti-pattern, OR circular dep, OR high churn with no test |
| FRAGILE | Minor anti-patterns, OR medium churn, OR no test coverage |
| STABLE | No anti-patterns, low churn, test exists |

Outputs `FRAGILITY_MAP.md` — a human-readable map of every file's risk level with a GO / HOLD / REWRITE recommendation.

#### 6. Refactoring Planner
Generates an executable refactoring plan from the analysis results.
- Tier 1 steps: blocking / critical issues (fix first)
- Tier 2 steps: improvements (fix after)
- Each step has: title, why, operations (CREATE / MODIFY / DELETE / MOVE), complexity, and projected score impact
- 5 built-in rules: hub-splitter, god-class-splitter, cycle-breaker, dead-code-removal, layer-violation-fix
- Outputs `REFACTORING_PLAN.md`

#### 7. C4 Architecture Generator
Generates professional architecture documentation automatically.
- Level 1 — System Context: who uses the system and what external systems it touches
- Level 2 — Containers: top-level buildable/deployable units
- Level 3 — Components: top modules by connectivity with import relationships
- Output format: Mermaid C4 diagrams — render natively on GitHub
- Detects external systems automatically (database, auth, storage, email, AI, queue, payments, monitoring)
- Writes to `docs/architecture/C4_ARCHITECTURE.md`

#### 8. Security Templates
Generates two security documents automatically, tailored to the project type.

**STRIDE Threat Model** — covers all 6 STRIDE categories:
- Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege
- Mitigations are archetype-specific (api / cli / library)

**OWASP Top 10 Checklist** — all 10 items:
- Items marked N/A automatically when not applicable (e.g., auth items for CLI tools)
- Writes to `docs/security/STRIDE_ANALYSIS.md` and `docs/security/OWASP_CHECKLIST.md`

---

### Part B — Genesis Decision Engine (v6.1.0)

The GDE is the permanent central brain of Genesis Architect PRO. Every engine — Recovery, Research, Refactoring, Gate, Committee — now runs **through** the GDE. It decides what runs, in what order, when to stop, and when to ask.

#### Intent Classification
- Maps any free-text instruction to an execution mode automatically
- 7 modes: RECOVERY / RESEARCH / REFACTOR / GATE / BUILD / DOCUMENT / COMMITTEE
- Signal-based — no LLM required, sub-millisecond
- Ambiguous instructions escalate to COMMITTEE mode with clarifying questions

#### Execution Planning
- Builds a topologically-sorted execution plan per mode
- Engines with no mutual dependency run in parallel automatically
- Duration estimate before execution begins

#### Engine Runner
- Executes all engines with timeout enforcement per engine
- Graceful degradation — one engine failure never crashes the session
- Confidence score tracks session quality in real time (starts at 1.0, penalized per failure)

#### Gate Engine — 12 named approval gates

| Gate | Type | Overridable |
|---|---|---|
| PLAN_WRITE | Hard block | Never |
| RULES_FAIL | Hard block | Never |
| CONFIDENCE_LOW | Soft block | Yes |
| DRIFT_CRITICAL | Soft block | Yes |
| SECURITY_RISK | Soft block | Yes |
| POLICY_VIOLATION | Soft block | Yes |
| COMMIT_CONFLICT | Soft block | Yes |
| WRITE_SCOPE | Warning | Yes |
| REQUIRED_FAILED | Warning | Yes |
| DEGRADED_MODE | Warning | Yes |
| NO_ENGINES | Warning | Yes |
| RESEARCH_STALE | Warning | Yes |

Gate policy is a static table — not scattered in orchestration code. `planned.json` is unconditionally protected.

#### Session Persistence
- Every session saved to `.genesis/gde_session.json` — crash-safe atomic write
- Full decision log at `.genesis/gde_decision_log.jsonl` — append-only, never overwritten
- Sessions are resumable after interruption

#### One-command usage
```python
from genesis_architect_pro import GenesisDecisionEngine

gde = GenesisDecisionEngine(project_dir=Path("."))
report = gde.run("diagnose the project and identify drift")
```

---

## New CLI commands (free tier, unlocked by Pro)

These commands are added to the `genesis` CLI and activated when a Pro license is present:

```bash
genesis score .                           # Run architecture scorer, print 0-100 score
genesis score . --profile microservices   # Use specific adaptive profile
genesis antipattern .                     # Detect all 7 anti-patterns, print findings
genesis antipattern . --json              # Machine-readable output
genesis recover .                         # Full recovery report (all engines combined)
genesis harden .                          # Generate STRIDE + OWASP + scan for hardcoded secrets
```

`genesis recover` produces:
- Architecture score + trend
- Import graph + cycle report
- Anti-pattern report
- Fragility map (VOLATILE / FRAGILE / STABLE per module)
- Refactoring plan (tier-1 and tier-2)
- `PROJECT_RECOVERY_REPORT.md` — single consolidated report

`genesis harden` produces:
- `docs/security/STRIDE_ANALYSIS.md`
- `docs/security/OWASP_CHECKLIST.md`
- Hardened `.gitignore`
- GitHub Actions workflows: secrets-scan + SAST
- Console report of any hardcoded secrets found

---

## What already existed in Pro (unchanged, still included)

- Research Orchestrator — multi-source research with quality floor
- Pitfall Ranker — deduplication and scoring of pitfalls
- Video Research — YouTube/Reddit/Instagram query builder
- Video to Pitfall — turns videos into PITFALLS.md entries
- Cross-Session Memory — restores project context across sessions
- Package Registry — validates PyPI/npm/crates.io dependencies
- Recovery Scan (basic) — git history fragility signals

---

## Summary for website copy

**Before v6:** Pro = deeper research + memory persistence

**After v6.1:** Pro = deeper research + memory + full codebase intelligence layer + central decision brain

The new angle to emphasize:
> Genesis PRO now analyzes your existing codebase — not just new projects.
> Point it at any repo and get an architecture score, a risk map of every file,
> a prioritized refactoring plan, C4 diagrams, and a security checklist.
> All in under 30 seconds. No LLM required for the analysis.
>
> And now with the Genesis Decision Engine: one instruction routes automatically
> to the right engines, in the right order, with built-in safety gates.

### Suggested feature bullets for the Pro page

**Codebase Intelligence**
- Architecture score 0–100 with trend history
- 7 anti-pattern detectors (god class, circular deps, dead code, and more)
- STABLE / FRAGILE / VOLATILE risk map per file
- Executable refactoring plan — tier-1 blocking issues first
- Auto-generated C4 architecture diagrams (Mermaid, GitHub-native)
- STRIDE threat model + OWASP Top 10 checklist
- Works on Python, JavaScript, TypeScript, Go, Rust
- `genesis recover .` — one command, full codebase health report

**Genesis Decision Engine**
- Single entry point for all Genesis intelligence — one call, full lifecycle
- Intent classifier routes any instruction to the right engine set automatically
- 12-gate approval policy — hard safety guarantees built in
- Confidence score on every session — know how reliable the output is
- Full decision log — always know why Genesis did what it did
- Crash-safe session persistence — resume after interruption

---

*Report generated 2026-06-28 | Genesis Architect PRO v6.1.0*
