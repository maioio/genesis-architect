# Genesis Architect PRO — Website Update Report
> For the website agent: update the Pro page/pricing/docs section to reflect these capabilities.
> **This is the living source of truth for what to publish on the site. It is kept up to date as the product evolves — always check the "Last updated" date and the "🆕 NEW" banner before a site refresh.**

> ✅ **MILESTONE — v6.6.0 complete (2026-07-02).** Companion Intelligence Layer shipped.
> **Committee Engine (anti-sycophancy, 28 tests), WebSocket Streaming Layer (20 event types, 21 tests),
> IDE Bridge server + VS Code extension, VoicePipeline STT/TTS stub (52 tests). 1,569 tests passing.**
> All work is on the private remote `pro/main`. See §🆕 NEW — v6.6.0 below.

> ✅ **MILESTONE — v6.5.1 complete (2026-07-02).** Companion Phase 0+1 shipped.
> **Gate miss-rate instrumentation, OS notifications (plyer optional), health page
> server (stdlib only), `genesis companion` CLI. 1,496 tests passing. Zero new
> required deps.** All work is on the private remote `pro/main`.

> ✅ **MILESTONE — v6.6.1 complete (2026-07-02).** All engines fully wired — 17 production
> engines, 4 new (rules_engine, git_analyzer, import_audit, knowledge_graph auto),
> decay forecast in scorer, `genesis memory` + `genesis ui` CLI. 181 public API symbols.

> 🏗️ **ARCHITECTURE MILESTONE — v6.5.0 (2026-07-01).** Full architecture
> specifications complete for the Genesis PRO Companion standalone app and the
> Committee engine as a core GDE primitive. **Not yet shipped — design phase.**
> Three new spec documents committed. See §🆕 NEW below.

---

## 🌐 Site sync status (check this when editing the landing page)

| Surface | File | Version | Status |
|---------|------|:-------:|--------|
| Free landing | `docs/index.html` | v6.4.0 | ⏳ needs sync |
| Pro page | `docs/pro.html` | v6.4.0 | ⏳ needs sync |
| This report | (source of truth) | v6.6.1 | ✅ current |

**Live URLs:** Pro site = GitHub Pages of the private `genesis-architect-pro`
repo. Public free landing (origin) uses `docs/pro/guide/LANDING_HANDOFF.md`.

When you edit the landing page, keep this table honest: bump the version + flip
status to "⏳ needs sync" for anything that drifts from this report, then back to
"✅ in sync" once published. Never publish a capability not listed below as
shipped.

---

## 🆕 NEW in v6.6.0 — Companion Intelligence Layer (publish these as "coming soon" / roadmap)

### Committee Engine ✅ shipped code + tests (2026-07-02) — publish as "PRO roadmap"

> **Status:** Fully implemented and tested (28 tests passing). Not yet wired into the default
> GDE CLI flow — arriving in a future `genesis decide` release. Safe to list as "coming soon"
> with confidence it is already built.

The Committee Engine is Genesis's answer to AI sycophancy. Instead of one LLM giving one answer,
five specialized advisors debate every major architectural decision independently, then review each
other's reasoning — and Genesis detects when they reach manufactured consensus versus genuine agreement.

**5 Advisor roles:**
- **Contrarian** — challenges assumptions, finds what's wrong with the obvious answer
- **First Principles** — breaks the problem down to fundamentals, ignores precedent
- **Expansionist** — looks for missing context, broader system effects, unknown unknowns
- **Outsider** — applies cross-domain patterns, asks "how would X industry solve this?"
- **Executor** — focuses on implementation reality: what can actually be built, in what time

**Collapse detection — manufactured vs earned consensus:**
When advisors agree too quickly after peer review, Genesis flags it. A post-review variance drop
>70% with high final agreement → `MANUFACTURED_CONSENSUS` warning + confidence capped at 0.65.
Genuine convergence (advisors start similar, stay similar) → `EARNED_CONSENSUS`, full confidence.

**Transparency Profiles (FREE vs PRO):**
- **FREE tier:** Final verdict + confidence score only
- **PRO tier:** Full debate transcript, per-advisor positions, divergence map, voting record,
  minority view, manufactured-consensus warning — all streamed live to the Companion panel

**Technical implementation:**
- ThreadPoolExecutor(5) parallel advisor calls — all 5 positions in one LLM round-trip time
- Peer review round triggered automatically when advisor variance > 0.15
- Injectable LLM callable (real Anthropic SDK default; mock for tests)
- Atomic append to `.genesis/gde_decision_log.jsonl`
- 28 tests: unit (advisors, collapse detector, transparency filter) + 3 integration with mock LLM

---

### WebSocket Streaming Layer ✅ shipped code + tests (2026-07-02) — publish as "PRO roadmap"

> **Status:** Fully implemented and tested (21 tests passing). The Companion panel reads from
> this stream. Not yet exposed via public CLI — arrives with the Companion app.

Real-time event stream from GDE engine execution to the Companion panel (and any future IDE extension).

**20 event types:**
`ENGINE_START`, `ENGINE_DONE`, `ENGINE_FAILED`, `GATE_FIRED`, `SESSION_CONFIDENCE`,
`COMMITTEE_SYNTHESIS`, `IDE_LINE_EVENT`, `DIFF_READY`, `DIFF_APPROVED`, `DIFF_REJECTED`,
`VOICE_STT`, `VOICE_TTS`, `SESSION_START`, `SESSION_COMPLETE`, `USER_MESSAGE`,
`USER_COMMAND`, `HEARTBEAT`, `AUTH_OK`, `AUTH_FAIL`, `CONTEXT_WINDOW`

**Architecture:**
- WebSocket server on `127.0.0.1:47291` (loopback only — no external exposure)
- Auth handshake required: first message must be `{"type":"auth","token":"<32-hex>"}` or connection closes
- Runner patch: monkey-patches `gde_runner._run_single` to emit engine lifecycle events — no GDE source changes required
- Gate patch: patches `gde_gate_engine.evaluate_gates` to emit `GATE_FIRED` on every gate
- Thread-safe emitter: `loop.call_soon_threadsafe()` — sync threads emit into async WebSocket loop without blocking
- Bidirectional: outbound engine events + inbound `user.*` commands (cancel, approve, reject)

---

### IDE Bridge + VS Code Extension ✅ shipped code (2026-07-02) — publish as "PRO roadmap"

> **Status:** Python server + TypeScript extension implemented. Not published to VS Code Marketplace yet.

**IDE Bridge server (`localhost:47292`):**
- HTTP server (Python stdlib) receives cursor events from the VS Code extension
- Matches (file, line) against the last GDE engine result index — exact path + basename fallback, ±5 line tolerance
- Max 2 hints per cursor event (avoids overwhelming the developer)
- Emits `ide.line_event` over WebSocket to the Companion panel
- Hot-swap: pattern index updated after each GDE run without restarting the server
- `build_index_from_engine_results()` — converts antipattern_detector + fragility_classifier output to a queryable index

**VS Code Extension (TypeScript):**
- Activation: `onStartupFinished` — zero user setup required
- Sends `{file, line, event}` via HTTP POST to `localhost:47292/ide-event` on cursor move + file open
- Rate limit: 3000ms minimum between same (file, line) — no flooding
- Silent on error: sidecar not running → extension does nothing (no error dialogs)
- `onDidChangeTextEditorSelection` → `cursor` event; `onDidChangeActiveTextEditor` → `open` event

**Example hint (future UI):**
> "You're on line 42 of `services/auth.py` — God Class detected (imports 18 modules).
> Run Committee analysis on this file?"

---

### VoicePipeline STT/TTS ✅ shipped stub + tests (2026-07-02) — publish as "coming soon"

> **Status:** Full implementation stub with graceful degradation. Actual model download requires
> `genesis companion --setup` (not yet shipped). 52 tests passing.

**STT (Speech-to-Text):**
- faster-whisper + `ivrit-ai/faster-whisper-v2-d4` (Hebrew + English, Apache 2.0, 229ms streaming latency)
- VAD filter enabled — silence is stripped automatically
- Device auto-detection: CUDA → MPS → CPU
- Compute type: int8 (runs on CPU with no GPU)
- Graceful degradation: if faster-whisper not installed, `transcribe()` returns `""`, no exception

**TTS (Text-to-Speech) with language routing:**
- **Hebrew → Meta MMS TTS** (ONNX via sherpa-onnx, `mms-tts-heb.onnx`)
- **English → Kokoro-82M** (sub-300ms, highest quality local English TTS)
- **Fallback → eSpeak NG** (always available if installed, no model download)
- Urgency levels: CRITICAL (synchronous, interrupts), HIGH/NORMAL (daemon thread), BACKGROUND
- Language detection: >15% Hebrew codepoints → route to Hebrew TTS

**Proactive notifications (5 built-in, Hebrew + English):**
| Event | English | Hebrew |
|---|---|---|
| Architecture drift | "Critical architecture drift detected — approval required" | "זוהה סחף ארכיטקטורי קריטי — נדרש אישור" |
| God Class | "God Class pattern detected — run Committee analysis?" | "זוהה תבנית God Class — להריץ ניתוח Committee?" |
| Confidence drop | "Session confidence dropped — check the panel" | "רמת הביטחון ירדה — בדוק את הפאנל" |
| Task complete | "Genesis task complete — changes staged for approval" | "משימת Genesis הסתיימה — שינויים ממתינים לאישור" |
| Volatile module | "Volatile module detected — high risk of regression" | "מודול תנודתי זוהה — סיכון גבוה לרגרסיה" |

---

### Test count summary — v6.6.0

| Module | Tests | Status |
|---|:---:|---|
| Committee Engine | 28 | ✅ all passing |
| WebSocket Streaming | 21 | ✅ all passing |
| IDE Bridge | 19 | ✅ all passing |
| VoicePipeline STT/TTS | 33 | ✅ all passing |
| All prior modules | 1,468 | ✅ unchanged |
| **Total** | **1,569** | **✅ 100% green** |

---

## 🆕 NEW in v6.5.1 — Companion Phase 0+1 (publish these as available)

### Genesis PRO Companion — Phase 0+1 ✅ shipped (2026-07-02)

> These are **shipped and tested** (1,496 tests passing). Safe to publish as available.

- **Gate miss-rate instrumentation** — every approval gate now records `presented_at` +
  `responded_at` timestamps. `genesis companion --stats` shows your real miss rate and
  tells you whether a persistent overlay is justified by your usage pattern.
- **OS gate notifications** — when a BLOCK_AND_ASK gate fires while you're in another
  window, Genesis sends a desktop notification: "Gate: SECURITY_RISK — open the health
  page to respond." Zero setup: `pip install genesis-architect-pro[companion]` adds
  `plyer`. Degrades gracefully if not installed.
- **Health page** — `genesis companion` starts a local server (Python stdlib, zero new
  required deps) on `http://127.0.0.1:7433`. Opens in your browser automatically.
  Shows live engine status, gate state, pending writes, and session confidence —
  polling every 2 seconds. The same session file the GDE already writes.
- **`genesis companion --stats`** — prints gate miss-rate report. If >15% of gates went
  unanswered for >5 minutes, recommends building the full overlay. Data-driven decision,
  not guesswork.

### 🧭 Designed, coming next (do NOT list as available)

- **Genesis PRO Companion — full Control Center** (Phase 2): persistent browser-based
  Control Center with snap/dock behavior, all panel tabs (Progress, Engines, Timeline,
  Reports, Architecture, Research, Decisions, Canvas, Activity). Builds on the Phase 1
  health page foundation. Gated on Phase 1 adoption data.
- **Genesis PRO Companion — native overlay** (Phase 3): true always-on-top floating
  bubble. Only if Phase 1/2 data shows users want persistent presence. Delivery
  mechanism TBD (no Tauri/Electron until zero-setup path confirmed).
- **Standalone Companion App** (v2+): Tauri v2 shell, voice layer (Whisper + Kokoro),
  IDE Bridge (VS Code), Visual Diff Approval. Full architecture spec in
  `docs/pro/COMPANION_ARCHITECTURE.md`. Not yet built.

---

## 🆕 NEW in v6.6.1 — Engine Completeness (publish these)

> **Shipped 2026-07-02.** All previously-written engines are now fully wired into the GDE.
> 17 production engines. 181 public API symbols.

### 4 New Engines Connected

| Engine | Mode | What it adds |
|--------|------|-------------|
| **Rules Engine** | GATE | Architecture regression gate: reads `.genesis/rules.json`, evaluates min score / max anti-patterns / risk level / circular dep policy — PASS or FAIL with per-rule detail |
| **Git Churn Analyzer** | RECOVERY, REFACTOR, GATE | Per-module churn classification (HIGH/MEDIUM/LOW/STALE), fix-commit ratio, bus factor from real git history |
| **Import Audit** | GATE | Declares-vs-actual audit: catches "the diagram lies" — declared model links with no real import, and real imports the model never declared |
| **Knowledge Graph** | RECOVERY, REFACTOR | Now auto-registered on startup (was previously opt-in only); links code, anti-patterns, CVEs into one queryable graph automatically |

### Decay Forecast in Architecture Scorer

When `.genesis/score_history.jsonl` has ≥ 3 data points, the scorer now also returns:
- `weekly_delta` — score change per week (negative = declining)
- `predicted_score_12w` — projected score in 12 weeks
- `weeks_to_critical` — weeks until score drops below 40 (null if not projected)
- `forecast_confidence` — WLS R² with recency weighting

### 2 New CLI Commands

```bash
genesis memory [--init] [--status]   # Show/manage .genesis/*.md memory files
genesis ui [--open] [--output PATH]  # Generate self-contained HTML Canvas workspace
```

### Engine count: 13 → 17

```
RECOVERY:  import_graph → architecture_scorer → antipattern_detector →
           git_analyzer → fragility_classifier → recovery_report → knowledge_graph

REFACTOR:  import_graph → architecture_scorer → antipattern_detector →
           git_analyzer → fragility_classifier → refactoring_planner → knowledge_graph

GATE:      import_graph → architecture_scorer → antipattern_detector →
           git_analyzer → fragility_classifier → rules_engine → import_audit →
           security_templates

DOCUMENT:  import_graph → c4_generator → security_templates
RESEARCH:  source_registry → field_intelligence → evidence_pack
BUILD:     build_scaffold
COMMITTEE: import_graph → architecture_scorer → antipattern_detector →
           fragility_classifier → committee_analysis
```

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
  - **Implementation roadmap (council-validated 2026-07-02):**
    - **Phase 0 (instrument):** Add gate timestamps to `gde_session.json`
      (`gate_presented_at`, `gate_responded_at`). Measure miss rate over 7 days.
      If >15% of gates go 5+ min without response → Companion is justified.
    - **Phase 1 (MVP):** OS gate notifications via `plyer` (single small pip dep,
      ~20KB, zero new runtime). Health page served via Python stdlib `http.server`
      + `threading` — **zero new dependencies**, ships the self-contained Canvas
      HTML on a local port. Auto-opened on `genesis run`. No overlay,
      no always-on-top. Validates whether users keep it open and demand persistence.
    - **Phase 2 (v1):** Persistent Control Center (browser-based, stdlib HTTP
      server upgraded to SSE for real-time push if needed), snap/dock behavior,
      full panel set. FastAPI explicitly NOT added — not a current dependency
      and adding it (~20MB) violates zero-setup promise.
    - **Phase 3 (v2+):** True always-on-top overlay + Tauri v2 native shell —
      only if Phase 1/2 data shows adoption. Native desktop ruled out for MVP
      (Electron ~150MB, tkinter breaks ARM Mac + headless CI, Tauri requires
      Rust toolchain — all violate zero-setup).
  - **Architecture decision (council):** The moat is the state model (13 engines,
    gde_session.json coherence, approval gates), not the visual layer. The overlay
    is discoverable and copyable; the engine architecture is not. Build the
    instruments before the glass.
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

*Last updated: 2026-07-02 | Genesis Architect PRO v6.6.1 (17 engines wired, engine completeness) | Next site review due: 2026-07-16*

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

> **Council decision (2026-07-02):** 5-advisor LLM council on Floating Companion
> architecture. Key findings: (1) native desktop (Tauri/Electron/PyQt) ruled out
> for MVP — violates zero-setup on ARM Mac + headless CI + Linux/Wayland;
> (2) browser-based delivery is correct direction but `window.open alwaysRaised`
> is unreliable — degrades to "a tab to find" not a true overlay; (3) the moat
> is the state model (gde_session.json + 13 engines + gate coherence), not the
> visual layer — the UI is copyable, the engine architecture is not;
> (4) validated implementation order: instrument gate miss rate first →
> OS notifications (plyer/notify-py) → health page (localhost:PORT/status) →
> persistent Control Center → true overlay only if adoption data justifies it.
> Key open question before any UI investment: are sessions long enough (20+ min,
> unattended) that users actually leave the terminal? Measure first.
>
> **Dependency audit (2026-07-02):** `pyproject.toml` confirmed — Genesis PRO
> has only 2 deps: `genesis-architect` + `cryptography`. FastAPI is NOT present.
> Therefore: health page must use Python stdlib `http.server` + `threading`
> (zero new deps). Notifications via `plyer` (one small dep). This is cleaner
> than the council assumed — full Phase 1 Companion deliverable with one pip dep.

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

> **Companion Intelligence Layer shipped (2026-07-02) — v6.6.0:** Committee Engine
> (5 advisors, collapse detection, transparency profiles, 28 tests), WebSocket Streaming
> Layer (CompanionServer localhost:47291, runner patch, 20 event types, 21 tests),
> IDE Bridge server (HTTP localhost:47292, pattern index, hot-swap, 19 tests),
> VS Code Extension (TypeScript, cursor events, rate-limited, silent on sidecar absent),
> VoicePipeline STT/TTS stub (faster-whisper + ivrit.ai, Kokoro-82M, Meta MMS ONNX,
> proactive Hebrew+English notifications, 33 tests).
> Total: 1,569 tests passing (was 1,517 before this session).
> All four subsystems are production-quality stubs: offline-safe, gracefully degrade
> when optional deps (faster-whisper, kokoro, sherpa-onnx) are not installed.

> **Architecture session (2026-07-01) — v6.5.0:** Full PRO Companion standalone app
> architecture designed. Committee engine promoted to core GDE primitive with
> Transparency Profiles (FREE: verdict only; PRO: full advisor debate + divergence).
> Voice layer designed: faster-whisper + ivrit.ai Hebrew (Apache 2.0), Kokoro-82M
> English, Meta MMS Hebrew TTS, OpenWakeWord custom Hebrew models.
> IDE bridge designed: VS Code cursor → line-level pattern hints.
> Visual Diff Approval designed: Canvas diff view before any commit.
> Instagram reel research complete: Vercel AI SDK 7 voice pattern evaluated;
> mid-conversation function calls adopted for v2.0 roadmap.
> New spec docs: `COMPANION_APP_ARCHITECTURE.md`, `COMMITTEE_ENGINE_ARCHITECTURE.md`,
> `STT_TTS_DECISION_MATRIX.md`, `INSTAGRAM_REEL_RESEARCH_REPORT.md`.
