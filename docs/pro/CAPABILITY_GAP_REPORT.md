# Genesis PRO — Capability Gap Report
<!-- Generated after deep audit of architect (camilooscargbaptista) and scryer (aklos) -->
<!-- Original date: 2026-06-27 | Updated: 2026-07-03 — all G-CRIT gaps now implemented -->

> **Update 2026-07-03:** G-CRIT-01, G-CRIT-02, G-CRIT-03, and G-CRIT-06 are all
> implemented. See the status table below. The "Critical Gaps" section is kept for
> historical reference; current status is ✅ for all four.

## Audit Basis

Two repositories audited to exhaustion:
- `architect` — TypeScript monorepo, mature metric scoring, temporal forecasting, CI/agent generation
- `scryer` — Rust + Tauri, C4 model substrate, drift detection, dual-layer planned/committed design

Genesis PRO current state assessed against every discovered capability (116 total).

---

## Current Genesis PRO Inventory

| Module | Capability |
|--------|-----------|
| `import_graph.py` | Dependency graph construction, cycle detection, layer classification, Python/TS/JS |
| `architecture_scorer.py` | 4-metric scoring (modularity/coupling/cohesion/layering), adaptive profiles, score history |
| `antipattern_detector.py` | 7 anti-patterns (God Class, Hub File, Circular Dep, Dead Code, Feature Envy, Leaky Abstraction, Shotgun Surgery) |
| `git_analyzer.py` | Per-file churn, fix-ratio, last-touched, churn level classification |
| `fragility_classifier.py` | STABLE/FRAGILE/VOLATILE per module combining anti-patterns + churn + test coverage |
| `refactoring_planner.py` | 5-rule refactoring plan (hub-splitter, god-class-splitter, cycle-breaker, dead-code, layer-fix) |
| `c4_generator.py` | Mermaid C4 diagrams (L1 Context, L2 Container, L3 Component) from evidence.json |
| `security_templates.py` | STRIDE/OWASP security pattern templates |
| `research_orchestrator.py` | GitHub repo research, pitfall mining |
| `cross_session_memory.py` | Persistent session memory |
| `license.py` | Ed25519 Pro license gate |
| `package_registry.py` | Package metadata lookup |
| `recovery_scan.py` | Basic recovery workflow |

---

## Critical Gaps — Implementation Status (2026-07-03)

| Gap | Implemented | Location |
|-----|-------------|---------|
| G-CRIT-01 Dual-Layer Model | ✅ | `model_store.py` — `load_planned()`, `save_planned()`, `mark_implemented()`, `is_planned_diverged()` |
| G-CRIT-02 Model Diff Engine | ✅ | `model_store.py` — `_compute_diff()`, `ModelDiff`, `NodeChange`, `ResponsibilityChange`, `LinkChange` |
| G-CRIT-03 Source Anchors | ✅ | `source_anchor.py` — 3-pass matcher, `AnchorReport`, `persist_anchors()` |
| G-CRIT-06 WLS Decay Regression | ✅ | `decay_regressor.py` — full WLS, R², t-test, 95% CI, threshold crossing, human summary |

---

## Critical Gaps — Original Analysis (kept for reference)

### G-CRIT-01: Dual-Layer Architecture Model (planned vs. committed)
- **What's missing:** Genesis has no concept of intended vs. verified architecture. Every analysis is current-state only. There is no way to express "I intend to refactor auth into a separate module" without immediately changing code.
- **Scryer's approach:** `.scryer/planned.scry` vs `model.scry`. Agent writes to planned; `mark_implemented` folds planned into committed once code backs it.
- **Impact:** Without this, Genesis cannot support design-first workflows, cannot show "what will be true" vs "what is true now", and cannot prevent planning-commit confusion.

### G-CRIT-02: Model Diff Engine
- **What's missing:** No way to compute a git-status-style diff between two architecture states.
- **Scryer's approach:** Typed `Change` enum (Added, Deleted, Moved, Repointed, Reworded, MembersChanged); stable IDs per element so a reparent is `Moved`, not delete+add.
- **Impact:** Users cannot see what changed between runs, cannot review planned vs. current, cannot generate meaningful PRs about architecture changes.

### G-CRIT-03: Source-Level Responsibility Anchoring
- **What's missing:** Genesis maps modules to files but cannot anchor a specific responsibility to a specific file+line range. The C4 generator produces diagrams but they are not backed by source evidence.
- **Scryer's approach:** `source_map: HashMap<String, Vec<SourceLocation>>` with `line`/`endLine` per responsibility; a "range covering the whole symbol is stripped to the symbol anchor."
- **Impact:** Without source anchors, "Auth validates JWT" is unverifiable. Cannot detect drift (code no longer does what the model claims).

### G-CRIT-04: Prompt Budget Manager
- **What's missing:** No mechanism to prevent LLM context overflow when refactoring large codebases. Currently, all file content is passed to the LLM regardless of token cost.
- **Architect's approach:** `core-target` (always full), `important-context` (if budget permits), `consumer-ref` (abbreviated: first 20 lines + exports + last 5). Model-specific presets (Claude-3: 60k tokens, Qwen-32b: 8k).
- **Impact:** Genesis fails silently on large repos. 500KB+ prompts exceed context windows without warning.

### G-CRIT-05: Drift Flags (vagrant + stale)
- **What's missing:** No machine-observation flags on responsibilities. Genesis detects issues but cannot mark them as "discovered in code, awaiting user verdict" (vagrant) or "model claims this but code no longer does it" (stale).
- **Scryer's approach:** `vagrant: true` on a responsibility = code-discovered claim not yet committed to model. `stale: true` = committed claim whose code no longer backs it. User resolves each: adopt (clear flag) or reject (delete, signal agent to remove code).
- **Impact:** Every run re-reports the same findings. Users cannot indicate "I know about this, I'll fix it in sprint 3." No human-in-the-loop architecture governance.

### G-CRIT-06: WLS Decay Regression with Confidence Intervals
- **What's missing:** Genesis has basic trend detection (arrow up/down) but no statistical forecasting. No weighted least-squares regression, no R² goodness-of-fit, no 95% confidence intervals, no t-statistic significance test.
- **Architect's approach:** Exponential recency weights (half-life: 8 weeks); WLS formula; R², slopeStdError, t-statistic; trajectory per week; threshold-crossing prediction; human-readable summary.
- **Impact:** "Your score will be 42 in 8 weeks" is only meaningful with a confidence interval. Without it, all forecasts are marketing, not engineering.

### G-CRIT-07: Partial Re-analysis Scoping (AffectedScope)
- **What's missing:** After applying a refactoring step, Genesis re-runs the full analysis. For large repos this is expensive and slow.
- **Architect's approach:** `computeAffectedScope()` returns `changedFiles + consumerFiles` using a pre-built `DependencyIndex`. Re-analysis scoped to only that set.
- **Impact:** Refactoring feedback loop is slow. Interactive refactoring is impractical on repos with >500 files.

---

## High-Value Gaps (missing, high Pro differentiation)

### G-HIGH-01: Architecture Regression Test DSL
- **What's missing:** No way to write architecture assertions that fail CI. Rules engine validates scores and anti-pattern counts but has no temporal assertions.
- **Neither repo has this fully.** Architect has `.architect.rules.yml` quality gates; Scryer has modeling rule validation. Neither supports `score_not_declining_over: 4_weeks` or `bus_factor_min: 2_per_module`.
- **Genesis opportunity:** Own this space. `.genesis.rules.yml` with full assertion DSL.

### G-HIGH-02: Active Hotspot Warnings with Prescriptive Actions
- **What's missing:** Genesis detects hotspots (high churn + high coupling) but does not prescribe a specific refactoring action with estimated score delta.
- **What's needed:** "This file changed 47 times in 8 weeks, has 3 authors, and a fan-in of 12. Extract `PaymentService` into its own module. Estimated score delta: +8 pts."

### G-HIGH-03: Confidence Annotations on Every Output
- **What's missing:** No output carries a `confidence` field. Anti-patterns are reported as facts, not estimates.
- **What's needed:** Every detection, score, forecast, and recommendation annotated with `confidence: float` and `basis: str`. Users need to know how much to trust each finding.

### G-HIGH-04: Weekly Commit Timeline
- **What's missing:** git_analyzer.py produces per-file stats but no week-by-week project-level timeline.
- **Architect's approach:** `WeeklySnapshot` with commits, churn, activeFiles per week; fills all weeks in the window (no gaps).

### G-HIGH-05: Bus Factor Per File
- **What's missing:** git_analyzer.py does not track distinct authors per file. Single-author files are knowledge concentration risk.
- **Architect's approach:** `authors: Set[str]` per file; `busFactor = len(authors)`.

### G-HIGH-06: Change Coupling Detection
- **What's missing:** Genesis detects individual file hotspots but not file pairs that always change together.
- **Architect's approach:** Co-change map with `confidence = cochangeCount / maxCommits`; top 50 pairs reported.

### G-HIGH-07: HTML Self-Contained Reporter
- **What's missing:** Genesis produces CLI output and JSON. No browser-viewable report.
- **Architect's approach:** Modular section system (header, overview, score, anti-patterns, layers, agents, refactoring-plan, suggestions); self-contained single HTML file with inline CSS/JS.

### G-HIGH-08: GitHub Actions Adapter
- **What's missing:** Genesis cannot run in CI as an automated governance gate.
- **Architect's approach:** `github-action.ts` reads `GITHUB_EVENT_PATH`; fails PR if rules violated; posts report as PR comment.

### G-HIGH-09: Pre-commit Boundary Enforcement Hook
- **What's missing:** No mechanism to enforce architecture rules at commit time.
- **What's needed:** Project-specific pre-commit hook that runs the rules engine on staged files only, fails commit on boundary violations, reports exactly which rule and file.

### G-HIGH-10: Benchmark Suite Against Real Projects
- **What's missing:** No objective quality measurement. Cannot claim "Genesis scores projects correctly" without baselines.
- **Architect's approach:** Benchmark reports for axios, express, nest, vite. Known scores against known codebases.

### G-HIGH-11: Cycle Breaking with Interface Extraction Suggestions
- **What's missing:** Genesis detects circular dependencies and suggests "break the cycle." It does not propose the minimal interface extraction that actually breaks it.
- **What's needed:** Analyze cycle members; identify the lowest-dependency node; suggest "Introduce `IAuthService` in a shared module; AuthModule depends on the interface."

---

## Medium Gaps (Free tier improvements)

### G-MED-01: Annotated Project Structure Scanner
- Genesis scans files for analysis but does not produce a human-readable annotated tree.
- Scryer's approach: `TreeNode` with annotation propagation; collapses noise; shows only manifest/infrastructure/environment files with labels.

### G-MED-02: Python Stdlib Filter (complete)
- Genesis has partial stdlib filtering but no comprehensive set (100+ stdlib names with top-level extraction).

### G-MED-03: Score Timeline Visualization
- Score history is stored in `.genesis/score_history.jsonl` but there is no timeline chart or ASCII sparkline output.

### G-MED-04: Offline Prompt Generator
- Cannot generate refactoring prompts for export/offline use without LLM execution.

### G-MED-05: Human Gate for Interactive Refactoring
- No interactive approval mechanism. Users cannot review each step before applying. Currently all-or-nothing.

### G-MED-06: Git Cache Layer
- git_analyzer.py re-runs `git log` on every invocation. No persistent cache keyed by project + date range.

### G-MED-07: Dependency Index (O(1) lookups)
- import_graph.py builds the graph but does not pre-compute `incomingByFile` / `outgoingByFile` maps. Rules must re-scan all edges O(E) per rule.

---

## Capabilities Where Genesis Already Exceeds Both

| Area | Genesis Advantage |
|------|-----------------|
| Python-first ecosystem | Best-in-class Python import parsing, stdlib filtering, AST analysis |
| Adaptive scoring profiles | 6 profiles (same as Architect) plus auto-detection from evidence.json |
| Anti-pattern coverage | 7 detectors, all deterministic, no LLM required |
| Fragility classification | Unique 3-tier STABLE/FRAGILE/VOLATILE combining multiple signals |
| Research-first workflow | 8-phase workflow with GitHub issue mining (no equivalent in either repo) |
| License gate | Ed25519 Pro license gating (neither repo has monetization) |
| Security templates | STRIDE/OWASP built-in (neither repo has this) |
| Cross-session memory | Persistent context across sessions (neither repo has this) |
| Zero external dependencies | stdlib-only Python enforcement (both competitors require npm/Cargo ecosystems) |
