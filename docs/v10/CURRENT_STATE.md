# Genesis Architect — Canonical Current-State Document (v10 reconciliation)

Reconciles `gap_TEMP.md`, `split_TEMP.md`, `v8v9_audit_TEMP.md` against the live
repository on branch `pro-v3-analysis`. Every row below is (verified) against
source, tests, or a live command — not copied from the TEMP docs. Classification
scheme: **VERIFIED BUILT / PARTIAL / PLANNED / OBSOLETE-SUPERSEDED / UNKNOWN**.

Baseline facts:
- Package: `genesis-architect-pro`, version `8.0.0` (verified: `pyproject.toml`) — unchanged despite extensive work the TEMP docs label "v9"/"v10". No CHANGELOG.md exists (verified: root listing).
- Test suite (verified: live `pytest tests/ -q` run this session): **2322 passed, 1 skipped, 7 warnings, exit 0, 133.12s**. This supersedes v8v9_audit_TEMP.md's recorded 2202-passed baseline from 2026-08-22 — work has continued since without regressions.
- Module count: 66 `.py` files under `src/genesis_architect_pro/` (verified: Glob). `capability_map.py` is itself the drift guard: `unmapped_modules()` / `stale_entries()` are asserted empty by a test, so the CAPABILITIES table below is self-consistent with the package by construction, not by manual audit.

---

## 1. The flagged contradiction — RESOLVED

**gap_TEMP.md** claims an Ed25519 Pro `license.py` license gate as a current differentiator.
**split_TEMP.md** states `license.py` was deleted and there is no license gate.

**Verdict: split_TEMP.md is correct, gap_TEMP.md is stale.** `license.py` does not exist anywhere in `src/genesis_architect_pro/` (verified: file listing + grep, zero matches). Every Pro feature runs unconditionally. The Free/Pro split now describes packaging only, not an access boundary.

## 2. Unflagged contradiction found during reconciliation

**split_TEMP.md**'s "Free CLI" table (`genesis score/analyze/refactor/git/c4/structure`) describes a CLI shape that **no longer exists**.

**Classification: OBSOLETE-SUPERSEDED.** The actual CLI surface (verified: `cli/parser.py`, `cli/analysis_cmds.py`, `cli/project_cmds.py`, `cli/session_cmds.py`) is unified under `genesis decide "<instruction>"`, GDE-routed through `GDEMode {RECOVERY, RESEARCH, REFACTOR, GATE, BUILD, DOCUMENT, COMMITTEE}` (verified: `gde_types.py`), plus supporting subcommands: `explain, memory, engines, deps, ui, companion, sync, doctor, recover, harden, advise, fetch, ingest, purge, organize, gate, telemetry [+sub-subcommands], mcp [serve/list/call]`. There is no standalone `score`/`analyze`/`refactor`/`git`/`c4`/`structure` subcommand — this is an architectural supersession, not an unbuilt gap.

---

## 3. Capability ledger

### VERIFIED BUILT

| Capability | Evidence |
|---|---|
| Import graph + cycle detection (multi-language) | `capability_map.py` → `import_graph`; reached via `genesis recover` |
| Import audit (broken imports) | `import_audit.py`; `genesis recover` |
| Architecture Scorer, 4 dimensions, 6 adaptive profiles | `architecture_scorer.py` lines 8, 34 — profiles comment block confirms `frontend-spa, backend-monolith, microservices, data-pipeline` + default/library |
| Anti-Pattern Detector, all 7 types | `antipattern_detector.py` — confirmed by name: `god-class` (L51), `hub-file` (L59), `circular-dep` (L66), `dead-code` (L72), `feature-envy` (L81, `_detect_feature_envy` L112), `leaky-abstraction` (L87, `_detect_leaky_abstractions` L155), `shotgun-surgery` (L93, `_detect_shotgun_surgery` L198) |
| Fragility Classifier (STABLE/FRAGILE/VOLATILE) | `capability_map.py` → `fragility_classifier`; `genesis recover` |
| Confidence annotations on scores/anti-patterns | `architecture_scorer.py:81-133` (`_score_confidence`, `result["confidence"]`, `result["confidence_basis"]`); `antipattern_detector.py:41` ("PRO: confidence annotation"); test: `test_step2_confidence_annotations.py` (29+9 cases, passing) |
| WLS Decay Regressor — weighted regression, R², t-stat, 95% CI, half-life (G-CRIT-06) | `decay_regressor.py`: `fit_weighted_regression` (L256), `r_squared` (L315), `t_stat`/`is_significant` (L329-330), `_t_critical` (L197), `apply_weights` w/ exponential half-life decay (L228-245); test: `test_step4_decay_regressor.py` (39+ cases) |
| Score trajectory / threshold-crossing forecast | `decay_regressor.py`: `generate_trajectory` (L345), `_compute_weeks_to_threshold` (L399), `_compute_overall_confidence` (L430), `forecast` (L457) |
| Dual-layer architecture model (planned vs. committed) (G-CRIT-01) + Model diff engine (G-CRIT-02) | `model_store.py`: `ArchModel`, `ModelNode`, `ModelLink`, `ModelGroup`, `ModelResponsibility` (L73-121), `ModelDiff`, `NodeChange`, `ResponsibilityChange`, `LinkChange` (L143-170), `_compute_diff` (L237), `ModelStore` (L355); tests: `test_step5_model_store.py`, `test_step6_model_diff.py` (65+ cases combined) |
| Drift flags (vagrant / stale) + reconcile (G-CRIT-05) | `drift_detector.py` L11,17,29,38,89-115 (`vagrant_candidates`, `stale_candidates`, `VagrantCandidate`, `StaleCandidate`); tests: `test_step7_drift_detector.py`, `test_step9_persist_anchors.py` |
| Source Anchor (claim → file:line) (G-CRIT-03) | `source_anchor.py`; test: `test_step8_source_anchor.py` (38+ cases) |
| Bus factor per file (G-HIGH-05) | `git_analyzer.py` — `WeeklySnapshot`, author-count computation |
| Weekly commit timeline (G-HIGH-04) | `git_analyzer.py`: `build_timeline(commits, period_weeks=12)` |
| Score sparkline (ASCII) — resolves gap_TEMP.md's G-MED-03 ("no timeline chart or sparkline"), which is now stale | `git_analyzer.py`: `render_sparkline(snapshots, metric="commits")`, CLI `--timeline` flag |
| HTML self-contained reporter (recovery report only — see PARTIAL below) | `recovery_report.py`: `to_html()` (L224) → `_render_html()` (L1068), `<html lang="en">` literal (L1244); test: `test_step12_html_report.py` (20-point docstring: XSS escaping, section completeness, determinism, embedded JSON) |
| Cycle-breaking interface-extraction suggestions | `refactoring_planner.py`: `_suggest_split_path(p.file, "interface")` (L136), "Extract stable public interface" (L137), "Suggest where to put shared types extracted to break a cycle" (L327) |
| Supply-chain CI audit (unpinned GitHub Actions) | `supply_chain_audit.py`: `scan_workflows()`; feeds `rules_engine.gather_facts()`; test: `test_supply_chain_audit.py` |
| Rules Engine / `genesis gate` — static architecture regression gate | `rules_engine.py` (413 lines, read in full): `DEFAULT_RULES`, `SHADOW_BY_DEFAULT=True`, `policy_mode()`, `load_rules()` (`.genesis/rules.json` preferred, `.genesis/rules.yml` optional via PyYAML — confirmed L10-11, L126-148), `gather_facts()`, `evaluate()` (11 static rule keys), `RuleResult`/`CheckReport`, `main()` CLI entry |
| Capability map + drift guard | `capability_map.py` (326 lines, read in full) — 50 engines mapped across diagnosis/research/security/planning/memory/workspace groups; `unmapped_modules()`/`stale_entries()` self-check |
| MCP tool exposure for core engines | `mcp__genesis__genesis_gate`, `genesis_architecture_score`, `genesis_anti_patterns`, `genesis_recovery_report` registered and reachable as MCP tools (verified live in this session's tool list) — `mcp_tools.py` implements them under different internal names than the MCP-exposed ones, which is fine; the capability is reachable |
| Dependency scanning + CVE lookup, package registry validation | `dependency_scanner.py`, `package_registry.py`; `genesis deps` |
| Prescriptive refactoring with estimated score delta (G-HIGH-02) | `refactoring_planner.py:56` — `RefactorStep.score_impact: int` ("estimated score points gained"), populated per generated step alongside `complexity` and `confidence` |
| Security pattern templates, STRIDE + OWASP (G-CRIT differentiator claim) | `security_templates.py`: `generate_security_docs()` (L544), `_generate_stride_doc()` (L175), `_generate_owasp_doc()` (L471), stack/framework auto-detection (`_detect_stack` L39, `_detect_framework` L61) |
| Cross-session persistent memory | `cross_session_memory.py`: `SessionContext` (L31), `restore_session()` (L105), phase checkpoints `save_phase2/4/6()` (L157-187), `list_analyzed_videos()` (L202) |
| C4 Mermaid diagram generation (L1-L3) | `c4_generator.py`: `generate_c4_doc()` (L77), `_generate_component_diagram()` (L31) |
| Research orchestration — coverage scoring, domain classification, evidence floor check | `research_orchestrator.py`: `ResearchSummary`/`RepoResult` (L38-47), `compute_coverage()` (L190) — this is the producer of the `coverage` value `gde_gate_engine.py`'s `RESEARCH_COVERAGE_LOW` gate consumes — `check_floor()` (L317), `classify_domain()` (L273) |

### PARTIAL

| Capability | What's built | What's missing |
|---|---|---|
| **HTML reporter** (G-HIGH-07) | Full single-file HTML renderer exists, with XSS-safe escaping and embedded JSON, for `RecoveryReport` specifically (`recovery_report.py`) | No architecture-score/anti-pattern/forecast *dashboard* HTML (the "architecture velocity dashboard" split_TEMP.md describes — per-week-per-module score/churn/bus-factor with confidence bands) — that is a separate, larger rendering surface not found anywhere |
| **Partial Re-analysis Scoping** (G-CRIT-07 / user's deferred item 3 — also resolves G-MED-07's "O(1) incoming/outgoing lookup" ask, same module) | Core data structures exist and are unit-tested: `dependency_index.py` → `DependencyIndex` (`importers_of()`, `imports_of()`, `__len__()`), `AffectedScope` (`total()`, `all_files()`), `build_dependency_index()`, `compute_affected_scope()`; test: `test_step3_dependency_index.py` | Referenced nowhere outside itself and `__init__.py`'s re-export (verified: cross-codebase grep, zero other call sites). Not wired into any actual refactor/re-analysis pipeline — the machinery exists, the integration doesn't. This is integration work on an existing foundation, not greenfield |
| **Architecture Regression Test DSL** (G-HIGH-01 — Stage 2's target) | A full single-snapshot policy gate exists and is production-wired: rule-file loading (JSON/YAML), fact-gathering from 4 engines, structured pass/fail reporting, shadow/enforcing modes, CLI entry (`genesis gate`) | Zero temporal/regression keywords anywhere in the codebase (verified: grep for `score_not_declining|bus_factor_min|banned_imports|coupling_below|churn_below_over`, zero matches outside TEMP docs' own illustrative YAML). `rules_engine.py`'s 11 rule keys are all point-in-time, not trend-based. This is the precise, correctly-scoped gap Stage 2 should fill by **extending** `rules_engine.py`'s rule vocabulary and `gather_facts()`, not building a parallel DSL/parser |
| **Stdlib filter** | Exists, 86 lines, functional (`stdlib_filter.py`) | split_TEMP.md's "complete, 100+ names" claim is unverified at face value — file is short enough (86 lines, ~38 string literals by rough count) that "100+ stdlib names" is plausible only if it delegates to `sys.stdlib_module_names` rather than hardcoding a list; worth a closer read before repeating that exact claim verbatim, but functionally the capability (separating stdlib from third-party imports) is built and reachable via `genesis deps` |

### PLANNED (confirmed absent — zero matches anywhere in `src/`)

| Capability | Gap ID | Evidence of absence |
|---|---|---|
| Prompt Budget Manager | G-CRIT-04 | grep `prompt_budget\|token_budget\|PromptBudget` → zero matches |
| Change Coupling Detection (file co-change analysis) | G-HIGH-06 | grep `co.?change\|change_coupling\|coupling_matrix` → zero matches |
| Annotated Project Structure Scanner | G-MED-01 | grep `def.*structure\|TreeNode\|annotated.*tree\|structure_scan` → zero matches |
| GitHub Actions CI Adapter (runs Genesis in CI, posts PR comments) | G-HIGH-08 | No `genesis-check.yml`-style template, no PR-comment logic found. Distinct from `supply_chain_audit.py`, which only *audits* existing CI files, doesn't *run inside* CI |
| Pre-commit boundary enforcement hook | G-HIGH-09 | grep `pre-commit\|pre_commit` across `src/*.py` → zero matches |
| Human gate / interactive per-step refactor approval | G-MED-05 | grep `human_gate\|interactive.*approv\|approve.*step` → zero matches |
| Offline prompt generator (export refactor prompts) | G-MED-04 | grep `offline.*prompt\|prompt_generator` → zero matches |
| Git cache layer (persistent, keyed by projectPath/dateRange/fileHash) | G-MED-06 | grep `cache` in `git_analyzer.py` → zero matches |
| Benchmark suite (run against known OSS projects, score calibration) | G-HIGH-10 | grep `benchmark` across `src/*.py` → only match is unrelated (`intent_classifier.py`, incidental word use, not a benchmark suite) |
| Agent Generation (`.agent/` directory, role-specific markdown agents) | — | grep `\.agent["'/]\|agent_generator\|generate_agents` → zero matches |
| Docker image `genesis-pro:latest` for hermetic CI | — | not found; out of scope for this grep pass but no evidence surfaced anywhere in this session's searches |
| Violation persistence / self-improving suggestions / cross-project benchmarking | — | not found in any engine file; these read as aspirational Pro differentiators in split_TEMP.md with no corresponding code |

### OBSOLETE-SUPERSEDED

| Item | Why |
|---|---|
| split_TEMP.md's Free CLI table (`genesis score/analyze/refactor/git/c4/structure`) | Replaced by unified `genesis decide` GDE routing (see §2) |
| gap_TEMP.md's 13-module "Current Genesis PRO Inventory" | Actual module count is 66; the table predates most of the current engine set and is unreliable as an inventory |
| gap_TEMP.md's `license.py` / Ed25519 license-gate claim | File deleted; see §1 |

### UNKNOWN (not verified this session — would need a further read, not safe to classify either way)

- Whether `stdlib_filter.py`'s list is genuinely ≥100 names or a shorter curated set (file is short; needs a direct read of its contents, not just a grep, to settle the exact claim).
- The literal content of the Hebrew `Genesis_Architect_v10_Full_Improvement_Report_HE.md` vision report — only a thematic summary survived prior context compaction; if that document makes specific claims not covered by gap/split/v8v9 TEMP docs, they are not reconciled here.
- Whether `mcp_tools.py`'s internal function names map 1:1 to the four MCP-exposed tool names, or whether there's a thin adapter layer in between (grep for `def genesis_gate` etc. inside `mcp_tools.py` returned no direct match, yet the tools are live and reachable — functionally confirmed working, implementation detail unconfirmed).

---

## 3b. GDE gate count — RESOLVED (direct read, this session)

**Live count: 15 named approval gates** (verified: `gde_gate_engine.py`, direct read lines 1-80 this session). The module docstring (line 3) says "Evaluates the 15 named approval gates" and enumerates all 15 by name in its trigger-condition table (lines 10-27); `_GATE_POLICY` (lines 61-80) contains exactly 15 tuples. **Docstring and policy table agree — there is no documentation-drift bug in this file as of this session's read.**

The 15 gates: `PLAN_WRITE`, `RULES_FAIL` (hard blocks) · `CONFIDENCE_LOW`, `DRIFT_CRITICAL`, `SECURITY_RISK`, `POLICY_VIOLATION`, `COMMIT_CONFLICT`, `RED_TEAM_CRITICAL`, `RESEARCH_COVERAGE_LOW` (soft blocks) · `WRITE_SCOPE`, `REQUIRED_FAILED`, `DEGRADED_MODE`, `NO_ENGINES`, `RESEARCH_STALE`, `RESEARCH_EVIDENCE_UNKNOWN` (warnings).

**Note on provenance, since this supersedes two prior figures in play:**
- `v8v9_audit_TEMP.md`'s 2026-08-17 snapshot recorded "total gates in policy table: 13" (verified: that document, line 133) — this is where the "13" figure originates; it was accurate at that date, before `RESEARCH_COVERAGE_LOW` and `RESEARCH_EVIDENCE_UNKNOWN` were added.
- This session's correction instruction stated the count as **14**, with the docstring allegedly stale at "13". Direct read contradicts both parts of that: the live count is **15**, not 14, and the docstring already says 15 — it is not stale. Flagging this per the verify-before-recording standard applied throughout Stage 1, rather than writing an unverified "14" into the canonical record.
- `RESEARCH_COVERAGE_LOW`'s existence is independently corroborated by `research_orchestrator.py`'s `compute_coverage()` (see §3 VERIFIED BUILT) feeding exactly the `coverage` field `gde_gate_engine.py`'s `_check_research_coverage_low` reads — the gate is wired, not just declared.

---

## 3c. Carried-forward findings from `v8v9_audit_TEMP.md` outside the architecture-engine scope

The capability ledger in §3 is scoped to architecture-analysis engines (matching `gap_TEMP.md`/`split_TEMP.md`'s framing). `v8v9_audit_TEMP.md` additionally audited GDE core routing, the adversarial red-team gate, auto-purge/ephemeral hygiene, the two-tier MCP advisor, and the dynamic skill fetcher — subsystems outside that scope. Its own 2026-08-22 status update is the freshest self-contained snapshot of those; the items below are **carried forward from that update, not re-verified live this session** (tagged accordingly, since re-auditing session/orchestration infrastructure was outside this session's grep/read sweep):

| Item | Status as of 2026-08-22 (carried, not re-verified) |
|---|---|
| D-1 No commit pinning in skill fetcher | CLOSED (`605688a`) |
| D-2 Symlink containment unverified on Windows | CLOSED (Linux clean-room container harness, `tests/e2e/docker/`) |
| D-3 `hygiene_notice()` walks whole tree unbounded | CLOSED (`605688a`, now reads `.claudeignore`) |
| D-4 `knowledge_graph` handoff coupling is convention, not enforced | OPEN, low severity, unchanged |
| D-5 MCP Advisor LOCAL tier is manifest-based, not AST-based (wording overstates it) | OPEN, low severity, unchanged |
| D-6 `_pid_alive` fails safe on undeterminable PID | Accepted tradeoff, not a bug |
| D-7 Red-team LLM path tested only via injected fakes | Accepted as-is, low severity |
| A4 evidence/inference split, A5 `failure_modes` field | BUILT (`ada45f4`) |
| R1–R6 research protocol (outline, coverage, uncertainty, floor check) | BUILT (6 of 6) — **independently corroborated this session**: `research_orchestrator.py`'s `compute_coverage()`/`check_floor()`/`is_uncertain()` (§3 VERIFIED BUILT) are exactly the R1/R3/R4 machinery this blueprint item describes, and `RESEARCH_COVERAGE_LOW` is live in `gde_gate_engine.py`'s policy table (§3b) |

Test-count lineage for context: 2029 passed (2026-08-17) → 2202 passed (2026-08-22) → 2322 passed (Stage 1 reconciliation session) → **2881 passed, 2 skipped** (2026-10-02, verified on a clean detached worktree at `4ed23cd`, after Stage 2's temporal-rules work landed — see §4 item 1) — monotonic growth, no regressions reported at any checkpoint.

---

## 4. Dependency ordering on remaining gaps

1. **Architecture Regression Test DSL — DONE (2026-10-02)**: shipped as two bounded v1 temporal rules, `max_score_decline` and `max_cycle_count_increase`, per `ARCHITECTURE_REGRESSION_TEMPORAL_DESIGN.md` (verified: commits `764d730`, `4ed23cd`; 30 new tests, 62/62 in `test_rules_engine.py`, full suite 2881 passed on a clean worktree). Critical-anti-pattern-count and bus-factor temporal rules remain explicitly deferred (design doc §10, ledger row A3) — not dropped, just not in v1.
2. **Partial Re-analysis Scoping** (PARTIAL → wire `dependency_index.py` into a real pipeline) — benefits from having the DSL in place first only loosely; really just needs a caller. Could proceed independently of (1).
3. **Prompt Budget Manager** (PLANNED, greenfield) — no dependency on (1) or (2); purely about file abbreviation and token estimation for LLM-prompt construction during refactor-plan generation.
4. **Capability Manager / larger v10 work** — depends on whichever of the above land, since it's the broader orchestration layer.

This ordering matches the user's own stated recommended order exactly — the evidence gathered this session doesn't surface any reason to resequence it.

## 5. Claims stronger than the implementation (call these out explicitly)

- **Version number**: `pyproject.toml` still says `8.0.0` despite work the TEMP docs and recent commits label v9/v10. Either the version should be bumped to reflect actual capability growth, or the "v9"/"v10" labels in docs should be understood as informal milestone names, not semver claims. Worth a decision, not a blocker.
- **HTML reporter**: split_TEMP.md describes a full "architecture velocity dashboard." What exists is a single-report HTML renderer (`recovery_report.py`), which is real and well-tested, but narrower than the dashboard description.
- **Partial Re-analysis Scoping**: described in split_TEMP.md as if it's an active re-analysis optimization. In reality the scoping math exists and is tested in isolation but produces no effect on any running workflow today.
- **Stdlib filter "100+ names"**: plausible but unverified at the literal-count level.
- **Free CLI table**: entirely describes a CLI that was replaced; anyone reading split_TEMP.md today would try commands that don't exist.

## 6. Recommended next milestone

~~**Architecture Regression Test DSL**~~ — **done, see §4 item 1.** With that gap closed, the two remaining items from §4 are, in order:
1. **Partial Re-analysis Scoping** (PARTIAL → wire `dependency_index.py` into a real pipeline) — the scoping math already exists and is tested in isolation (§5) but has no effect on any running workflow; the remaining work is purely wiring a caller.
2. **Prompt Budget Manager** (PLANNED, greenfield) — file abbreviation and token estimation for LLM-prompt construction during refactor-plan generation. No dependency on (1).

Both are independent of each other and can proceed in isolation — this is unchanged from §4's original ordering, just renumbered now that the DSL item is closed.

---

## 7. Disposition of the three TEMP files

All three were read in full twice — once for the initial reconciliation, once more for a dedicated completeness re-check — and cross-checked against live source, tests, and grep evidence this session. Specifically:
- `gap_TEMP.md` — module inventory and license-gate claim are stale; several "gap" items (bus factor, weekly timeline, sparkline, HTML reporter) are actually built. The completeness re-check additionally surfaced and verified five previously-missed built capabilities (G-HIGH-02 prescriptive refactoring with score delta, STRIDE/OWASP security templates, cross-session memory, C4 diagram generation, research orchestration/coverage scoring — all now in §3 VERIFIED BUILT) and two further gap-resolution cross-references (G-MED-03 sparkline, G-MED-07 dependency-index lookups — both now annotated in their resolving rows). The Architecture Regression DSL gap claim is correct and is now Stage 2's target.
- `split_TEMP.md` — license-gate-removed statement is accurate and is the one piece of ground truth from these three docs that's fully current; its Free CLI table is obsolete; its Pro-feature list is a useful target inventory but several items are aspirational (not built).
- `v8v9_audit_TEMP.md` — accurate as of 2026-08-22 but superseded by this session's live 2322-passed test run. Its gate-count snapshot ("13 at audit time") is superseded by this session's direct read of `gde_gate_engine.py`: live count is 15, with docstring and policy table in agreement — see §3b, which also documents the discrepancy against the user's stated interim correction of 14. Its GDE/orchestration-infrastructure findings (D-1 through D-7, blueprint items A4/A5/R1-R6), which sit outside §3's architecture-engine scope, are now carried forward in §3c, with R4/`RESEARCH_COVERAGE_LOW` independently corroborated live rather than merely carried over.

**Recommendation: safe to remove.** Every claim worth keeping from all three has been carried into this canonical file with fresher evidence (re-confirmed by a second completeness pass, not just the initial reconciliation), and every claim that was wrong — including the user's own interim gate-count correction — has been corrected here rather than silently dropped or silently accepted. No deletion has been performed — awaiting your explicit approval per Stage 1's instructions.
