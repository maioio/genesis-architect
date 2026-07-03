# Genesis Architect PRO — Website Update Report

> **For the website agent:** read this file top to bottom before touching the site.
> This is the **single source of truth** for every feature, its readiness state, and the
> exact copy the landing page should reflect.
> Always check **version + Last updated** before a site refresh.

---

## 🚦 Version & Status

**Current product version: v6.8.0**
**Last updated: 2026-07-03**
**Next site review due: 2026-07-17**

> 🆕 **This session (2026-07-03):** the **Floating Assistant web UI** is now real
> and wired end-to-end. `genesis companion --ui` starts the full backend and opens
> a draggable bubble ↔ chat panel in the browser; a typed instruction runs a real
> Decision Engine session and **7 engines stream live progress back** (verified).
> Fixed a wire-protocol mismatch that was silently dropping the UI's messages.
> **Still "early access / coming soon" on the site** — needs the `[streaming]`
> extra and is not yet a one-click desktop app. See the readiness matrix row.
> `render_companion_html` / `write_companion_html` + `progress_report` (downloadable
> HTML phase reports) shipped in the package. 1,611 tests. Pro-only, on `pro/main`.

---

## 🚦 Customer-Readiness Matrix — THE publish gate

> A feature may be code-complete and tested yet **not usable by a paying customer**.
> Only publish a feature as *available now* if its row says ✅.

| Capability | State | Can a customer USE it today? |
|---|---|---|
| **Analysis engines (17)** — score, anti-patterns, fragility, C4, security, knowledge graph | ✅ Shipped | **Yes.** Core product. Works offline. |
| **Genesis Decision Engine** — `genesis decide / explain` | ✅ Shipped | **Yes.** Full CLI + Rich TUI. |
| **genesis sync** — autonomous weekly maintenance (GREEN/YELLOW/RED zones) | ✅ Shipped | **Yes.** Weekly cron + GitHub Actions + manual trigger. |
| **genesis memory** — per-project `.genesis/*.md` memory + decision journal | ✅ Shipped | **Yes.** |
| **genesis ui** — self-contained HTML Canvas workspace (no build, no server) | ✅ Shipped | **Yes.** |
| **genesis companion** — local health page + gate miss-rate stats | ✅ Shipped | **Yes.** |
| **Committee Engine** — 5-advisor debate, collapse detection, transparency profiles | ✅ Shipped | **Yes**, via CLI/API. |
| **Floating Assistant (web UI)** — `genesis companion --ui`: bubble ↔ chat panel, live multi-engine progress, approvals, quick actions | ⚙️ Early access | **Partly.** One command starts the backend + opens the assistant in a browser; chat drives a real GDE session and 7 engines stream live progress back (verified end-to-end). Needs the `[streaming]` extra. Zero build. Present as "early access / coming soon". |
| **WebSocket Streaming Layer** | ✅ Has a client now | Installable (`[streaming]`); the Floating Assistant web UI consumes it end-to-end. The Tauri desktop shell will consume the same stream. |
| **Voice (STT/TTS)** — faster-whisper + Kokoro + Meta MMS Hebrew | ⚙️ Self-serve | `genesis companion --setup` downloads models; `--check` + `--speak` verify the round-trip. Not yet one-click. Present as "coming soon / early access". |
| **IDE Bridge / VS Code extension** | 🚧 Source only | Not compiled, no `.vsix`, not on marketplace. |
| **Tauri standalone desktop app** | 🚧 Phase 1–3 built (28 files) | Needs `cargo build` + code signing. Phase 4 = distribution. Not shippable yet. |

**Publish rule:**
- ✅ = announce as *available today*
- ⚙️ / 🚧 = **"coming soon" / roadmap only** — never as a shipped feature

---

## 🌐 Site sync status

| Surface | Location | Version | Status |
|---------|----------|:-------:|--------|
| Free landing (LIVE, React) | `genesis-react` → `main:docs/` | v6.6.1 | ⏳ needs sync — add `genesis sync` + v6.7/v6.8 features |
| Pro page (static draft, NOT live) | `docs/pro.html` | v6.4.0 | ⚠️ not the live site |
| This report (source of truth) | `docs/WEBSITE_UPDATE_REPORT_v6.1.0.md` | **v6.8.0** | ✅ current |

> **Which file is actually live:** the published site at https://maioio.github.io/genesis-architect/
> is the **React app** built from `C:\temp\genesis-react` (Vite), published to `main:docs/`.
> The static `docs/index.html` / `docs/pro.html` in `pro-v*` branches are **not** what visitors see.
> To publish: edit `genesis-react` → `npm run build` → copy `dist/` into a clean `git worktree` of `main` → push.
> **NEVER push a `pro-v*` branch to `main`.**

---

## ✅ What to put on the landing page (everything available today)

### Hero copy

> Genesis PRO analyzes your existing codebase — not just new projects.
> Point it at any repo and get an architecture score, a risk map of every file,
> a prioritized refactoring plan, C4 diagrams, and a security checklist.
> All in under 30 seconds. No LLM required for the analysis.
>
> One plain-English instruction routes automatically to the right engines,
> in the right order, with built-in safety gates that can never be bypassed.
>
> A cross-source **Knowledge Graph** connects your code, CVEs, risks and decisions —
> so Genesis can tell you which "do-not-touch" module has a live vulnerability.
>
> And now: **Genesis runs itself.** Autonomous weekly maintenance checks your
> architecture, flags drift, and queues improvements — while you sleep.

---

### Feature bullets — Codebase Intelligence

- Architecture score **0–100** with trend history and decay forecast (weekly delta, weeks-to-critical)
- **7 anti-pattern detectors** — god class, circular deps, dead code, hub files, feature envy, leaky abstraction, shotgun surgery
- **STABLE / FRAGILE / VOLATILE risk map** — every file, with GO / HOLD / REWRITE recommendation
- **Executable refactoring plan** — tier-1 blocking issues first, tier-2 improvements after
- **Auto-generated C4 architecture diagrams** (Mermaid, renders natively on GitHub)
- **STRIDE threat model + OWASP Top 10 checklist**, tailored to your project type
- Works on Python, JavaScript, TypeScript, Go, Rust
- `genesis recover .` — one command, full codebase health report in under 30 seconds

### Feature bullets — Genesis Decision Engine

- Type any instruction in plain English — GDE routes it to the right engines automatically
- **No LLM required for routing** — deterministic, sub-millisecond, always consistent
- **17 production engines** wired across 7 modes: RECOVERY, REFACTOR, GATE, DOCUMENT, RESEARCH, BUILD, COMMITTEE
- Parallel execution: independent engines run concurrently within each phase
- **12-gate approval policy** — 2 gates can never be bypassed, even by you
- **APPROVE → COMMIT lifecycle**: inspect pending writes before anything touches disk
- Atomic writes: all file operations use tmp→rename — no partial writes on crash
- **Confidence score** on every session — know exactly how reliable the output is
- **Full decision log** — every choice recorded, always auditable
- **Crash-safe session persistence** — resume exactly where you left off
- Only tool in the market with all 5 decision-engine capabilities (verified against 11 competitors)

### Feature bullets — Autonomous Sync Manager (NEW v6.7.0)

- **`genesis sync`** — runs a full GATE check on a schedule (weekly cron / GitHub Actions)
- **3-zone approval scope:**
  - 🟢 **GREEN** — auto-applied: score history, fragility map refresh, sync log
  - 🟡 **YELLOW** — queued to `.genesis/pending.json` for human review: rule failures, decay trend, high churn
  - 🔴 **RED** — blocks and alerts only: critical anti-patterns, score below 55, hard gate failures
- **Never touches source code autonomously** — only metrics, docs, and findings files
- **GitHub Actions workflow** included — runs every Sunday 02:03 UTC, auto-commits GREEN writes, opens PR for YELLOW, opens issue for RED
- **`genesis sync --dry-run`** — analyse without writing; `--json` for CI pipelines
- Configurable via `.genesis/sync_config.json`

### Feature bullets — AI Engineering Partner

- **Knowledge Graph** — links code, CVEs, risks and decisions; finds do-not-touch zones with an open CVE (nothing else on the market does this)
- **Committee Engine** — 5-advisor debate (Contrarian, First Principles, Expansionist, Outsider, Executor), manufactured-consensus detection, full debate transcript in PRO
- **Learning Engine** — improves which research strategy it picks for your task kind, with honest confidence
- **Research Source Registry** — 25+ ranked sources, extensible per-project without code changes
- **Reddit Answers workflow** — verified developer field intelligence (never treated as final truth)
- **Evidence Packs** — proof behind every recommendation, with honest confidence grade
- **Memory + Decision Journal** — per-project `.genesis/*.md`; every significant decision journaled
- **Floating Assistant + Canvas Workspace** — zero-setup visual workspace (no Node, no build, no server)
- **`genesis companion`** — local health page, gate miss-rate stats, OS notifications on gate fires
- **Anonymous Product Intelligence** — opt-in, default-off, privacy enforced in code (not trust)
- **Four-step install, no Docker** — Download → Install → License → Work
- **Works fully offline** — local analysis never needs a network; online sources honestly marked when unavailable
- **26-page documentation** — the complete "Read the docs" technical layer

### Feature bullets — CLI (full list of shipped commands)

```bash
# Decision Engine
genesis decide "diagnose the project and identify drift"   # Full session
genesis decide --classify-only "generate C4 diagrams"      # Intent only
genesis decide --yes "run a full recovery scan"             # Auto-approve (CI)
genesis decide --no-commit "check compliance"               # Analysis only
genesis explain                                             # Print last decision log

# Autonomous Sync
genesis sync                        # Run full maintenance check
genesis sync --dry-run              # Analyse only, no writes
genesis sync --auto-apply           # Apply GREEN zone writes
genesis sync --json --ci-mode       # Structured output for CI pipelines

# Direct engine commands
genesis score .                           # Architecture score 0-100
genesis score . --profile microservices   # Score with adaptive profile
genesis antipattern .                     # Detect all 7 anti-patterns
genesis antipattern . --json              # Machine-readable output
genesis recover .                         # Full recovery report (all engines)
genesis harden .                          # STRIDE + OWASP + secrets scan

# Project memory & workspace
genesis memory [--init] [--status]        # Manage .genesis/*.md memory files
genesis ui [--open] [--output PATH]       # Generate HTML Canvas workspace

# Companion (health page)
genesis companion                         # Start local health page (port 7433)
genesis companion --stats                 # Gate miss-rate report
genesis companion --setup                 # Download voice models (STT/TTS)
genesis companion --check                 # Verify voice readiness
genesis companion --speak "Hello"         # Test TTS round-trip
```

---

## 🗓️ Coming soon — roadmap (do NOT list as available)

### Voice — early access (⚙️)
- faster-whisper STT (Hebrew + English, 229ms streaming latency)
- Meta MMS TTS Hebrew (ONNX, `mms-tts-heb.onnx`)
- Kokoro-82M English TTS (sub-300ms, highest-quality local English)
- Wake word: "Genesis, start" / "ג'נסיס, תתחיל"
- **Remaining gap:** live microphone capture loop + wake-word detector. Currently transcribes supplied audio, not a live mic stream. Verify on a clean machine. → Present as "early access / coming soon"

### Tauri Standalone Desktop App (🚧)
- Phase 1–3 complete: 28 Rust+TypeScript files, Panel↔Bubble IPC bridge, Gate Resume Flow, IDE Bridge hot-swap, Voice PTT (Web Audio → WAV → base64 → STT)
- **Phase 4 remaining:** distribution packaging, code signing
- → Present as "coming soon"

### IDE Bridge / VS Code Extension (🚧)
- HTTP server live after GDE run (port 47292), pattern index built from engine results
- TypeScript extension source complete, cursor events, rate-limited, silent on sidecar absent
- **Remaining:** compile to `.vsix`, publish to VS Code Marketplace
- → Present as "coming soon"

### WebSocket Streaming Layer (⚙️)
- CompanionServer on `127.0.0.1:47291`, 20 event types, auth handshake, bidirectional
- Installable today with `[streaming]` extra, but no UI client consumes it yet
- → Present as "coming soon"

---

## 🔢 Engine reference — all 17 production engines

| # | Engine | Modes | What it does |
|---|--------|-------|-------------|
| 1 | Import Graph | RECOVERY, REFACTOR, GATE, DOCUMENT, COMMITTEE | Multi-language dependency graph, cycles, dark modules, layer map |
| 2 | Architecture Scorer | RECOVERY, REFACTOR, GATE, COMMITTEE | 0–100 score across 4 dimensions, 6 adaptive profiles, decay forecast |
| 3 | Anti-Pattern Detector | RECOVERY, REFACTOR, GATE, COMMITTEE | 7 structural anti-patterns (God Class, Hub File, Circular Dep, Dead Code, etc.) |
| 4 | Fragility Classifier | RECOVERY, REFACTOR, GATE, COMMITTEE | VOLATILE / FRAGILE / STABLE per module; writes FRAGILITY_MAP.md |
| 5 | Recovery Report | RECOVERY | Consolidated PROJECT_RECOVERY_REPORT.md with risk level + recommendations |
| 6 | Refactoring Planner | REFACTOR | Tier-1 (blocking) + Tier-2 (improvements) executable plan |
| 7 | C4 Generator | DOCUMENT | Level 1–3 C4 diagrams in Mermaid; writes C4_ARCHITECTURE.md |
| 8 | Security Templates | GATE, DOCUMENT | STRIDE threat model + OWASP Top 10 checklist, project-type aware |
| 9 | Source Registry | RESEARCH | Loads ranked 25+ source catalog |
| 10 | Field Intelligence | RESEARCH | Reddit Answers developer sentiment, claim verification |
| 11 | Evidence Pack | RESEARCH | Structured evidence pack with honest confidence grades |
| 12 | Build Scaffold | BUILD | Delegates to free-core scaffolder |
| 13 | Rules Engine | GATE | Architecture regression gate; reads `.genesis/rules.json`; per-rule PASS/FAIL |
| 14 | Git Churn Analyzer | RECOVERY, REFACTOR, GATE | Per-module churn (HIGH/MEDIUM/LOW/STALE), fix ratio, bus factor |
| 15 | Import Audit | GATE | Declared vs actual import edges — "the diagram lies" detection |
| 16 | Knowledge Graph | RECOVERY, REFACTOR | Cross-source graph (code, CVEs, decisions, risks); auto-registered on startup |
| 17 | Committee Analysis | COMMITTEE | 5-advisor debate, collapse detection, divergence map |

---

## 💰 Pricing (live on site)

- **Founder pricing:** $9/mo or $90/yr (2 months free) — first 50 seats locked for life
- **Standard pricing:** $19/mo or $190/yr
- **Free tier:** genesis-architect core (public, open-source); no codebase intelligence engines

---

## 🔁 Maintenance protocol (for the assistant — do not delete)

- **Update this file in the same change** whenever a customer-visible capability ships
- On each update: bump the **version**, update the customer-readiness matrix, and update the "Last updated" line
- **Site-refresh cadence:** every 2 weeks minimum, and always after a capability ships
- If ≥14 days have passed since "Last updated" while work continued, proactively remind the user that the site is due for a refresh
- **Honesty rule:** never list a capability here as available unless it is actually shipped + tested

---

## 📋 Milestone history (for reference — do not publish verbatim)

| Version | Date | What shipped |
|---------|------|-------------|
| v6.8.0 | 2026-07-02 | Companion Phase 3 — Intelligence Wiring: Panel↔Bubble IPC, Gate Resume Flow, IDE Bridge hot-swap, Voice PTT. Tauri: 28 files total. |
| v6.7.0 | 2026-07-02 | Autonomous Sync Manager: `genesis sync`, 3-zone approval scope, GitHub Actions workflow, sync_config.json, pending.json queue |
| v6.6.1 | 2026-07-02 | Engine completeness: 17 engines wired (rules_engine, git_analyzer, import_audit, knowledge_graph auto), decay forecast in scorer, `genesis memory` + `genesis ui` CLI, 181 public API symbols |
| v6.6.0 | 2026-07-02 | Companion Intelligence Layer: Committee Engine (28 tests), WebSocket Streaming (21 tests), IDE Bridge (19 tests), VoicePipeline stub (33 tests). 1,569 total tests. |
| v6.5.1 | 2026-07-02 | Companion Phase 0+1: gate miss-rate instrumentation, OS notifications, health page server (stdlib, zero new deps), `genesis companion` CLI. 1,496 tests. |
| v6.5.0 | 2026-07-01 | Architecture specs: PRO Companion standalone app, Committee engine as GDE primitive, STT/TTS decision matrix |
| v6.4.0 | 2026-06-29 | Rich CLI TUI, all 7 GDE modes wired (13 engines), intent classifier calibration, UI Engine (Floating Assistant + Canvas), Memory Engine + Decision Journal |
| v6.3.0 | — | Research Source Registry, Reddit Answers workflow, Evidence Packs |
| v6.2.0 | — | Knowledge Graph Engine, Learning Engine, Product Intelligence, no-setup packaging, 26-page docs |
| v6.1.0 | — | Genesis Decision Engine (full INTAKE→PLAN→EXECUTE→GATE→COMMIT lifecycle, 12 gates) |
| v6.0.0 | — | 8 new codebase intelligence engines: Import Graph, Arch Scorer, Anti-Pattern, Git Churn, Fragility, Refactoring Planner, C4 Generator, Security Templates |
