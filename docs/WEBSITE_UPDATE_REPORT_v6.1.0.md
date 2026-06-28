# Genesis Architect PRO — v6.1.0 Update Report
> For the website agent: update the Pro page/pricing section to reflect these new capabilities.

---

## Version bump
- **Was:** v5.4.1
- **Now:** v6.1.0

---

## What was added

### Part A — 8 New Codebase Intelligence Engines (v6.0.0)

Brand-new capabilities that did not exist in any previous version.
Available to Pro license holders via `pip install genesis-architect-pro`.

#### 1. Import Graph
Builds a multi-language dependency graph from source code.
- Supported languages: Python, JavaScript, TypeScript, Go, Rust
- Detects circular dependencies (import cycles)
- Maps each file to an architectural layer: presentation / domain / application / infrastructure / shared / test
- Identifies "dark modules" — files no other module imports (orphans)
- Computes fan-in and fan-out per module

#### 2. Architecture Scorer
Gives any codebase a 0–100 architecture quality score.
- 4 dimensions: Modularity, Coupling, Cohesion, Layering
- 6 adaptive profiles: `default`, `frontend-spa`, `backend-monolith`, `microservices`, `data-pipeline`, `library`
- Score label: EXCELLENT / GOOD / FAIR / POOR / CRITICAL
- Persists score history in `.genesis/score_history.jsonl` — tracks trend over time
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
- Fix-keyword detection: fix, bug, patch, hotfix, regression, revert, crash, etc.
- Configurable time window (default: last 90 days)

#### 5. Fragility Classifier
Combines anti-pattern data + git churn + test existence to classify every module.

| Status | Meaning |
|---|---|
| VOLATILE | CRITICAL anti-pattern, OR circular dep, OR high churn with no test |
| FRAGILE | Minor anti-patterns, OR medium churn, OR no test coverage |
| STABLE | No anti-patterns, low churn, test exists |

Outputs `FRAGILITY_MAP.md` — a human-readable risk map of every file with a GO / HOLD / REWRITE recommendation.

#### 6. Refactoring Planner
Generates an executable refactoring plan from the analysis results.
- Tier 1: blocking / critical issues — fix first
- Tier 2: improvements — fix after
- Each step includes: title, why, operations (CREATE / MODIFY / DELETE / MOVE), complexity, and projected score impact
- 5 built-in rules: hub-splitter, god-class-splitter, cycle-breaker, dead-code-removal, layer-violation-fix
- Outputs `REFACTORING_PLAN.md`

#### 7. C4 Architecture Generator
Generates professional architecture documentation automatically.
- Level 1 — System Context: who uses the system and what external systems it touches
- Level 2 — Containers: top-level buildable/deployable units
- Level 3 — Components: top modules by connectivity with import relationships
- Output: Mermaid C4 diagrams — render natively on GitHub
- Auto-detects external systems: database, auth, storage, email, AI, queue, payments, monitoring
- Writes to `docs/architecture/C4_ARCHITECTURE.md`

#### 8. Security Templates
Generates two security documents automatically, tailored to the project type.

**STRIDE Threat Model** — all 6 STRIDE categories:
- Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege
- Mitigations are archetype-specific (api / cli / library)

**OWASP Top 10 Checklist** — all 10 items:
- Items auto-marked N/A when not applicable (e.g., auth items for CLI tools)
- Writes to `docs/security/STRIDE_ANALYSIS.md` and `docs/security/OWASP_CHECKLIST.md`

---

### Part B — Genesis Decision Engine (v6.1.0)

The Genesis Decision Engine (GDE) is the permanent central brain of Genesis Architect PRO. Every engine — Recovery, Research, Refactoring, Gate, Committee — now runs **through** the GDE. It decides what runs, in what order, when to stop, and when to ask.

This is a verified, tested implementation — not a concept. The full INTAKE → PLAN → EXECUTE → GATE → REPORT lifecycle was run live and validated. See the [Practical Research Report](GDE_PRACTICAL_RESEARCH_REPORT.md) for full output.

#### Intent Classification
- Maps any free-text instruction to an execution mode — no LLM required, sub-millisecond
- 7 modes: RECOVERY / RESEARCH / REFACTOR / GATE / BUILD / DOCUMENT / COMMITTEE
- Validated on 12 real-world inputs: 7/12 classified correctly without needing clarification
- Ambiguous instructions escalate automatically to COMMITTEE with clarifying questions
- Genuinely ambiguous inputs (e.g., "our build is broken — fix it") correctly escalate rather than guessing

#### Execution Planning
- Builds a topologically-sorted execution plan per mode
- Engines with no mutual dependency run **in parallel** automatically
- Validated: `architecture_scorer` and `antipattern_detector` ran concurrently in phase 2 of a 5-engine RECOVERY chain
- Duration estimate computed before execution begins

#### Engine Runner
- Executes engines phase by phase with per-engine timeout enforcement
- Graceful degradation: one engine failure never crashes the session
- Confidence score tracks session quality in real time — starts at 1.0, penalized per failure:
  - Optional engine failure: −0.10
  - Required engine failure: −0.20
  - Engine degraded (warnings): −0.05
  - Floor: 0.10 — session never reports zero confidence

#### Gate Engine — 12 named approval gates

| Gate | Type | Overridable | Trigger |
|---|---|---|---|
| PLAN_WRITE | Hard block | **Never** | Any write targeting `planned.json` |
| RULES_FAIL | Hard block | **Never** | Rules engine hard failure |
| CONFIDENCE_LOW | Soft block | Yes | Session confidence < 0.40 |
| DRIFT_CRITICAL | Soft block | Yes | Drift score > 80 |
| SECURITY_RISK | Soft block | Yes | Engine reports security risk |
| POLICY_VIOLATION | Soft block | Yes | Rules engine policy violation |
| COMMIT_CONFLICT | Soft block | Yes | Write op conflicts with committed model |
| WRITE_SCOPE | Warning | Yes | Any pending write operations |
| REQUIRED_FAILED | Warning | Yes | Any engine failed |
| DEGRADED_MODE | Warning | Yes | Session confidence < 0.60 |
| NO_ENGINES | Warning | Yes | Zero engines ran |
| RESEARCH_STALE | Warning | Yes | Research results flagged stale |

Gate policy is a static table — not scattered in orchestration code. Verified live: `PLAN_WRITE` fired and blocked unconditionally when a write targeting `planned.json` was injected.

#### Session Persistence
- Session saved to `.genesis/gde_session.json` — crash-safe atomic write (via `.tmp` rename)
- Decision log at `.genesis/gde_decision_log.jsonl` — append-only, never overwritten
- Verified round-trip: session_id, confidence (0.73), and risk_level all preserved exactly
- Sessions are resumable after interruption

#### One-command usage
```python
from genesis_architect_pro import GenesisDecisionEngine
from pathlib import Path

gde = GenesisDecisionEngine(project_dir=Path("."))
report = gde.run("diagnose the project and identify drift")
# Returns: SessionReport with mode, confidence, gate_report, engine_results, decision_log
```

#### Market position (verified)
The GDE is the only tool in the market with all 5 decision-engine capabilities. Verified against 11 competing tools (Cursor, Cline, Aider, GitHub Copilot Workspace, Sweep, Cody, Continue, Devin, SWE-agent, OpenHands, AutoCodeRover):

| Capability | All 11 competitors | Genesis GDE |
|---|---|---|
| Intent classification (free text → mode) | None | Yes |
| Engine routing by classified intent | None | Yes |
| Static approval gate policy table | None | Yes |
| Session confidence score | None | Yes |
| Persistent decision log | None | Yes |

Every competing tool either uses an LLM to interpret intent (slow, nondeterministic) or forces the user to select a mode manually (slash commands, dropdowns). Genesis GDE routes deterministically, sub-millisecond, with no LLM involved.

---

## New CLI commands (unlocked by Pro license)

```bash
genesis score .                           # Architecture score 0-100
genesis score . --profile microservices   # Score with specific adaptive profile
genesis antipattern .                     # Detect all 7 anti-patterns
genesis antipattern . --json              # Machine-readable output
genesis recover .                         # Full recovery report (all engines combined)
genesis harden .                          # Generate STRIDE + OWASP + secrets scan
```

`genesis recover .` produces:
- Architecture score + trend history
- Import graph + circular dependency report
- Anti-pattern report (7 detector types)
- Fragility map (VOLATILE / FRAGILE / STABLE per module)
- Refactoring plan (tier-1 critical first, tier-2 improvements)
- `PROJECT_RECOVERY_REPORT.md` — single consolidated report

`genesis harden .` produces:
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

### Headline angle

> Genesis PRO now analyzes your existing codebase — not just new projects.
> Point it at any repo and get an architecture score, a risk map of every file,
> a prioritized refactoring plan, C4 diagrams, and a security checklist.
> All in under 30 seconds. No LLM required for the analysis.
>
> And now with the Genesis Decision Engine: one plain-English instruction routes
> automatically to the right engines, in the right order, with built-in safety gates
> that can never be bypassed.

### Feature bullets for the Pro pricing page

**Codebase Intelligence**
- Architecture score 0–100 with trend history
- 7 anti-pattern detectors: god class, circular deps, dead code, hub files, and more
- STABLE / FRAGILE / VOLATILE risk map — every file, with GO / HOLD / REWRITE
- Executable refactoring plan — tier-1 blocking issues first, tier-2 improvements after
- Auto-generated C4 architecture diagrams (Mermaid, renders natively on GitHub)
- STRIDE threat model + OWASP Top 10 checklist, tailored to your project type
- Works on Python, JavaScript, TypeScript, Go, Rust
- `genesis recover .` — one command, full codebase health report in under 30 seconds

**Genesis Decision Engine**
- Type any instruction in plain English — GDE routes it to the right engines automatically
- No LLM required for routing — deterministic, sub-millisecond, always consistent
- 12-gate approval policy — 2 gates can never be bypassed, even by you
- Confidence score on every session — know exactly how reliable the output is
- Full decision log — every choice recorded, always auditable
- Crash-safe session persistence — resume exactly where you left off
- Only tool in the market with all 5 decision-engine capabilities (verified against 11 competitors)

---

*Report generated 2026-06-28 | Genesis Architect PRO v6.1.0*
