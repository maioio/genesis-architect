# Release Review — Recovery Intelligence v1.0

**Package:** `genesis_architect_pro`  
**Commit:** `e24fc5d` (tag: Recovery Intelligence v1.0 — Stable)  
**Branch:** `pro-v3-analysis`  
**Remote:** `https://github.com/maioio/genesis-architect-pro`  
**Status:** Locked — bug fixes and maintenance only  
**Date:** 2026-06-28

---

## 1. Executive Summary

Recovery Intelligence is the diagnostic core of Genesis Architect PRO. It answers one question on demand: *"What is wrong with this codebase's architecture, and what should I do first?"*

The subsystem runs a coordinated sweep of nine analysis engines against any project directory — scoring architecture health, detecting model drift, locating fragility hotspots, anchoring planned responsibilities to source code, and forecasting architectural decay — then collapses every signal into a single structured report with three output formats (JSON, Markdown, HTML) and a prioritised, confidence-ranked recommendation list.

The implementation is 4 788 lines of production Python across 9 modules, backed by 634 dedicated tests (998 total in the suite). It is read-only by default, crash-safe at every boundary, and deterministic: identical inputs always produce identical outputs.

Recovery Intelligence v1.0 is complete, stable, and accepted.

---

## 2. What Was Built

### Steps 1–9 (foundation, preceding this release cycle)
- `stdlib_filter` — Python 3.11+ stdlib name set for import classification
- `architecture_scorer` — adaptive 0-100 architecture health score with confidence annotation and historical trend tracking (`score_history.jsonl`)
- `dependency_index` — reverse-dependency map for change-impact analysis
- `decay_regressor` — weighted least-squares regression over score history; produces a `DecayForecast` with predicted trajectory and weeks-to-critical
- `model_store` — persistence layer for `model.json` (committed) and `planned.json` (planned); structural diff between them
- `drift_detector` — compares committed vs planned to produce `DriftFlags`: vagrant candidates (committed but not planned) and stale candidates (planned but not in code)
- `source_anchor` — maps each planned responsibility statement to concrete code locations via 3-pass fuzzy matching; persists results into model store
- `antipattern_detector` — detects 7 anti-pattern types (god-class, hub-file, circular-dep, dead-code, feature-envy, leaky-abstraction, shotgun-surgery) with per-finding confidence

### Steps 10–12 (this release cycle)
- `drift_scorer` — numeric penalty accumulator scoring drift [0, 100] across four signals: vagrant (V, cap 40), stale (S, cap 35), coverage (C, cap 20), temporal decay (T, cap 15)
- `recovery_report` — report generator producing `RecoveryReport` from any `scan()` output; three output formats; 9 recommendation categories; fully deterministic

### Phase 2a (integration closure)
Five missing wires that unified all engines into a single coherent pipeline:
1. `architecture_scorer.score_project()` → `scan()` output (`architecture_score`, `architecture_profile`)
2. `antipattern_detector.detect_all()` → `scan()` output (`anti_patterns`)
3. `source_anchor.persist_anchors()` → `scan()` output (`anchor_persist_result`)
4. `_missing_plan_recommendations()` → `recovery_report` (recommendation when `planned.json` absent)
5. `decay_regressor.forecast_from_history()` → `drift_scorer` (temporal penalty T)

### Cleanup pass (v1.0 stabilisation)
- Removed two dead helpers (`_safe_get`, `_confidence_label`) and unused import (`typing.Any`)
- Fixed `_missing_plan_recommendations` detection bug (wrong basis string match)
- Updated `all_expected` metadata list to include Phase 2a keys
- Expanded `scan()` docstring to document all 16 return keys
- Stripped development markers (`[Wire N]`) from source
- Produced architecture reference document (`docs/recovery_intelligence_v1.md`)

---

## 3. Problems Solved

| Problem | Solution |
|---|---|
| No way to know if a project's committed code matches its planned architecture | `drift_detector` + `drift_scorer` quantify the gap as a [0, 100] risk score |
| Planned responsibilities with no code backing them are invisible | `source_anchor` maps each responsibility statement to actual source locations |
| Architecture quality degrades gradually and unnoticed | `architecture_scorer` + `decay_regressor` track scores over time and forecast when the project will reach a critical threshold |
| Anti-patterns accumulate without formal detection | `antipattern_detector` surfaces 7 structural anti-patterns with confidence scores |
| Fragility signals live in separate tools with no unified view | `recovery_scan.scan()` runs all engines and returns a single flat dict |
| Findings need different consumers (humans, CI, LLMs) | `RecoveryReport` renders to HTML, Markdown, and JSON from a single computation |
| "Where do I start?" is unanswerable without priority ranking | 9 recommendation categories with explicit priority, confidence, quick-win, and risk-zone classification |
| Missing `planned.json` produces silent empty results | Explicit `no-planned-model` recommendation with `genesis plan init` guidance |
| Any engine failure breaks the whole scan | Every engine wrapped in `try/except`; failures surface as warning strings, not exceptions |

---

## 4. Public APIs Introduced

All 34 symbols are exported from `genesis_architect_pro.__init__` and listed in `__all__`.

### Report generation

```python
from genesis_architect_pro import generate_report, generate_report_for_project
from genesis_architect_pro import RecoveryReport, ArchitectureHealth, DriftSummary
from genesis_architect_pro import Recommendation, ReportMetadata
```

| Symbol | Description |
|---|---|
| `generate_report(scan_output: dict) -> RecoveryReport` | Pure function; converts any `scan()` output dict to a report. Never raises. |
| `generate_report_for_project(project_dir: Path) -> RecoveryReport` | Disk-backed wrapper; runs `scan()` then `generate_report()`. Never raises. |
| `RecoveryReport` | The report object. Has `.to_dict()`, `.to_json()`, `.to_markdown()`, `.to_html()`. Also exposes `.quick_wins`, `.risk_zones`, `.deep_refactor_candidates` as filtered views. |
| `ArchitectureHealth` | Score, label, anti-pattern count, hotspot files. |
| `DriftSummary` | Overall score, risk level, vagrant/stale/unanchored counts. |
| `Recommendation` | Single finding: priority, category, title, reason, evidence, confidence, suggested_action, affected, quick_win, risk_zone. |
| `ReportMetadata` | Generator, schema version, scan key presence tracking. |

### Drift scoring

```python
from genesis_architect_pro import (
    score_drift, compute_drift_score,
    DriftScore, NodeDriftScore, DriftScorerConfig,
)
```

| Symbol | Description |
|---|---|
| `compute_drift_score(project_dir, *, forecast=None, config=None) -> DriftScore` | High-level entry point. Loads all inputs from disk. |
| `score_drift(flags, anchor_report, forecast=None, *, config) -> DriftScore` | Low-level; accepts pre-loaded objects. |
| `DriftScore` | Overall score, risk level, per-node scores, top risk nodes, confidence, basis. |
| `NodeDriftScore` | Per-node penalty breakdown (vagrant, stale, coverage components). |
| `DriftScorerConfig` | Tunable penalty caps and risk thresholds. |

### Drift detection

```python
from genesis_architect_pro import (
    detect_drift, compute_drift_flags,
    DriftFlags, VagrantCandidate, StaleCandidate,
)
```

| Symbol | Description |
|---|---|
| `compute_drift_flags(project_dir) -> DriftFlags` | High-level; reads committed and planned models from disk. |
| `detect_drift(committed, planned, source_map, ...) -> DriftFlags` | Low-level; accepts pre-loaded models. |
| `DriftFlags` | Lists of vagrant and stale candidates; overall confidence and basis string. |
| `VagrantCandidate` | Node present in committed model but absent from planned. |
| `StaleCandidate` | Responsibility in planned but absent from both committed and source_map. |

### Source anchoring

```python
from genesis_architect_pro import (
    anchor_from_store, anchor_responsibilities, persist_anchors,
    AnchorEntry, AnchorResult, AnchorReport, PersistResult,
)
```

| Symbol | Description |
|---|---|
| `anchor_from_store(project_dir) -> AnchorReport` | High-level; loads committed model and runs anchoring. |
| `anchor_responsibilities(responsibilities, source_map) -> AnchorReport` | Low-level; accepts pre-loaded data. |
| `persist_anchors(report, store) -> PersistResult` | Merges anchors into model store. Idempotent. |
| `AnchorReport` | Full mapping: responsibility ID → `AnchorResult`. Counts anchored/unanchored. |
| `AnchorResult` | List of `AnchorEntry` objects for one responsibility. |
| `AnchorEntry` | Single code location: pattern, file, line range, symbol, confidence, basis. |
| `PersistResult` | added, skipped, saved, warnings. |

### Model store (34 total symbols; key ones listed)

```python
from genesis_architect_pro import ModelStore, ArchModel, ModelNode, ModelDiff
```

| Symbol | Description |
|---|---|
| `ModelStore(project_dir)` | Manages `.genesis/model.json` and `.genesis/planned.json`. |
| `ArchModel` | Top-level architecture model: nodes, links, groups. |
| `ModelNode` | Component/service/database node with id, kind, name, responsibilities, source_map. |
| `ModelDiff` | Structural diff: added/removed/changed nodes, links, responsibility changes. |

---

## 5. Internal Architecture

```
genesis_architect_pro/
├── recovery_scan.py          Pipeline orchestrator — scan() entry point
├── recovery_report.py        Report generator + 3 renderers (JSON/MD/HTML)
├── drift_scorer.py           Penalty accumulator [0, 100]
├── drift_detector.py         Vagrant + stale candidate detection
├── source_anchor.py          Responsibility → code location mapping
├── model_store.py            Model persistence (committed + planned)
├── decay_regressor.py        WLS temporal decay forecast
├── architecture_scorer.py    Adaptive 0-100 architecture health score
└── antipattern_detector.py   7-type static anti-pattern detection
```

**Layering (bottom to top):**

```
Free core (genesis_architect)
    import_graph  ──────────────────────────────────┐
                                                    ↓
PRO foundation layer                       architecture_scorer
    model_store ─────┬──────────────────── antipattern_detector
    decay_regressor  │
                     ↓
PRO detection layer
    drift_detector ──┐
    source_anchor ───┼──→ drift_scorer
                     │
                     ↓
PRO report layer
    recovery_scan (orchestrates all of the above)
         └──→ recovery_report → RecoveryReport
                                   ├── .to_dict()
                                   ├── .to_json()
                                   ├── .to_markdown()
                                   └── .to_html()
```

No circular dependencies. Each layer only imports from layers below it.

---

## 6. Recovery Pipeline Overview

`scan(project_dir)` runs these steps in order. Every step is independently guarded.

| # | Step | Engine | Output key(s) |
|---|---|---|---|
| 1 | Git churn analysis | `fix_commit_hotspots()` | `fix_commit_hotspots` |
| 2 | Hardcoded URL detection | `external_url_count()` | `external_url_count` |
| 3 | Version coherence check | `version_drift()`, `doc_version()` | `version_sources`, `doc_version`, `version_drift` |
| 4 | Dead file heuristic | `dead_file_candidates()` | `dead_file_candidates` |
| 5 | Model sync from import graph | `sync_model_from_graph()` | `model_sync` |
| 6 | Committed ↔ planned diff | `model_store.model_diff()` | `model_diff` |
| 7 | Drift flag detection | `drift_detector.compute_drift_flags()` | `drift_flags` |
| 8 | Architecture scoring | `architecture_scorer.score_project()` | `architecture_score`, `architecture_profile` |
| 9 | Anti-pattern detection | `antipattern_detector.detect_all()` | `anti_patterns` |
| 10 | Source anchoring | `source_anchor.anchor_from_store()` | `source_anchors` |
| 11 | Anchor persistence | `source_anchor.persist_anchors()` | `anchor_persist_result` |
| 12 | Decay forecast | `decay_regressor.forecast_from_history()` | (internal: `_decay_forecast`) |
| 13 | Drift scoring | `drift_scorer.compute_drift_score()` | `drift_score` |
| 14 | Report generation | `recovery_report.generate_report()` | `recovery_report` |

**Scan output:** 16 keys, always present, always JSON-serialisable.  
**Report output:** `RecoveryReport` with 9 recommendation categories, 3 output formats.

---

## 7. Free vs Pro Responsibilities

| Responsibility | Free (`genesis_architect`) | PRO (`genesis_architect_pro`) |
|---|---|---|
| Import graph construction | ✅ `build_graph()`, `load_or_build()` | Consumes via `import_graph` |
| Architecture scoring | ✅ Base scorer (fixed profiles) | ✅ Adaptive profiles + confidence + history |
| Anti-pattern detection | ✅ 4 base detectors | ✅ +3 advanced detectors (feature-envy, leaky-abstraction, shotgun-surgery) |
| Model persistence | — | ✅ `model_store` (committed + planned) |
| Drift detection | — | ✅ `drift_detector` (vagrant + stale) |
| Source anchoring | — | ✅ `source_anchor` (3-pass fuzzy matching) |
| Drift scoring | — | ✅ `drift_scorer` (4-component penalty accumulator) |
| Temporal decay forecast | — | ✅ `decay_regressor` (WLS regression) |
| Recovery report | — | ✅ `recovery_report` (3 output formats, 9 recommendation categories) |
| Pipeline orchestration | — | ✅ `recovery_scan.scan()` |

The free core provides the graph substrate. PRO builds the entire diagnostic and reporting layer on top of it. There is a clean boundary: PRO imports from the free core; the free core has no knowledge of PRO.

---

## 8. Testing Summary

### Coverage by subsystem

| Test file | Module(s) covered | Tests |
|---|---|---|
| `test_step4_decay_regressor.py` | decay_regressor | 75 |
| `test_step5_model_store.py` | model_store | 65 |
| `test_step6_model_diff.py` | model_store (diff) | 66 |
| `test_step7_drift_detector.py` | drift_detector | 60 |
| `test_step8_source_anchor.py` | source_anchor | 70 |
| `test_step9_persist_anchors.py` | source_anchor (persist) | 38 |
| `test_step10_drift_scorer.py` | drift_scorer | 77 |
| `test_step11_recovery_report.py` | recovery_report (data) | 86 |
| `test_step12_html_report.py` | recovery_report (HTML) | 61 |
| `test_phase2a_integration.py` | Full pipeline (all engines) | 36 |
| **Recovery Intelligence total** | | **634** |
| Other PRO tests (upstream) | | 364 |
| **Grand total** | | **998** |

### Test strategy
- **Unit tests** for every public function and data class
- **Integration tests** in `test_phase2a_integration.py` validate all five pipeline wires end-to-end
- **Crash-safety tests** verify every engine's `try/except` boundary using corrupted or missing inputs
- **XSS injection tests** in `test_step12_html_report.py` confirm `_h()` escaping on all user-controlled strings
- **Determinism tests** confirm identical inputs produce byte-for-byte identical HTML/MD/JSON
- **Result:** 998 passed, 0 failures, 7 benign `RuntimeWarning`s (all from deliberate corrupted-input guard tests)

---

## 9. Performance Summary

Measured on Windows 11, Python 3.14, empty project directory (warm imports):

| Operation | Time |
|---|---|
| `scan()` on empty project (all engines) | ~23 ms |
| `generate_report()` + `to_html()` | ~0.1 ms |
| Full pipeline (scan + report + HTML) | ~24 ms |

The dominant cost in `scan()` is `architecture_scorer.score_project()` which builds or loads the import graph. For real projects:
- Small projects (<50 modules): expect 200–800 ms
- Medium projects (50–200 modules): expect 1–4 s
- Large projects (>200 modules): expect 4–15 s

All costs are driven by the free-core import graph builder. The Recovery Intelligence reporting layer adds negligible overhead on top.

**No profiling-informed optimisations were made in v1.0.** Performance is acceptable for on-demand CLI and CI use. It is not suitable for hot-path or real-time invocation without caching.

---

## 10. Known Limitations

### By design (will not change in v1.x)

1. **Read-only except anchor persistence.** `scan()` never modifies `planned.json`. Drift is diagnosed, never auto-healed.
2. **No streaming output.** `scan()` runs all engines sequentially and returns a complete dict. There is no incremental/streaming mode.
3. **No UI integration.** The HTML output is a self-contained static document. There is no live dashboard or WebSocket endpoint.
4. **No parallel engine execution.** Engines run in sequence. Parallelising them would require careful shared-state isolation.

### Technical constraints

5. **Dead-file detection is a heuristic.** It uses regex-based import pattern matching, not a true module graph. Dynamic imports, reflection, and `importlib` bypass it.
6. **Stale detection requires dual-signal.** A responsibility must be absent from both committed nodes AND source_map to be flagged stale. This suppresses false positives but can miss stale responsibilities in uncrawled source trees.
7. **DecayForecast requires ≥3 historical scores.** Projects with fewer archived `score_history.jsonl` records receive no temporal penalty in drift scoring.
8. **`external_url_count` and `model_diff` are computed but not consumed by `generate_report`.** They are available in the raw scan dict for callers to use; they do not yet drive recommendations.
9. **Source anchoring uses fuzzy matching only.** There is no AST-level semantic binding. Anchors can be wrong if responsibility statements share keywords with unrelated code.
10. **`architecture_profile` auto-detection is heuristic.** It relies on `evolution.json` markers and directory structure, not a formal project type declaration.

---

## 11. Future Extension Points

These points are **intentionally reserved** and left unimplemented in v1.0. They are the natural growth surface for v2.

### Within Recovery Intelligence

| Extension point | Location | Description |
|---|---|---|
| `external_url_count` → recommendations | `recovery_report._url_recommendations()` | Convert URL fragility counts into a recommendation category (e.g., "12 hardcoded endpoints in auth.py") |
| `model_diff` → recommendations | `recovery_report._model_diff_recommendations()` | Surface structural model divergence as a recommendation (e.g., "planned model has 3 nodes removed since last commit") |
| `doc_version` → recommendations | `recovery_report._doc_version_recommendations()` | Flag doc/code version mismatch |
| Parallel engine execution | `recovery_scan.scan()` | Run independent engines (URL scan, git churn, architecture score, anti-pattern) concurrently |
| Streaming scan progress | `recovery_scan.scan_stream()` | Yield partial results as engines complete (useful for CLI progress display) |
| Anchor confidence upgrade | `source_anchor` | Add AST-level binding (e.g., actual symbol resolution) alongside fuzzy matching |
| Recommendation suppression | `recovery_report` | Allow callers to suppress specific categories or nodes via config |
| Trend-aware recommendations | `drift_scorer` + `recovery_report` | Flag nodes whose drift score is increasing week-over-week even if still below risk threshold |

### For future systems that should integrate with Recovery Intelligence

| System | Integration surface | How |
|---|---|---|
| **Governance Orchestrator (P1)** | `scan()` output dict | Governance gates should read `recovery_report.project_risk_level` and `recommendations` to block or warn on PR merge |
| **CI/CD pipeline** | `generate_report_for_project()` | Run as a CI step; exit non-zero if `project_risk_level` ≥ "high" |
| **MCP tools** | `mcp_tools.py` (already wired) | Already reads `recovery_report`; extend to expose structured recommendations as MCP resources |
| **Rules engine** | `rules_engine.py` (already wired) | Already calls `recovery_report`; extend rules to act on specific recommendation categories |
| **Notification system** | `RecoveryReport.to_dict()` | Post drift score changes to Slack/email when score crosses a risk threshold |
| **Historical dashboard** | `architecture_scorer.load_score_history()` | Plot score trends + DecayForecast predictions over time |

---

## 12. Version Compatibility

| Component | Minimum version | Notes |
|---|---|---|
| Python | 3.11 | Uses `frozenset` literals, `X \| Y` type union syntax |
| `genesis_architect` (free core) | Current (C:\temp\genesis-core-wt) | Editable install required; PRO imports `import_graph` and the base scorer/detector |
| Schema version | 1.0 | `RecoveryReport.to_dict()` schema is stable at v1.0; breaking changes require schema version bump |
| `score_history.jsonl` format | v1.0 | Records must have `timestamp` (ISO 8601) and `total` (float); other fields are stored but optional for `forecast_from_history` |
| `.genesis/model.json` | Current `ModelStore` format | No migration tool; breaking changes to the model schema require a migration script |

**Backward compatibility promise for v1.x:**
- All `__all__` exports remain importable with the same signatures
- `RecoveryReport.to_dict()` keys are additive-only (new keys may be added, existing keys will not be renamed or removed)
- `scan()` output keys are additive-only
- The `schema_version` field in `ReportMetadata` will be incremented if any breaking change occurs

---

## 13. Release Notes (GitHub)

```markdown
## Genesis Architect PRO — Recovery Intelligence v1.0

Recovery Intelligence is the diagnostic core of Genesis Architect PRO.
Point it at any project directory. Get a complete architectural health report.

### What's included

**Nine analysis engines, unified into one pipeline:**

- **Architecture scoring** — 0-100 health score with adaptive profile detection
  and historical trend tracking
- **Anti-pattern detection** — 7 structural anti-patterns (god-class, hub-file,
  circular-dep, dead-code, feature-envy, leaky-abstraction, shotgun-surgery)
- **Drift detection** — identifies vagrant nodes (committed but not planned) and
  stale responsibilities (planned but absent from code)
- **Source anchoring** — maps each planned responsibility to its actual code location
  via 3-pass fuzzy matching; persists anchors back to the model store
- **Temporal decay forecasting** — weighted least-squares regression over score
  history predicts when the project will reach a critical threshold
- **Drift scoring** — numeric [0, 100] penalty score combining vagrant, stale,
  coverage, and temporal signals into a single risk level
- **Git churn analysis** — surfaces files with repeated fix commits as fragility signals
- **Dead file detection** — heuristic scan for source files with no detected imports
- **Version coherence check** — flags version mismatches across manifest files

**One report, three formats:**

```python
from genesis_architect_pro import generate_report_for_project

report = generate_report_for_project("/path/to/project")
print(report.to_markdown())   # human-readable
report.to_html()               # self-contained HTML with embedded JSON
report.to_json()               # machine-readable
```

**Prioritised, confidence-ranked recommendations:**

Every finding is classified by priority (1–8), category, confidence, affected
files/nodes, a suggested action, and whether it is a quick win or a risk zone.

### What this is not

- Not a linter. It works at the architectural level, not the line level.
- Not a code fixer. All output is read-only and diagnostic.
- Not a real-time monitor. Designed for on-demand CLI and CI invocation.

### Stability

This release is marked **stable**. The public API and report schema are locked
for v1.x. New features require a v2.0 designation.

### Test coverage

998 tests, 0 failures.

### Performance

~23 ms on an empty project. For real projects, total scan time is dominated by
import graph construction in the free core (typically 200 ms – 15 s depending
on project size).
```

---

## 14. Developer Notes for Future Contributors

### Adding a new recommendation category

1. Add a builder function `_<category>_recommendations(scan: dict, warnings: list[str]) -> list[Recommendation]` in `recovery_report.py`. Follow the existing pattern: guard against missing/non-dict inputs; return `[]` on any error.
2. Choose a priority (1–8) and add a row to the module docstring priority table.
3. Add the builder call inside `generate_report()` in the try/except block pattern.
4. Write tests in `test_step11_recovery_report.py` covering the normal case, missing input, zero-item input, and confidence propagation.
5. No other files need to change.

### Adding a new scan engine

1. Add the engine call in `recovery_scan.scan()`, wrapped in `try/except`. The except clause must set a fallback dict with at least a `warnings` key.
2. Add the new key to `scan_result` and to `all_expected` in `generate_report()`.
3. Document the key in the `scan()` docstring return table.
4. Write integration tests in `test_phase2a_integration.py` or a new file.

### Invariants that must never be violated

- `scan()` never raises.
- `planned.json` is never written by any recovery code path.
- All user-controlled strings in HTML output must pass through `_h()`.
- `RecoveryReport.to_dict()` must be JSON-serialisable (no custom objects, no Path, no datetime).
- Recommendation sorting must remain deterministic: `(priority ASC, -confidence, title ASC)`.
- Stale detection must remain dual-signal (absent from BOTH committed nodes AND source_map).

### Testing requirements

Every new engine integration must include:
- A test that the key is present when the engine succeeds
- A test that the key is present when the engine raises an exception (crash safety)
- A test that the report correctly processes the new key's output

### Schema versioning

If any key is removed from `RecoveryReport.to_dict()` or any existing key changes its type, increment `ReportMetadata.schema_version` from `"1.0"` to `"1.1"` (or `"2.0"` for breaking changes).

---

## Recommendations

### Should Recovery Intelligence remain frozen until v2?

**Yes.** The subsystem is functionally complete for its defined scope. There are no known bugs, no open requirements, and no urgent gaps. The extension points listed in Section 11 are deliberately deferred — they each require design decisions (streaming API shape, AST anchoring strategy, governance integration contract) that should not be made incrementally inside v1.x. The risk of feature creep destabilising a working, well-tested system outweighs the benefit of any individual addition.

**Recommended freeze policy for v1.x:**
- Bug fixes: allowed without review
- Comment and documentation improvements: allowed without review
- Performance improvements that preserve all output: allowed with test confirmation
- New recommendation categories or scan keys: require explicit v1.1 designation and review
- Any change to `RecoveryReport.to_dict()` key names or types: require schema version bump
- Any change to `scan()` existing key names or types: require explicit review

### Which extension points are intentionally reserved for future work?

The following are reserved and should not be implemented without a versioned scope decision:

1. **`_url_recommendations()`** — reserved for v1.1 or v2
2. **`_model_diff_recommendations()`** — reserved for v1.1 or v2
3. **Parallel engine execution in `scan()`** — reserved for v2 (requires interface change)
4. **Streaming scan output** — reserved for v2 (requires new entry point)
5. **AST-level anchor binding** — reserved for v2 (source_anchor architecture change)
6. **Recommendation suppression config** — reserved for v2

### Which future systems should integrate with Recovery Intelligence?

In priority order:

1. **Governance Orchestrator (P1, next)** — Should read `project_risk_level` and the `recommendations` list to implement merge gates. A PR with `project_risk_level == "high"` and unresolved priority-1 recommendations should be blockable by policy.

2. **CI/CD integration** — `generate_report_for_project()` is already designed for non-interactive invocation. A thin CLI wrapper (`genesis recover --ci --fail-on high`) is the only missing piece.

3. **MCP tools** — Already partially integrated (`mcp_tools.py` calls `recovery_report`). The structured `recommendations` list should be exposed as an MCP resource so agents can query "what should I fix first?"

4. **Rules engine** — Already partially integrated. Should be extended to allow rules that fire on specific recommendation categories (e.g., "block merge if any `vagrant` recommendation with confidence ≥ 0.80 exists").

5. **Historical trend dashboard** — `load_score_history()` + `DecayForecast` provide the data substrate. A dashboard rendering score trends and decay predictions is the natural consumer.

---

*Recovery Intelligence v1.0 is closed. The subsystem is stable, documented, tested, and locked. Future development begins only with an explicit version scope decision.*
