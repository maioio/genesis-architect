# Genesis Architect PRO — Website Update Report

> **For the website agent:** read this file top to bottom before touching the site.
> This is the **single source of truth** for every feature, its readiness state, and the
> exact copy the landing page should reflect.
> Always check **version + Last updated** before a site refresh.

---

## 🚦 Version & Status

**Current product version: v7.2.0**
**Last updated: 2026-07-03**
**Next site review due: 2026-07-17**

> 🆕 **v7.2.0 (2026-07-03):** Full test coverage pass — 1,721 tests, 0 failures.
> Added `test_voice_pipeline_orchestrator.py` (34 tests: EntityExtractor, ContextPrefetcher,
> BargeInWatcher, VoicePipeline) and `test_package_registry.py` (38 tests: PyPI/npm/crates adapters,
> dispatcher, score_packages). Fixed EntityExtractor keyword-regex false-positive (word-boundary guard).
> All source modules now have explicit test coverage.

> 🆕 **v7.1.0 (2026-07-03):** Voice companion upgraded to three alive-feeling behaviors:
> **streaming VAD end-of-turn detection** (replaces fixed-duration recording — mic closes after ~600ms silence);
> **barge-in** (`TTSPipeline.stop()` + cancel token — bot goes silent the instant you speak);
> **mid-turn context prefetch** (entity extraction from partial transcript → parallel KG + fragility lookup before you finish speaking).
> `VoicePipeline` orchestrator added. `webrtcvad` added to `[voice]` extra. 1,649 tests. Pro-only.

> 🆕 **Phase 4 — Distribution Pipeline (2026-07-03):** GitHub Actions matrix build
> wired: push `companion-v*` tag → CI builds **Windows MSI / macOS DMG / Linux AppImage**
> in parallel and publishes a draft GitHub Release + `latest.json` update manifest.
> **`tauri-plugin-updater` wired** — auto-update works once signing keys are in place.
> **VS Code extension** gains `vsce package/publish` scripts + separate CI workflow.
> **Code signing guide** written (`companion/docs/code-signing.md`) — Windows Authenticode
> + macOS notarization + Tauri Ed25519 key. 1,649 tests (+25 from Phase 3 intelligence
> wiring). Pro-only, on `pro/main`. **Ready to ship on first tag.**

> 🆕 **Turnkey milestone (2026-07-03):** the Companion is now a real, installable
> product. The **Tauri desktop app builds** → `genesis-companion.exe` + Windows
> **MSI** + **setup.exe** (verified). **Voice is complete** — `genesis companion
> --listen` runs a live wake-word loop ("genesis" / "ג'נסיס"). The **VS Code
> extension packages** to a `.vsix`. All three are **early access** (unsigned /
> not on stores) — keep them "early access / coming soon" on the site until code
> signing + store publish. 1,624 tests. Pro-only, on `pro/main`.

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
| **WebSocket Streaming Layer** | ✅ Has a client now | Installable (`[streaming]`); the Floating Assistant web UI consumes it end-to-end. The Tauri desktop shell also consumes the same stream (Panel↔Bubble IPC bridge wired). |
| **Voice (STT/TTS + live mic + wake word + barge-in + streaming VAD + prefetch)** — faster-whisper + Kokoro + Meta MMS Hebrew | ⚙️ Self-serve, complete | `genesis companion --setup` downloads models; `--listen` runs a live wake-word loop ("genesis" / "ג'נסיס"); `--check` / `--speak` verify. Streaming VAD end-of-turn (no fixed duration), barge-in (bot goes silent instantly), mid-turn entity prefetch all implemented. VoicePTT wired in Tauri Panel. 1,721 tests. Present as "early access" until pre-bundled. |
| **VS Code extension** | ⚙️ CI pipeline ready | `genesis-companion-0.1.0.vsix` compiles + packages; installable via "Install from VSIX". `vscode-extension.yml` CI workflow builds + publishes on `vscode-v*` tag. **Needs `VSCE_PAT` secret** for Marketplace publish. |
| **Tauri standalone desktop app** | ⚙️ Distribution pipeline ready | **`tauri build` succeeds:** produces `genesis-companion.exe` + Windows **MSI** + **NSIS setup.exe**. **GitHub Actions `companion-release.yml`** builds Windows/macOS/Linux in parallel on `companion-v*` tag. `tauri-plugin-updater` wired (auto-update). **Needs code signing certs** before public distribution (SmartScreen/Gatekeeper). Present as "early access". |

**Publish rule:**
- ✅ = announce as *available today*
- ⚙️ / 🚧 = **"coming soon" / roadmap only** — never as a shipped feature

---

## 🌐 Site sync status

| Surface | Location | Version | Status |
|---------|----------|:-------:|--------|
| Free landing (LIVE, React) | `genesis-react` → `main:docs/` | v7.2.0 | ✅ in sync — CHANGELOG, ROWS, NEW_PRO cards, pricing bullets all updated |
| Pro page (static draft, NOT live) | `docs/pro.html` | v6.4.0 | ⚠️ not the live site |
| This report (source of truth) | `docs/WEBSITE_UPDATE_REPORT_v6.1.0.md` | **v7.2.0** | ✅ current |

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
- **Research Source Registry — 30 sources, 11 tiers, priority-ordered** (engineering truth first, market signal last):
  - Tier 1 · official (priority 100): Official docs, API docs, SDK docs + RFCs / specifications
  - Tier 2 · local (priority 99): Source code, tests, CI logs, TODO/FIXME markers, crash reports
  - Tier 3 · security (priority 98): OSV.dev, NVD, CVE (MITRE), GitHub Security Advisories, Snyk DB
  - Tier 4 · source (priority 97): GitHub REST API, GitHub GraphQL API, GitHub Issues/PRs/Discussions, Releases/changelogs/git history
  - Tier 5 · qa (priority 90): Stack Overflow (API), Stack Exchange (advanced search)
  - Tier 6 · packages (priority 88): PyPI, npm, crates.io, Maven Central, NuGet
  - Tier 7 · field (priority 85): Reddit, Reddit Answers (AI layer), Hacker News, Lobste.rs
  - Tier 8 · blog (priority 82): DEV.to, Hashnode, Company engineering blogs
  - Tier 9 · research (priority 80): arXiv, Papers with Code
  - Tier 10 · learning (priority 76): YouTube (transcripts, conference talks)
  - Tier 11 · market (priority 40): Instagram — demand/trend signal ONLY; never presented as engineering truth
  - **5 engine profiles**: research_intelligence · developer_field · security · project_discovery · recovery
  - Extensible per-project without code changes; JSON-configurable
- **Evidence Packs** — proof behind every recommendation, with honest confidence grade
- **Memory + Decision Journal** — per-project `.genesis/*.md`; every significant decision journaled
- **Floating Assistant + Canvas Workspace** — zero-setup visual workspace (no Node, no build, no server)
- **`genesis companion`** — local health page, gate miss-rate stats, OS notifications on gate fires
- **Anonymous Product Intelligence** — opt-in, default-off, privacy enforced in code (not trust)
- **Four-step install, no Docker** — Download → Install → License → Work
- **Works fully offline** — local analysis never needs a network; online sources honestly marked when unavailable
- **26-page documentation** — the complete "Read the docs" technical layer

---

### 📊 Comparison table — exact agent instructions

> **SITE AGENT: These are the exact labels to use in the Free/Pro comparison table.**
> Do NOT abbreviate. Do NOT summarize to just "GitHub, Reddit, YouTube, IG".
> The whole point is to show the systematic architecture we built.

| Row # | Label (exact text) | Free | Pro |
|---|---|---|---|
| 1 | Full scaffolder — Python, TypeScript, Go, Rust | ✓ | ✓ |
| 2 | CI/CD pipelines, security defaults, language templates | ✓ | ✓ |
| 3 | Top 3 GitHub pitfalls per project (cited, CI-verified) | ✓ | ✓ |
| 4 | **30-source research across 11 tiers** — official docs + RFCs (priority 100) · local code (99) · OSV / NVD / CVE / Snyk (98) · GitHub REST + GraphQL + Issues + Releases (97) · Stack Overflow / Stack Exchange (90) · PyPI / npm / crates / Maven / NuGet (88) · Reddit / Hacker News / Lobste.rs (85) · DEV.to / Hashnode / engineering blogs (82) · arXiv / Papers with Code (80) · YouTube talks (76) · market signal (40). Engineering truth first, market signal last. | ✗ | ✓ |
| 5 | Cross-source pitfall ranking + Evidence Packs (proof behind every recommendation) | ✗ | ✓ |
| 6 | Video-to-pitfall extraction (conference talks → concrete warnings) | ✗ | ✓ |
| 7 | Package-registry + CVE validation — PyPI, npm, crates.io, Maven, NuGet | ✗ | ✓ |
| 8 | Architecture score 0–100 + 7 anti-pattern detectors (god class, circular deps, dead code, hub files, feature envy, leaky abstraction, shotgun surgery) | ✗ | ✓ |
| 9 | STABLE / FRAGILE / VOLATILE risk map — every file rated with GO / HOLD / REWRITE | ✗ | ✓ |
| 10 | Architecture decay forecast — weekly delta, weeks-to-critical, trend history | ✗ | ✓ |
| 11 | Recovery scan + executable refactoring plan for existing codebases (`genesis recover .`) | ✗ | ✓ |
| 12 | C4 architecture diagrams auto-generated (Mermaid, renders natively on GitHub) | ✗ | ✓ |
| 13 | STRIDE threat model + OWASP Top 10 checklist, tailored to your project type | ✗ | ✓ |
| 14 | Genesis Decision Engine — plain-English instruction → auto-routes to 7 modes, 17 engines, deterministic (no LLM for routing) | ✗ | ✓ |
| 15 | 12-gate approval policy — 2 gates are hard-locked and can never be bypassed, even by you | ✗ | ✓ |
| 16 | Rules gate + git churn + import audit — catches when the diagram lies | ✗ | ✓ |
| 17 | Cross-session memory + Decision Journal — every significant choice recorded in .genesis/*.md | ✗ | ✓ |
| 18 | Cross-source Knowledge Graph — code ↔ CVEs ↔ risks ↔ decisions, one queryable graph | ✗ | ✓ |
| 19 | Committee Engine — 5-advisor debate (Contrarian, First Principles, Expansionist, Outsider, Executor), manufactured-consensus detection, full transcript | ✗ | ✓ |
| 20 | Autonomous maintenance — `genesis sync` on a schedule: GREEN auto-applies, YELLOW queues for review, RED blocks and alerts. Never edits your source. | ✗ | ✓ |
| 21 | Companion web UI — floating assistant, live 17-engine stream, gate approvals (`genesis companion --ui`) | ✗ | ✓ |
| 22 | Voice pipeline — streaming VAD end-of-turn, barge-in, mid-turn entity prefetch, Hebrew + English TTS, local transcription (nothing leaves your machine) | ✗ | ✓ |

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
genesis companion --listen                # Live wake-word loop ("genesis" / "ג'נסיס")
genesis companion --ui                    # Launch Floating Assistant web UI
```

---

## 🗓️ Coming soon — roadmap (do NOT list as available)

### Voice — early access (⚙️)
- faster-whisper STT (Hebrew + English, 229ms streaming latency)
- Meta MMS TTS Hebrew (ONNX, `mms-tts-heb.onnx`)
- Kokoro-82M English TTS (sub-300ms, highest-quality local English)
- Wake word: "genesis" / "ג'נסיס" — VAD-gated (not fixed-duration polling)
- **Streaming VAD end-of-turn** — turn closes after ~600ms silence; no fixed duration
- **Barge-in** — `TTSPipeline.stop()` + cancel token; bot goes silent instantly on speech onset
- **Mid-turn context prefetch** — entity extraction → parallel KG + fragility lookup before utterance ends; `VoicePipeline` orchestrator wired
- **Remaining before GA:** voice models must be downloaded via `genesis companion --setup`; not pre-bundled. → Present as "early access"

### Tauri Standalone Desktop App (⚙️ — ready to distribute pending signing)
- All 4 phases complete: Python backend, Tauri Rust+TS app, intelligence wiring, distribution pipeline
- `companion-release.yml` builds Windows MSI / macOS DMG / Linux AppImage on `companion-v*` tag
- `tauri-plugin-updater` wired — auto-update works once signing keys are added
- **Remaining before GA:** add GitHub Secrets (TAURI_SIGNING_PRIVATE_KEY, APPLE_*, Windows cert)
- → Present as "early access"

### IDE Bridge / VS Code Extension (⚙️ — ready to publish pending PAT)
- HTTP server live after GDE run (port 47292), pattern index hot-swapped after every GDE run
- TypeScript extension source complete, `vscode-extension.yml` CI workflow packages + publishes
- **Remaining before Marketplace:** open `genesis-pro` publisher account, add `VSCE_PAT` secret
- → Present as "early access"

### WebSocket Streaming Layer (✅ — both web UI and Tauri Panel consume it)
- CompanionServer on `127.0.0.1:47291`, 20 event types, auth handshake, bidirectional
- Web UI (`genesis companion --ui`) + Tauri Panel both consume the same stream
- Panel→Bubble IPC bridge mirrors all events to Bubble via Tauri native events
- → Installable today with `[streaming]` extra

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
| v7.2.0 | 2026-07-03 | Full coverage pass: test_voice_pipeline_orchestrator (34 tests) + test_package_registry (38 tests). EntityExtractor word-boundary fix. 1,721 tests, 0 failures. All source modules covered. |
| v7.1.0 | 2026-07-03 | Voice 3 alive behaviors: streaming VAD end-of-turn, barge-in (TTSPipeline.stop()), mid-turn context prefetch (EntityExtractor + ContextPrefetcher + BargeInWatcher + VoicePipeline orchestrator). webrtcvad added to [voice]. 1,649 tests. |
| v7.0.0 | 2026-07-03 | Companion Phase 4 — Distribution Pipeline: GitHub Actions matrix build (Win/Mac/Linux), tauri-plugin-updater + auto-update, vscode-extension CI, code signing guide, latest.json template. 1,649 tests. |
| v6.9.0 | 2026-07-03 | Phase 3 Intelligence Wiring: Gate Resume Flow (approve→commit), VoicePTT (Web Audio→WAV→STT→GDE), IDE Bridge hot-swap post-GDE, Panel↔Bubble IPC bridge. +25 tests. |
| v6.8.0 | 2026-07-02 | Companion Phase 2 — Tauri App Scaffold: Rust sidecar, 6 commands, Zustand store, WS client, 7 React components, design tokens. `tauri build` → .exe + MSI verified. |
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
