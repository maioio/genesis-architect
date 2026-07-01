# Genesis Architect PRO — Website Update Report
> For the website agent: update the Pro page/pricing/docs section to reflect these capabilities.
> **This is the living source of truth for what to publish on the site. It is kept up to date as the product evolves — always check the "Last updated" date and the "🆕 NEW" banner before a site refresh.**

> ✅ **MILESTONE — v6.4.0 complete (2026-06-29).** All engines, modes, and UI
> fully built and tested. **1,441 tests passing. 13 GDE engines. 7/7 modes wired.
> Rich CLI TUI. Nothing open.** All work is on the private remote `pro/main`.

---

## 🌐 Site sync status (check this when editing the landing page)

| Surface | File | Version | Status |
|---------|------|:-------:|--------|
| Free landing | `docs/index.html` | v6.4.0 | ✅ in sync |
| Pro page | `docs/pro.html` | v6.4.0 | ✅ in sync |
| This report | (source of truth) | v6.4.0 | ✅ current |

**Live URLs:** Pro site = GitHub Pages of the private `genesis-architect-pro`
repo. Public free landing (origin) uses `docs/pro/guide/LANDING_HANDOFF.md`.

When you edit the landing page, keep this table honest: bump the version + flip
status to "⏳ needs sync" for anything that drifts from this report, then back to
"✅ in sync" once published. Never publish a capability not listed below as
shipped.

---

## 🆕 NEW in v6.4.0 (publish these)
> The newest additions since the last site update. Lead the announcement with these.

- **Rich CLI TUI** — `genesis decide` now renders with panels, a live progress
  spinner, color-coded gate status, engine results table, and an interactive
  approval prompt. Graceful plain-text fallback when rich is not installed
  (`pip install genesis-architect-pro[tui]`).
- **All 7 GDE modes fully wired** — RESEARCH, BUILD, and COMMITTEE were
  previously stubs with 0 engines. Now:
  - RESEARCH: source_registry → field_intelligence → evidence_pack (3 engines)
  - BUILD: build_scaffold delegates to the free core scaffolder (1 engine)
  - COMMITTEE: full analysis pass (import_graph → scorer → anti-pattern →
    fragility) + committee_analysis synthesis with divergence detection (5 engines)
- **Intent classifier calibration** — all 7 modes now classify correctly on
  natural-language phrases with healthy confidence; RESEARCH/BUILD/COMMITTEE
  signals expanded with real practitioner phrases.
- **Two-page site (v6.4.0)** — `docs/index.html` is the Free landing page
  ("Research First. Build Once."); `docs/pro.html` is the Pro page (AI Engineering
  Partner) with all 13 engine cards, the GDE pipeline, GDE vs 11 competitors, and
  the founder pricing section. Both at v6.4.0.

- **Memory Engine + Decision Journal** — per-project memory as plain Markdown
  under `.genesis/` (project memory, decision log, research history, ADRs, known
  risks, lessons). Every significant decision is journaled with alternatives,
  evidence, confidence, and "what would change it" — a decision with no entry is
  treated as not made.
- **UI Engine — Floating Assistant + Canvas Workspace** — a premium visual layer
  with **zero setup**: a single self-contained HTML workspace (no Node, no build,
  no server, no Docker) rendered from the engine outputs. Floating status panel +
  full canvas (score, knowledge graph, CVEs, drift, risk zones). Opens in any
  browser; the same artifact a future desktop app embeds.

### 🧭 Designed, coming next (do NOT list as shipped yet)

- **Genesis PRO Companion (Standalone App)** — the flagship next evolution:
  a voice-capable, IDE-aware, proactive engineering partner built as a Tauri v2
  standalone application. Surfaces the full GDE + Committee intelligence through
  a floating bubble → panel → canvas surface hierarchy. Key capabilities in design:
  - **Voice layer:** Push-to-talk (Alt+Space) + wake word ("Genesis, start" /
    "ג'נסיס, תתחיל") — Hebrew + English + 5 more languages. Local STT (Whisper.cpp
    large-v3-turbo) + local TTS (Kokoro English / Piper he_IL Hebrew). No cloud
    dependency.
  - **IDE Bridge:** Read-only VS Code + JetBrains sidecar. Line-level pattern
    detection ("God Class detected on line 42 — run Committee?"). Context Engine
    fetches only high-relevance snippets from the Knowledge Graph (Scryer-style).
  - **Visual Diff Approval:** All GDE writes presented as a visual diff; user
    approves/denies per-file before any commit.
  - **Committee transparency profiles:** Free = final recommendation only; Pro =
    full discussion panel with divergence map + voting record, streamed live.
  - **Status:** Full architecture spec complete (`docs/pro/COMPANION_ARCHITECTURE.md`
    + `FLOATING_ASSISTANT_SPEC.md`; approved visual reference in `docs/pro/assets/`).
    Implementation not yet started. Present as **"coming soon"** — never as an
    available feature.
  - **Pro-only + backed up:** this subsystem lives exclusively in the **private**
    `genesis-architect-pro` repo (verified private on GitHub), visible only to
    paying licensees — never the public free core. All work is committed and pushed
    to `pro/main`.

### Earlier in v6.3.0 (still featured)

- **Research Source Registry** — Genesis researches from a ranked, configurable
  catalog of 25+ sources (official docs, source, security DBs, packages, Q&A,
  developer field, learning). Sources are ranked by authority × evidence weight,
  and **new sources can be added per-project without changing the engine**.
- **Reddit Answers workflow** — Developer Field Intelligence now mines real
  practitioner pain ("problems / not working / production issues / vs X / worth
  it / migration"), then **verifies every claim against engineering-truth
  sources** before it influences advice. Field signal is never treated as final
  truth.
- **Evidence Packs** — every significant recommendation now ships with a proof
  pack: the sources consulted (with reliability), an **honest confidence grade**
  (never "high" without an authoritative source; contradictions lower it), and
  unreachable sources marked *unavailable* rather than faked.

### Earlier in v6.2.0 (still new-ish — keep featured)

- **Knowledge Graph Engine** — cross-source connective intelligence. Links code,
  CVEs, decisions, risks, and field findings into one queryable graph. Answers
  questions no competitor can: *"which do-not-touch zone has an open CVE?"*
  **This is the flagship differentiator — neither competing tool has it.**
- **Decision Engine wiring (engine adapters)** — the GDE now drives the *real*
  engines end-to-end (architecture → anti-pattern → recovery / knowledge-graph),
  with dependency ordering and graceful degradation. Not a skeleton — verified
  end-to-end on a live project.
- **Learning Engine** — Genesis learns which research strategy works for each
  task kind and improves over time, with honest confidence (never overclaims
  from one sample).
- **Product Intelligence (telemetry)** — anonymous, opt-in, **default-OFF**.
  Privacy enforced in code (a sanitizer blocks any leak of code/paths/secrets),
  not by trust. Survived an adversarial privacy review.
- **No-setup customer readiness** — backs the four-step promise
  (Download → Install → License → Work) with a `doctor` check and honest
  offline/degraded reporting. **No Docker, ever, for customers.**
- **Customer documentation (26 pages)** — the full "Read the docs" technical
  layer, grounded in shipped engines. Ready to link from the homepage.

---

## Version bump
- **Was:** v6.3.0
- **Now:** v6.4.0

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

#### One-command usage (Python API)
```python
from genesis_architect_pro import GenesisDecisionEngine
from pathlib import Path

gde = GenesisDecisionEngine(project_dir=Path("."))
report = gde.run("diagnose the project and identify drift")
# Returns: SessionReport with mode, confidence, gate_report, engine_results, decision_log

# APPROVE stage — inspect pending writes before committing
request = gde.approve(report)
print(request.summary)

# COMMIT stage — execute approved writes atomically
from genesis_architect_pro.gde_types import ApprovalDecision, ApprovalChoice
decision = ApprovalDecision(session_id=report.session_id, choice=ApprovalChoice.APPROVE)
result = gde.commit(report, decision)
```

#### CLI usage
```bash
# Full GDE session — analyses the project, prompts for approval before writing
genesis decide "diagnose the project and identify drift"

# Classification only — which mode would this trigger?
genesis decide --classify-only "generate C4 diagrams for the codebase"

# Non-interactive auto-approve (CI/scripting)
genesis decide --yes "run a full recovery scan"

# Analysis only — no writes, no approval prompt
genesis decide --no-commit "check compliance before we proceed"

# Print the last session's decision log
genesis explain
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

### Part C — AI Engineering Partner layer (v6.2.0)

Five new engines that turn Genesis from a codebase analyzer into a full AI
Engineering Partner. All Pro-only, all tested.

#### 9. Knowledge Graph Engine ⭐ flagship
Links everything Genesis knows about a project into one directed, queryable graph.
- **Node types:** module, anti-pattern, drift, CVE, package, risk, decision,
  evidence, field-finding, test.
- **Edges carry confidence** (0–1) + an optional evidence reference — a link with
  no basis is low-confidence by construction (honesty clause).
- **Connective queries** across sources, e.g.
  `cve → package → module` intersected with `risk → module` to find
  **do-not-touch zones that have an open CVE**.
- Additive + deterministic; persisted to `.genesis/knowledge/graph.json`.
- **Market position:** neither scryer nor architect — nor any of the 11 surveyed
  competitors — has cross-source connective intelligence. Hardest capability to
  copy.

#### 10. Decision Engine — real engine wiring
The GDE now orchestrates the actual analysis engines, not a skeleton.
- Thin **engine adapters** bridge each real engine (architecture scorer,
  anti-pattern detector, recovery, security, knowledge graph) to the GDE runner.
- Correct dependency ordering: `recovery` requires `architecture`;
  `knowledge_graph` requires `antipattern`.
- **Graceful degradation:** an unavailable engine or empty source returns a
  low-confidence, degraded result with a warning — never a crash, never fabricated
  data.
- Verified **end-to-end**: real engines run through the real planner + runner on a
  sample project; the registry validates clean (deps satisfied, no cycles).

#### 11. Learning Engine
Genesis improves which research strategy it picks, over time.
- Records outcomes per task kind (bug / architecture / security / migration / …)
  and recommends the best-performing research profile.
- **Honest confidence:** `low` until ≥3 samples (`medium`) / ≥8 (`high`).
  A perfect rate from one sample is never "high".
- Two scopes: **per-project** (immediate feedback) and **cross-project** (only via
  anonymous, consented telemetry — never from your code).
- Writes a `lessons_learned.md` digest.

#### 12. Product Intelligence (telemetry)
Anonymous, opt-in product feedback — the loop that shows which engines earn their
keep.
- **Default OFF.** No pre-checked opt-in. Nothing recorded until you consent.
- **Anonymous only** (random install id; never account/machine/project/path).
- **Revocable**, and you can **see exactly what is stored**.
- **Never collected:** code, file paths, project names, secrets, prompts.
- Enforced by a fail-closed **sanitizer** in code (drops paths/secrets/free-text/
  unknown event shapes), not by trust. Survived an adversarial privacy review.
- With telemetry off, the product is fully functional — it is never a gate.

#### 13. No-setup customer readiness (packaging)
Backs the four-step customer promise with code.
- `doctor` check: the **license is the only required step**; everything else is
  optional and never blocks.
- **Honest offline mode:** local analysis (graph, score, anti-patterns, C4, drift,
  recovery, gate, knowledge graph) works fully offline; network-backed research is
  marked *unavailable*, never faked.
- Self-heal for optional deps (e.g. ffmpeg) — explicit, opt-in, one prompt.
- **No Docker, Python infra, Node, DB, Redis, or MCP server** is ever a customer
  step.

#### 📚 Customer documentation (26 pages)
The full "Read the docs" technical layer, ready to publish, grounded in shipped
engines (not aspirational):
- Part I — the partner, five principles, the 15-step Thinking Loop, Free vs Pro
- Part II — Research Intelligence, Developer Field Intelligence, Evidence Packs,
  Source Registry + 9 profiles
- Part III — every engine page (what it does, Free/Pro, worked example, output)
- Part IV — recovery + CI-gate workflows
- Part V — install/license, privacy, offline
- Part VI — `.genesis/` file reference, changelog
- Plus `LANDING_HANDOFF.md` — approved homepage copy (removes "pitfall finder"
  framing; drops Instagram-as-source).

> ✅ Update (v6.4.0): the **UI Engine (Floating Assistant + Canvas Workspace)** is
> now **shipped** — built as a zero-setup self-contained HTML workspace
> (`ui_workspace.py`). It is safe to present as available on the site. (A native
> Tauri desktop shell remains optional future polish.)

---

## New CLI commands (unlocked by Pro license)

```bash
# Genesis Decision Engine
genesis decide "diagnose the project and identify drift"   # Full session
genesis decide --classify-only "generate C4 diagrams"     # Intent only — no execution
genesis decide --yes "run a full recovery scan"            # Auto-approve (CI mode)
genesis decide --no-commit "check compliance"              # Analysis only
genesis explain                                            # Print last decision log

# Direct engine commands
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

**After v6.4:** Pro = deeper research + memory + full codebase intelligence layer
+ central decision brain (now wired to the real engines) + **cross-source
Knowledge Graph** + continuous Learning + anonymous Product Intelligence +
no-setup install — i.e. a full **AI Engineering Partner**, not just an analyzer.

### Headline angle

> Genesis PRO now analyzes your existing codebase — not just new projects.
> Point it at any repo and get an architecture score, a risk map of every file,
> a prioritized refactoring plan, C4 diagrams, and a security checklist.
> All in under 30 seconds. No LLM required for the analysis.
>
> And now with the Genesis Decision Engine: one plain-English instruction routes
> automatically to the right engines, in the right order, with built-in safety gates
> that can never be bypassed.
>
> New: a cross-source **Knowledge Graph** connects your code, security CVEs, risk
> zones and decisions — so Genesis can tell you which "do-not-touch" module has a
> live vulnerability. It **learns** which research strategy works for your work,
> and installs in four steps with **no Docker, ever**.

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
- 8 production engines wired and running: import graph, scorer, anti-patterns, fragility, recovery, refactoring, C4, security
- Parallel execution: independent engines run concurrently within each phase
- 12-gate approval policy — 2 gates can never be bypassed, even by you
- APPROVE → COMMIT lifecycle: inspect pending writes before anything touches disk
- Atomic writes: all file operations use tmp→rename — no partial writes on crash
- Confidence score on every session — know exactly how reliable the output is
- Full decision log — every choice recorded, always auditable
- Crash-safe session persistence — resume exactly where you left off
- `genesis decide "<instruction>"` CLI — one command, full pipeline with approval prompt
- Only tool in the market with all 5 decision-engine capabilities (verified against 11 competitors)

**AI Engineering Partner**
- **Knowledge Graph** — links code, CVEs, risks and decisions; finds do-not-touch zones that have an open CVE (nothing else on the market does this)
- **Learning Engine** — gets better at choosing research strategies for your work, with honest confidence
- **Research Source Registry** — 25+ ranked sources, extensible per-project without code
- **Reddit Answers workflow** — verified field intelligence (never treated as final truth)
- **Evidence Packs** — proof behind every recommendation, with honest confidence
- **Memory + Decision Journal** — per-project `.genesis/*.md` memory; every decision journaled
- **Floating Assistant + Canvas** — zero-setup visual workspace (no Node/build/server)
- **Anonymous Product Intelligence** — opt-in, default-off, privacy enforced in code
- **Four-step install, no Docker** — Download → Install → License → Work
- **Works offline** — all local analysis runs with no network; online sources are honestly marked when unavailable
- **26-page documentation** — the full technical "Read the docs" layer

---

## 🔁 Maintenance protocol (for the assistant — do not delete)

This report is the **living source of truth** for site updates. Keep it current:

- **Update this file in the SAME change** whenever a customer-visible capability
  ships (new engine, new CLI command, pricing/positioning change, a planned
  feature becoming available, or a removed feature).
- On each update: bump the **version**, refresh the **🆕 NEW** banner (move the
  now-published items into the body), and set **Last updated** below.
- **Site-refresh cadence:** review at least **every 2 weeks**, and always after a
  capability ships. If ≥14 days have passed since "Last updated" while work
  continued, proactively remind the user that the site is due for a refresh.
- **Honesty rule:** never list a capability here as available unless it is
  actually shipped + tested. Planned features are marked "coming soon".

---

*Last updated: 2026-07-01 | Genesis Architect PRO v6.4.0 | Next site review due: 2026-07-15*

> **Design milestone (2026-07-01):** Genesis PRO Companion — full architecture spec
> complete (`docs/pro/COMPANION_ARCHITECTURE.md`). Covers: Committee engine as
> core primitive + Transparency Profiles, Tauri v2 standalone app shell,
> voice layer (Whisper + Kokoro + Piper), IDE bridge (VS Code + JetBrains),
> Visual Diff Approval, Context Engine (Scryer-style), STT/TTS decision matrix.
> Informed by: Instagram reel (Vercel AI SDK 7 voice gateway — Vercel approach
> rejected in favor of local-first; UX pattern adopted).
> **Reddit field research was cut short by an account weekly-usage limit** and did
> NOT return verified findings — §7 open questions remain unvalidated by field data
> and the STT/TTS matrix stands on model-card/benchmark evidence only (honest
> confidence grade). Do not present the voice quality claims as field-validated.
> This is a DESIGN deliverable — not yet implemented. "Coming soon" on the site.

> **Bug fix (2026-07-01):** `get_default_registry()` now auto-loads engine
> descriptors on first call (lazy import). Cold import previously returned 0
> engines. 1,441 tests still passing.

> **Session additions (2026-06-29):** Rich TUI, all 7 GDE modes wired (13 engines),
> intent classifier calibration, landing page Pro/GDE sections, README rewrite.
> 1,441 tests passing. pyproject.toml v6.4.0.

> **Pricing confirmed (2026-06-29):** Founder $9/mo or $90/yr (2 months free),
> first 50 seats locked for life; then $19/mo or $190/yr. Live on the site.
> **v2 build phase closed** — see `docs/pro/PHASE_v2_CLOSURE.md`. **Nothing from
> the spec remains open** (Memory + UI engines shipped in v6.4.0). All work is on
> the private remote `pro/main`.
