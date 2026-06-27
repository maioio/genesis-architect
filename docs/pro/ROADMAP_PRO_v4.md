# Genesis PRO — Implementation Roadmap v4
<!-- Post-audit roadmap. Based on deep reverse engineering of architect + scryer. -->
<!-- Date: 2026-06-27 | Status: PLANNING — no code written yet -->

## Priority Framework

Each item is classified by:
- **Tier:** 1 = Critical (blocks Pro launch), 2 = High-value Pro differentiator, 3 = Free core improvement, 4 = Pro intelligence layer, 5 = UI/Reporting, 6 = CI/Infra/Validation
- **Effort:** S = hours, M = 1-2 days, L = 3-5 days, XL = 1+ week
- **Dependency:** what must be done first

---

## Track 1 — Critical Must-Have Capabilities (blocks Pro launch)

These are required before Genesis PRO can be sold or used in production teams.

### 1.1 Prompt Budget Manager
**Tier:** 1 | **Effort:** M | **Dep:** None

Prevents silent LLM context overflow on large codebases. Currently the single largest production failure mode.

New module: `src/genesis_architect_pro/prompt_budget.py`

Capabilities:
- `OperationClass` enum: `CORE_TARGET`, `IMPORTANT_CONTEXT`, `CONSUMER_REF`
- `estimate_tokens(content: str) -> int` — 1 token per 4 chars
- `abbreviate_file(content: str) -> str` — first 20 lines + exported symbols + last 5 lines
- `build_prompt(steps, model: str) -> str` — fills to model's budget, abbreviates overflow
- Model-specific budgets: `{"claude": 60000, "gpt-4": 30000, "gemini": 40000, "default": 8000}`
- Directive appended to every prompt requiring separate code blocks per file

Tests required:
- `test_estimate_tokens_character_ratio`
- `test_abbreviate_preserves_exports`
- `test_build_prompt_respects_budget_limit`
- `test_core_target_always_included`
- `test_consumer_ref_gets_abbreviated`

### 1.2 Confidence Annotations on Every Output
**Tier:** 1 | **Effort:** M | **Dep:** None

Every finding, score, and recommendation must carry `confidence` and `basis`. Without this, Genesis is not credible as a governance tool.

Changes:
- Add `confidence: float` and `basis: str` to `AntiPattern` dataclass
- Add `confidence: float` and `data_points: int` to score result dict
- Add `confidence: float` and `basis: str` to `RefactoringStep`
- `_compute_detection_confidence(metrics: dict) -> float` — scales with evidence strength
- Basis strings: `"based on N commits over D days"`, `"R²=0.87 on 12 data points"`, etc.

Tests required:
- `test_antipattern_has_confidence_field`
- `test_score_result_has_confidence`
- `test_confidence_scales_with_evidence`
- `test_low_data_produces_low_confidence`

### 1.3 Partial Re-analysis Scoping (DependencyIndex + AffectedScope)
**Tier:** 1 | **Effort:** M | **Dep:** None (improves import_graph.py)

Pre-compute O(1) lookup maps; compute affected scope after a refactor step.

Changes to `import_graph.py`:
- Add `build_dependency_index(modules: dict) -> DependencyIndex` — builds `incoming_by_file` and `outgoing_by_file` dicts in one O(E) pass
- `DependencyIndex` dataclass: `incoming: dict[str, set[str]]`, `outgoing: dict[str, set[str]]`

New `compute_affected_scope(step: RefactoringStep, index: DependencyIndex) -> AffectedScope`:
- `AffectedScope` dataclass: `changed_files: list[str]`, `consumer_files: list[str]`
- Changed files = all paths in step operations
- Consumer files = all files importing any changed file (one level deep from index)

Changes to `refactoring_planner.py`:
- Pre-build DependencyIndex before running rules
- Pass index to each rule (replaces O(E) scans per rule)

Tests required:
- `test_dependency_index_builds_correctly`
- `test_incoming_by_file_accurate`
- `test_affected_scope_includes_consumers`
- `test_affected_scope_excludes_unrelated`
- `test_refactor_rules_use_index`

### 1.4 WLS Decay Regressor with Confidence Intervals
**Tier:** 1 | **Effort:** L | **Dep:** score history (already exists)

Replaces the current "trend arrow" with statistically rigorous forecasting.

New module: `src/genesis_architect_pro/decay_regressor.py`

Capabilities:
- `ScoreDataPoint` dataclass: `week_offset: int`, `score: float`, `weight: float | None`
- `RegressionResult` dataclass: `slope`, `intercept`, `r_squared`, `data_points`, `slope_std_error`, `is_significant`
- `ScorePrediction` dataclass: `week_offset`, `predicted_score`, `lower_bound`, `upper_bound`, `confidence`
- `DecayForecast` dataclass: full forecast with trajectory, threshold prediction, summary
- `DecayRegressor` class:
  - `apply_weights(data) -> list[ScoreDataPoint]` — exponential recency (half-life: 8 weeks)
  - `fit_weighted_regression(data) -> RegressionResult` — WLS formula, R², t-statistic
  - `generate_trajectory(regression, start, end) -> list[ScorePrediction]` — confidence decays with distance
  - `forecast(data) -> DecayForecast | None` — full pipeline, returns None if < 3 data points
- Load from `.genesis/score_history.jsonl` → convert to `ScoreDataPoint` list

Tests required:
- `test_apply_weights_recency_order`
- `test_fit_regression_known_linear_data`
- `test_r_squared_perfect_fit`
- `test_t_statistic_significance`
- `test_confidence_intervals_widen_with_distance`
- `test_threshold_crossing_negative_slope`
- `test_threshold_crossing_stable_returns_infinity`
- `test_forecast_returns_none_insufficient_data`
- `test_forecast_summary_human_readable`

### 1.5 Dual-Layer Model (planned vs. committed)
**Tier:** 1 | **Effort:** L | **Dep:** None

The architectural foundation for design-first workflows.

New module: `src/genesis_architect_pro/model_store.py`

Capabilities:
- `ArchElement` base dataclass: `id: str`, `label: str`
- `ModelNode` dataclass: `id`, `kind`, `name`, `parent_id`, `technology`, `description`, `responsibilities`
- `ModelResponsibility` dataclass: `id`, `statement`, `vagrant: bool`, `stale: bool`
- `ArchModel` dataclass: `nodes`, `links`, `groups`, `source_map`
- `ModelStore` class:
  - `genesis_dir` → `.genesis/`
  - `committed_path` → `.genesis/model.json`
  - `planned_path` → `.genesis/planned.json`
  - `load_committed() -> ArchModel`
  - `load_planned() -> ArchModel`
  - `save_committed(model: ArchModel) -> None`
  - `save_planned(model: ArchModel) -> None`
  - `mark_implemented(node_ids: list[str]) -> None` — folds planned nodes into committed
  - `is_planned_diverged() -> bool` — True when planned differs from committed

Tests required:
- `test_committed_and_planned_are_independent`
- `test_mark_implemented_folds_node`
- `test_planned_diverged_true_when_different`
- `test_planned_diverged_false_when_same`
- `test_save_and_load_roundtrip`
- `test_genesis_dir_created_if_missing`

---

## Track 2 — High-Value Pro Differentiators

### 2.1 Model Diff Engine
**Tier:** 2 | **Effort:** M | **Dep:** 1.5 (ModelStore)

Git-status-style diff between any two model states.

New module: `src/genesis_architect_pro/model_diff.py`

Capabilities:
- `ElementKind` enum: `NODE`, `LINK`, `RESPONSIBILITY`, `PROPERTY`, `GROUP`
- `Change` union: `Added`, `Deleted`, `Moved(from_owner, to_owner)`, `Reworded(field, from_val, to_val)`, `MembersChanged(added, removed)`
- `ElementChange` dataclass: `kind`, `id`, `owner_id`, `label`, `changes: list[Change]`
- `ModelDiff` dataclass: `changes: list[ElementChange]`, `is_empty: bool`
- `diff(from_model: ArchModel, to_model: ArchModel) -> ModelDiff`
  - Stable ID tracking: reparent → Moved, relabel → Reworded
  - Covers: nodes, links, responsibilities, groups
- CLI: `genesis diff [path]` — shows planned vs. committed in git-status style

Tests required:
- `test_identical_models_empty_diff`
- `test_node_added`
- `test_node_deleted`
- `test_node_reparented_is_moved`
- `test_node_renamed_is_reworded`
- `test_responsibility_moved_between_nodes`
- `test_responsibility_moved_and_reworded_stacks`
- `test_diff_is_empty_property`

### 2.2 Source-Level Responsibility Anchoring
**Tier:** 2 | **Effort:** L | **Dep:** 1.5 (ModelStore)

Maps responsibilities to specific file + line ranges. Makes architecture claims verifiable.

New module: `src/genesis_architect_pro/source_anchor.py`

Capabilities:
- `SourceLocation` dataclass: `pattern: str` (file path), `line: int | None`, `end_line: int | None`, `symbol: str | None`
- `SourceMap` type alias: `dict[str, list[SourceLocation]]` — keyed by responsibility ID
- `anchor_responsibility(resp_id, file, line=None, end_line=None, symbol=None) -> SourceLocation`
- `validate_anchor(loc: SourceLocation) -> bool` — file exists, line range valid
- `find_dark_files(model: ArchModel, project_path: Path) -> list[str]` — files in boundaries not anchored to any responsibility
- Integration into `ModelStore`: source_map stored in model JSON
- CLI: `genesis anchor [path] --resp <id> --file <file> --line <n>`

Tests required:
- `test_anchor_stores_in_source_map`
- `test_validate_anchor_file_exists`
- `test_validate_anchor_bad_file_returns_false`
- `test_find_dark_files_returns_unanchored`
- `test_find_dark_files_returns_empty_when_all_anchored`

### 2.3 Drift Flags (vagrant + stale)
**Tier:** 2 | **Effort:** M | **Dep:** 2.2 (SourceAnchor), 1.5 (ModelStore)

Machine-observation flags on responsibilities awaiting user verdict.

Additions to `ModelResponsibility`:
- `vagrant: bool = False` — code-discovered claim not committed to model
- `stale: bool = False` — committed claim whose code no longer backs it
- `last_touched_at: str | None = None`

New module: `src/genesis_architect_pro/drift_detector_v2.py` (replaces basic recovery_scan.py)

Capabilities:
- `DriftScope` dataclass: `node_id`, `changed_files`, `reason`
- `DrifterConfig` dataclass: `use_git: bool`, `mtime_baseline: float | None`
- `detect_drift(model: ArchModel, project_path: Path, config: DriftConfig) -> list[DriftScope]`
  - Two-gate: mtime check → git content diff (eliminates touch-without-edit noise)
  - Per-node routing: finds which model node owns a changed file
- `flag_stale(resp_id, model) -> None` — sets `stale=True` on responsibility
- `flag_vagrant(statement, node_id, model) -> None` — adds new vagrant responsibility
- `reconcile_drift(node_id, model, git_commit) -> None` — clears flags, advances anchor timestamp
- CLI: `genesis drift [path]` — shows all vagrant + stale responsibilities

Tests required:
- `test_detect_drift_returns_changed_nodes`
- `test_mtime_gate_filters_unchanged`
- `test_git_gate_eliminates_touch_noise`
- `test_flag_stale_sets_field`
- `test_flag_vagrant_creates_responsibility`
- `test_reconcile_clears_flags`
- `test_reconcile_advances_timestamp`

### 2.4 Active Hotspot Warnings with Prescriptive Actions
**Tier:** 2 | **Effort:** M | **Dep:** git_analyzer.py, import_graph.py

Each hotspot gets a specific prescription, not just a label.

New module: `src/genesis_architect_pro/hotspot_advisor.py`

Capabilities:
- `HotspotPrescription` dataclass: `file`, `churn_commits`, `authors`, `fan_in`, `fan_out`, `risk_level`, `prescription: str`, `estimated_score_delta: float`, `confidence: float`
- `advise_hotspots(churn: dict, modules: dict, top_n: int = 3) -> list[HotspotPrescription]`
  - Rank by: churn_commits × fan_in (composite risk)
  - Generate specific prescription based on dominant pattern:
    - High fan_in + high churn → "Extract stable interface; dependents import interface not implementation"
    - High fan_out + high churn → "Split by responsibility; each cohesive group becomes a module"
    - Low bus_factor + high churn → "Document the implicit contract; add tests for each caller"
  - Estimate score delta: `hub_penalty_reduction × coupling_weight + modularity_gain × modularity_weight`
  - Confidence: `min(1.0, commits / 10 × author_diversity)`

Tests required:
- `test_advise_returns_top_n_hotspots`
- `test_high_fan_in_prescription`
- `test_high_fan_out_prescription`
- `test_low_bus_factor_prescription`
- `test_score_delta_positive`
- `test_confidence_scales_with_evidence`

### 2.5 Architecture Regression Test DSL
**Tier:** 2 | **Effort:** L | **Dep:** decay_regressor.py (1.4), git_analyzer.py

`.genesis.rules.yml` extended DSL that fails CI on violations.

New module: `src/genesis_architect_pro/rules_dsl.py`

Schema:
```yaml
assert:
  score_above: 70
  no_circular_deps: true
  bus_factor_min: 2
  coupling_below: 0.3
  score_not_declining_over: 4_weeks
  no_anti_pattern: [God Class, Shotgun Surgery]
  banned_imports: ["legacy/*", "v1/*"]
thresholds:
  max_critical_anti_patterns: 0
  max_high_anti_patterns: 3
per_module:
  "src/auth/*":
    score_above: 80
    bus_factor_min: 2
```

Capabilities:
- `RulesConfig` dataclass: all assertions + thresholds + per-module overrides
- `load_rules(path: Path) -> RulesConfig`
- `evaluate_rules(config, score_result, anti_patterns, churn, forecast) -> ValidationResult`
  - `ValidationResult` dataclass: `success: bool`, `violations: list[RuleViolation]`
  - `RuleViolation` dataclass: `rule`, `message`, `actual`, `expected`, `level: error | warning`
- Temporal assertion: `score_not_declining_over: N_weeks` — runs WLS on history, fails if slope significant-negative over N weeks
- CLI: `genesis check [path]` — exits 0 on pass, 1 on error violations

Tests required:
- `test_load_rules_parses_yaml`
- `test_score_above_passes`
- `test_score_above_fails`
- `test_no_circular_deps_catches_cycles`
- `test_bus_factor_min_fails_single_author`
- `test_temporal_assertion_stable_passes`
- `test_temporal_assertion_declining_fails`
- `test_per_module_override_stricter`
- `test_banned_imports_catches_pattern`

### 2.6 Change Coupling Detection
**Tier:** 2 | **Effort:** M | **Dep:** git_analyzer.py

File pairs that change together with statistical confidence.

Additions to `git_analyzer.py`:
- `ChangeCoupling` dataclass: `file_a`, `file_b`, `cochange_count`, `confidence`
- `detect_change_coupling(commits: list[dict], min_cochanges: int = 3) -> list[ChangeCoupling]`
  - Build co-change map: for each commit, pairwise combinations of up to 10 files
  - `confidence = cochange_count / max(commit_count_file_a, commit_count_file_b)`
  - Sort by confidence descending, return top 50
- Expose in `per_module_churn` return value under `change_couplings` key
- CLI output: `genesis git [path] --coupling`

Tests required:
- `test_coupling_detected_from_commits`
- `test_confidence_ratio_correct`
- `test_min_cochanges_filter`
- `test_pairwise_limited_to_10_files`
- `test_sorted_by_confidence`

---

## Track 3 — Free Core Improvements

### 3.1 Annotated Project Structure Scanner
**Tier:** 3 | **Effort:** S | **Dep:** None

New module: `src/genesis_architect_pro/structure_scanner.py`

- File categories: `manifest`, `infrastructure`, `environment`
- Known manifests: package.json, Cargo.toml, go.mod, pyproject.toml, setup.py, pom.xml, Gemfile, etc.
- Known infra: Dockerfile*, docker-compose.*, fly.toml, .github/workflows/*.yml, *.tf, Procfile
- Known env: .env.example, .env.sample, .env.template
- `project_structure(path: Path) -> str` — annotated tree, noise collapsed, `... (N more)` for unannotated
- `is_codebase(path: Path) -> bool` — quick check: .git or manifest exists
- CLI: `genesis structure [path]`

### 3.2 Python Stdlib Filter (Complete)
**Tier:** 3 | **Effort:** S | **Dep:** None

Extend `import_graph.py`:
- `PYTHON_STDLIB: frozenset[str]` — 100+ module names matching Python 3.11 stdlib
- `is_stdlib_import(module_name: str) -> bool`
- Apply in Python import parsing to exclude stdlib from dependency graph

### 3.3 Weekly Commit Timeline
**Tier:** 3 | **Effort:** S | **Dep:** git_analyzer.py

Additions to `git_analyzer.py`:
- `WeeklySnapshot` dataclass: `week_start: str`, `commits: int`, `churn: int`, `active_files: int`
- `build_timeline(commits: list[dict], period_weeks: int) -> list[WeeklySnapshot]`
  - Normalize all commits to Monday of their week
  - Fill all weeks in period (no gaps)
- `print_sparkline(timeline: list[WeeklySnapshot]) -> str` — ASCII trend chart

### 3.4 Bus Factor Per File
**Tier:** 3 | **Effort:** S | **Dep:** git_analyzer.py

Additions to `git_analyzer.py` per-file result:
- `authors: set[str]` — distinct committers
- `bus_factor: int` — `len(authors)`
- Add to `per_module_churn` output dict

### 3.5 Dependency Index (O(1) Lookups)
**Tier:** 3 | **Effort:** S | **Dep:** import_graph.py

See 1.3 above — also a Free core improvement that benefits all rules.

### 3.6 Git Cache Layer
**Tier:** 3 | **Effort:** S | **Dep:** git_analyzer.py

Additions to `git_analyzer.py`:
- `_cache_path(project_path, days) -> Path` — `.genesis/git_cache_{days}d.json`
- `_load_cache(path) -> dict | None` — returns None if stale (> 6 hours old)
- `_save_cache(path, data) -> None`
- Wrap `per_module_churn()` with cache read/write

### 3.7 Score Sparkline in CLI
**Tier:** 3 | **Effort:** S | **Dep:** score history

In `architecture_scorer.py`:
- `render_sparkline(history: list[dict], width: int = 20) -> str` — ASCII bar chart of last N scores
- Display in `print_score_report` when ≥ 3 history entries exist

---

## Track 4 — Pro-Only Intelligence Layer

### 4.1 Temporal Scorer (velocity-adjusted scores)
**Tier:** 4 | **Effort:** M | **Dep:** 1.4 (DecayRegressor), git_analyzer.py

New module: `src/genesis_architect_pro/temporal_scorer.py`

- `TemporalScore` dataclass: `module`, `static_score`, `temporal_score`, `trend`, `projected_score`, `projection_confidence`, `risk_level`
- `TemporalReport` dataclass: `overall_trend`, `overall_temporal_score`, `modules`, `degrading`, `improving`
- `TemporalScorer.score(churn, static_scores) -> TemporalReport`
  - Churn trend + commit acceleration → temporal penalty
  - `churn_penalty = churn_trend × churn_weight × 0.3`
  - `temporal_score = static_score - total_penalty`
  - Risk: critical < 30, high < 50, medium < 70, low ≥ 70
- CLI: `genesis forecast [path]`

### 4.2 ForecastV2 (module-level decay rankings)
**Tier:** 4 | **Effort:** M | **Dep:** 4.1, 1.4, score history

New module: `src/genesis_architect_pro/forecast_v2.py`

- `ModulePrediction` dataclass: `module`, `current_score`, `predicted_score`, `risk_level`, `weeks_to_threshold`, `recommendations: list[str]`
- `ForecastV2Report` dataclass: `headline`, `project_forecast`, `module_predictions`, `at_risk_modules`, `recommendations`
- `ForecastV2Engine.generate(project_path) -> ForecastV2Report`
- `genesis forecast [path] --detailed` — full per-module breakdown

### 4.3 Self-Improving Rules Suggester
**Tier:** 4 | **Effort:** M | **Dep:** score history, 2.5 (RulesDSL), anti-pattern history

New module: `src/genesis_architect_pro/rules_suggester.py`

- Read last N score history entries + violation records
- Patterns → rule suggestions:
  - Circular dep in 3+ analyses → suggest `no_circular_deps: true` if not set
  - Score consistently above X → suggest raising `score_above` gate
  - Anti-pattern recurring → suggest `no_anti_pattern` entry
- `suggest_rules(project_path: Path) -> list[RuleSuggestion]`
- MCP tool: `suggest_rules`

---

## Track 5 — UI and Reporting Upgrades

### 5.1 HTML Self-Contained Reporter
**Tier:** 5 | **Effort:** L | **Dep:** All analysis modules

New module: `src/genesis_architect_pro/html_reporter.py`

Sections (modular, each a function returning HTML fragment):
- `header_section(project_name, timestamp)` — title, run metadata
- `overview_section(score_result)` — score gauge, profile, module count
- `score_section(score_result, history)` — dimension breakdown, sparkline chart
- `antipatterns_section(report)` — severity-sorted cards
- `layers_section(modules)` — layer distribution
- `forecast_section(forecast)` — trajectory chart (SVG inline), confidence band
- `refactoring_section(plan)` — step-by-step with operations
- `coupling_section(couplings)` — top co-change pairs
- `render_report(all_data: dict) -> str` — assembles full self-contained HTML
- CLI: `genesis report [path] --html --output report.html`

### 5.2 Architecture Velocity Dashboard
**Tier:** 5 | **Effort:** M | **Dep:** 5.1, weekly timeline, forecast

Part of HTML reporter — dedicated "velocity" tab:
- Score per week per module (table + mini SVG sparklines)
- Churn rate trends
- Anti-pattern count evolution
- Bus factor per module over time
- Predicted score at 4/8/12 weeks with confidence bands

---

## Track 6 — CI, Docker, Validation, and Benchmarks

### 6.1 GitHub Actions Adapter (Pro)
**Tier:** 6 | **Effort:** M | **Dep:** 2.5 (RulesDSL)

New module: `src/genesis_architect_pro/github_action.py`

- Read `GITHUB_EVENT_PATH` for PR context
- Run full analysis + rules check
- Write summary to `GITHUB_STEP_SUMMARY`
- Post PR comment via `GITHUB_TOKEN` + GitHub REST API
- Exit 1 on error violations
- Template: `.github/workflows/genesis-check.yml`

### 6.2 Pre-commit Boundary Enforcement Hook (Pro)
**Tier:** 6 | **Effort:** S | **Dep:** 2.5 (RulesDSL)

New script: `src/genesis_architect_pro/precommit_hook.py`

- Get staged files: `git diff --cached --name-only`
- Run rules engine on staged files only (not full project)
- Output: exact rule violated + file path + suggestion
- Exit 1 on violation, 0 on clean
- Generator: `genesis hook install [path]` writes `.git/hooks/pre-commit`

### 6.3 Benchmark Suite
**Tier:** 6 | **Effort:** M | **Dep:** architecture_scorer.py

New module: `src/genesis_architect_pro/benchmark.py`

Known OSS projects with expected score ranges:
```python
BENCHMARKS = [
    {"repo": "psf/requests",      "expected_min": 60, "expected_max": 85},
    {"repo": "tiangolo/fastapi",  "expected_min": 65, "expected_max": 90},
    {"repo": "pallets/flask",     "expected_min": 70, "expected_max": 90},
    {"repo": "encode/httpx",      "expected_min": 65, "expected_max": 88},
]
```
- Clone repos to temp dir → run scorer → compare to expected range
- `BenchmarkResult` dataclass: `repo`, `actual_score`, `expected_min`, `expected_max`, `passed`
- CLI: `genesis benchmark` — runs all, reports pass/fail + calibration drift

### 6.4 Docker Image
**Tier:** 6 | **Effort:** S | **Dep:** All modules

`Dockerfile`:
```dockerfile
FROM python:3.12-slim
COPY src/ /app/src/
RUN pip install -e /app
ENTRYPOINT ["genesis"]
```
- `genesis-pro:latest` published to GHCR
- `genesis-pro:ci` — minimal image for CI use

---

## Implementation Sequence (Ordered by Dependency + Value)

```
Week 1:
  3.2  Python stdlib filter (complete)     [S, no deps]
  3.4  Bus factor per file                 [S, no deps]
  3.5  DependencyIndex (O(1) lookups)      [S, no deps]
  3.3  Weekly commit timeline              [S, git_analyzer]
  3.7  Score sparkline in CLI              [S, score history]
  3.6  Git cache layer                     [S, git_analyzer]
  1.2  Confidence annotations              [M, no deps]

Week 2:
  1.1  Prompt budget manager               [M, no deps]
  3.1  Project structure scanner           [S, no deps]
  1.3  Partial re-analysis scoping         [M, DependencyIndex]
  2.6  Change coupling detection           [M, git_analyzer]

Week 3:
  1.4  WLS Decay Regressor                 [L, score history]
  1.5  Dual-layer model (ModelStore)       [L, no deps]

Week 4:
  2.1  Model diff engine                   [M, ModelStore]
  2.2  Source-level responsibility anchoring [L, ModelStore]
  2.3  Drift flags (vagrant + stale)        [M, SourceAnchor, ModelStore]

Week 5:
  2.4  Hotspot advisor                     [M, git_analyzer, import_graph]
  2.5  Architecture regression test DSL    [L, DecayRegressor, git_analyzer]
  4.1  Temporal scorer                     [M, DecayRegressor, git_analyzer]

Week 6:
  4.2  ForecastV2                          [M, TemporalScorer, DecayRegressor]
  4.3  Self-improving rules suggester      [M, score history, RulesDSL]
  2.6  Cycle breaking intelligence         [M, anti-pattern detector]

Week 7:
  5.1  HTML self-contained reporter        [L, all analysis]
  5.2  Architecture velocity dashboard     [M, HTML reporter]

Week 8:
  6.1  GitHub Actions adapter              [M, RulesDSL]
  6.2  Pre-commit boundary hook            [S, RulesDSL]
  6.3  Benchmark suite                     [M, scorer]
  6.4  Docker image                        [S, all]
```

---

## Success Criteria for Pro v4 Launch

- [ ] All Track 1 (Critical) items complete and tested
- [ ] All Track 2 (High-value) items complete and tested
- [ ] Confidence annotations present on every output field
- [ ] HTML reporter produces valid, self-contained HTML
- [ ] GitHub Actions adapter passes CI on genesis-architect itself
- [ ] Pre-commit hook rejects boundary violations in < 5 seconds
- [ ] Benchmark suite all green against 4 OSS repos
- [ ] Decay regressor returns forecasts on 12+ data-point history
- [ ] Dual-layer model roundtrips through save/load without loss
- [ ] Model diff correctly identifies Moved vs. delete+add
- [ ] Source anchors validate against actual filesystem
- [ ] All Track 1 items have ≥ 90% test coverage
