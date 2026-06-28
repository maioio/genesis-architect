# Recovery Intelligence v1.0 — Architecture & API Reference

**Status:** Stable  
**Tag:** Recovery Intelligence v1.0  
**Package:** `genesis_architect_pro`  
**Schema version:** 1.0

---

## Overview

Recovery Intelligence is the diagnostic subsystem of Genesis Architect PRO. It analyses a project directory end-to-end and produces a structured, actionable report that surfaces architectural drift, code fragility signals, and recovery recommendations.

It is read-only by default. The only write operation is optional anchor persistence (idempotent, gated on finding new anchors). It never modifies `planned.json`, never auto-reconciles drift, and never integrates with UI or production pipelines.

---

## Pipeline

```
project_dir
    │
    ├─ fix_commit_hotspots()      git history → churn signal
    ├─ external_url_count()       file scan → hardcoded URL fragility
    ├─ version_drift()            manifest files → version coherence
    ├─ doc_version()              README/CHANGELOG → doc version
    ├─ dead_file_candidates()     import graph heuristic → unused files
    ├─ sync_model_from_graph()    import_graph → model_store → committed model
    │     └─ model_store.model_diff()  committed ↔ planned structural diff
    ├─ drift_detector             model_store → DriftFlags (vagrant + stale)
    ├─ source_anchor              model_store → AnchorReport (resp → code mapping)
    │     └─ persist_anchors()   AnchorReport → model_store (write, idempotent)
    ├─ architecture_scorer        import_graph → score 0-100 + profile
    ├─ antipattern_detector       import_graph → AntiPattern list
    ├─ decay_regressor            score_history.jsonl → DecayForecast (optional)
    └─ drift_scorer               DriftFlags + AnchorReport + DecayForecast → DriftScore
         │
         └─ recovery_report       all of the above → RecoveryReport
                                       ├─ .to_dict()      machine-readable JSON
                                       ├─ .to_json()      JSON string
                                       ├─ .to_markdown()  Markdown document
                                       └─ .to_html()      self-contained HTML
```

All engines run inside `scan()`. Every engine is wrapped in `try/except`; failures surface as warning strings inside the relevant sub-dict rather than exceptions. `scan()` never raises.

---

## Modules

### `recovery_scan` — Pipeline orchestrator

**Entry point:** `scan(project_dir: Path) -> dict`

Runs all engines in sequence and returns a single flat dict with 16 keys (see Return Contract below). Also exposes individual scan functions (`fix_commit_hotspots`, `external_url_count`, `version_drift`, `doc_version`, `dead_file_candidates`) for targeted use.

**Key design rules:**
- Every key is always present in the output dict
- Failures produce fallback values, never missing keys
- No mutations to `planned.json` ever

---

### `architecture_scorer` — Structural health scoring

**Entry point:** `score_project(project_path, profile=None, language=None) -> dict`

Computes a 0-100 architecture score (modularity, coupling, cohesion, layering) using an adaptive profile matched to the project type. Annotates the result with confidence and confidence_basis.

**Supporting functions:**
- `load_score_history(project_path) -> list[dict]` — reads `.genesis/score_history.jsonl`
- `append_score_history(project_path, score_result)` — appends one record to history

**Used by:** `recovery_scan` (score + history), `mcp_tools`, `rules_engine`

---

### `antipattern_detector` — Static anti-pattern analysis

**Entry point:** `detect_all(project_path, language=None) -> AntiPatternReport`

Detects 7 anti-pattern types: god-class, hub-file, circular-dep, dead-code, feature-envy, leaky-abstraction, shotgun-surgery. Each result carries a confidence score (0–1) and basis string.

**Used by:** `recovery_scan`, `fragility_classifier`, `refactoring_planner`, `mcp_tools`

---

### `decay_regressor` — Temporal decay forecasting

**Entry point:** `forecast_from_history(history: list[dict], config=None) -> DecayForecast | None`

Fits a weighted least-squares regression to historical architecture scores (recency half-life weighting). Returns `None` when fewer than 3 valid data points exist. The forecast feeds into `drift_scorer` as an optional temporal penalty.

**Key types:** `DecayForecast`, `DecayRegressor`, `DecayRegressorConfig`, `RegressionResult`, `ScorePrediction`, `ScoreDataPoint`

**Used by:** `recovery_scan`

---

### `model_store` — Architecture model persistence

**Entry point:** `ModelStore(project_dir: Path)`

Manages `.genesis/model.json` (committed) and `.genesis/planned.json` (planned). Provides load, save, diff, and divergence detection. Never modifies `planned.json` through the recovery pipeline.

**Key types:** `ModelStore`, `ArchModel`, `ModelNode`, `ModelLink`, `ModelGroup`, `ModelResponsibility`, `ModelDiff`

**Used by:** `recovery_scan`, `drift_detector`, `source_anchor`

---

### `drift_detector` — Architecture drift detection

**Entry point:** `compute_drift_flags(project_dir: Path) -> DriftFlags`

Compares committed model against planned model to identify:
- **Vagrant nodes** — in committed but absent from planned
- **Stale responsibilities** — in planned but absent from both committed nodes and source_map

Requires dual-signal (absent from both committed AND source_map) for stale detection to minimize false positives. Vagrant detection is skipped entirely when `planned.json` is absent.

**Key types:** `DriftFlags`, `VagrantCandidate`, `StaleCandidate`

**Confidence tiers:** high (0.80) when both models and source_map loaded; medium (0.55) when source_map empty; low (0.35) when planned absent.

**Used by:** `recovery_scan`, `drift_scorer`

---

### `source_anchor` — Responsibility-to-code mapping

**Entry points:**
- `anchor_from_store(project_dir: Path) -> AnchorReport` — builds anchor map from committed model
- `persist_anchors(report: AnchorReport, store: ModelStore) -> PersistResult` — merges anchors into model store (idempotent)

Uses 3-pass matching: exact symbol (confidence 0.95) → multi-keyword (0.70) → single keyword (0.45). Caps at 3 anchors per responsibility to reduce noise.

**Key types:** `AnchorEntry`, `AnchorResult`, `AnchorReport`, `PersistResult`

**Used by:** `recovery_scan`, `drift_scorer`

---

### `drift_scorer` — Numeric drift scoring

**Entry point:** `compute_drift_score(project_dir, forecast=None, config=None) -> DriftScore`

Accumulates a penalty score [0, 100] using four components:
- **V** (vagrant penalty, cap 40) — per vagrant candidate weighted by confidence
- **S** (stale penalty, cap 35) — per stale candidate weighted by confidence
- **C** (coverage penalty, cap 20) — unanchored responsibility ratio
- **T** (temporal penalty, cap 15) — from DecayForecast slope when significant

Risk levels: none (<20), low (<50), medium (<75), high (<100).  
Confidence tiers: high ≥0.75, medium ≥0.50, low <0.50.

**Key types:** `DriftScore`, `NodeDriftScore`, `DriftScorerConfig`

**Used by:** `recovery_scan`

---

### `recovery_report` — Report generation and rendering

**Entry points:**
- `generate_report(scan_output: dict) -> RecoveryReport` — pure, never raises
- `generate_report_for_project(project_dir: Path) -> RecoveryReport` — disk-backed wrapper

**Report structure:**

| Field | Type | Description |
|---|---|---|
| `executive_summary` | str | One-paragraph project health narrative |
| `project_risk_level` | str | none / low / medium / high / critical |
| `architecture_health` | ArchitectureHealth | Score, label, anti-patterns, hotspots |
| `drift_summary` | DriftSummary | Overall score, vagrant/stale/unanchored counts |
| `recommendations` | list[Recommendation] | All findings, sorted by priority then confidence |
| `quick_wins` | list[Recommendation] | Subset: low-effort, high-signal |
| `deep_refactor_candidates` | list[Recommendation] | Priority ≤3, not quick-win or risk-zone |
| `risk_zones` | list[Recommendation] | Do-not-touch-yet areas |
| `evidence_basis` | dict[str, str] | Signal source → one-line description |
| `warnings` | list[str] | Non-fatal issues during report generation |
| `metadata` | ReportMetadata | Generator, schema version, key presence tracking |

**Recommendation categories and priorities:**

| Priority | Level | Category | Trigger |
|---|---|---|---|
| 1 | critical | vagrant | Committed node absent from planned, confidence ≥ 0.75 |
| 2 | high | stale | Planned responsibility absent from code, confidence ≥ 0.70 |
| 3 | high | anti-pattern | Static analysis: god-class, hub-file, circular-dep, etc. |
| 4 | medium | coverage | >0% unanchored responsibilities |
| 4 | medium | no-planned-model | `planned.json` absent; no intent model to compare |
| 5 | medium | churn | File touched by ≥3 fix-related commits |
| 6 | low | stale | Planned responsibility absent, confidence < 0.70 |
| 7 | low | dead-file | No detected import references |
| 8 | info | version-drift | Version strings disagree across manifests |

Within each priority band, items are sorted: confidence DESC, then title ASC.

**Output formats:**
- `RecoveryReport.to_dict()` — Python dict, fully JSON-serialisable
- `RecoveryReport.to_json(indent=2)` — JSON string
- `RecoveryReport.to_markdown()` — GitHub-flavoured Markdown
- `RecoveryReport.to_html()` — Self-contained HTML (no external deps, XSS-safe via `_h()` escaping, embedded JSON payload)

All three formats are deterministic for identical inputs.

---

## `scan()` Return Contract

| Key | Type | Source engine | Consumed by report? |
|---|---|---|---|
| `fix_commit_hotspots` | dict[str, int] | git log | Yes (churn recs) |
| `external_url_count` | dict[str, int] | file scan | No (available to caller) |
| `version_sources` | dict[str, str] | manifest files | Yes (version-drift rec) |
| `doc_version` | str \| None | README/CHANGELOG | No (available to caller) |
| `version_drift` | bool | derived | Yes (version-drift rec) |
| `dead_file_candidates` | list[str] | import heuristic | Yes (dead-file recs) |
| `model_sync` | dict | model_store | Yes (no-planned-model rec) |
| `model_diff` | dict | model_store | No (available to caller) |
| `drift_flags` | dict | drift_detector | Yes (vagrant/stale recs) |
| `source_anchors` | dict | source_anchor | Yes (coverage rec) |
| `anchor_persist_result` | dict | source_anchor | No (operational result) |
| `architecture_score` | float \| None | architecture_scorer | Yes (arch health) |
| `architecture_profile` | str | architecture_scorer | No (available to caller) |
| `anti_patterns` | list[dict] | antipattern_detector | Yes (anti-pattern recs) |
| `drift_score` | dict | drift_scorer | Yes (drift summary) |
| `recovery_report` | dict | recovery_report | — (is the report) |

---

## Public API (`__init__.py` exports)

```python
# Recovery Report
from genesis_architect_pro import (
    RecoveryReport, ArchitectureHealth, DriftSummary,
    Recommendation, ReportMetadata,
    generate_report,              # pure: scan_output dict → RecoveryReport
    generate_report_for_project,  # disk-backed: project_dir → RecoveryReport
)

# Drift Scoring
from genesis_architect_pro import (
    DriftScorerConfig, NodeDriftScore, DriftScore,
    score_drift,          # low-level: flags + anchors + forecast → DriftScore
    compute_drift_score,  # high-level: project_dir → DriftScore
)

# Drift Detection
from genesis_architect_pro import (
    DriftFlags, VagrantCandidate, StaleCandidate,
    detect_drift,         # low-level
    compute_drift_flags,  # high-level: project_dir → DriftFlags
)

# Source Anchoring
from genesis_architect_pro import (
    AnchorEntry, AnchorResult, AnchorReport, PersistResult,
    anchor_responsibilities,  # low-level
    anchor_from_store,        # high-level: project_dir → AnchorReport
    persist_anchors,          # project_dir + store → PersistResult
)

# Model Store
from genesis_architect_pro import (
    ModelStore, ArchModel, ModelNode, ModelLink,
    ModelGroup, ModelResponsibility,
    ModelDiff, NodeChange, ResponsibilityChange, LinkChange,
)
```

---

## Design constraints (invariants)

1. `scan()` never raises — all engines are individually guarded.
2. `planned.json` is never written or modified by any recovery path.
3. No auto-reconciliation of drift — detection only, no healing.
4. `persist_anchors()` is idempotent — safe to call on every scan run.
5. All recommendation sorting is deterministic (priority ASC, confidence DESC, title ASC).
6. All user-controlled strings in HTML output are escaped via `_h()`.
7. Conservative detection — stale candidates require dual-signal (absent from BOTH committed nodes AND source_map).
8. The DecayForecast is optional — its absence does not affect other scores.

---

## Test coverage

| Test file | Scope | Tests |
|---|---|---|
| `test_step10_drift_scorer.py` | drift_scorer | 77 |
| `test_step11_recovery_report.py` | recovery_report (data) | 86 |
| `test_step12_html_report.py` | recovery_report (HTML) | 61 |
| `test_phase2a_integration.py` | full pipeline integration | 36 |
| Various step 1–9 tests | upstream modules | 738 |
| **Total** | | **998** |

All 998 tests pass. Zero failures. 7 benign RuntimeWarnings from corrupted-input guard tests.

---

## Stability contract

**Recovery Intelligence v1.0 is stable.**

From this point forward:
- Bug fixes and maintenance changes are allowed without version bump.
- New recommendation categories or scan keys require a v1.1 designation.
- Any change to the `RecoveryReport.to_dict()` schema shape requires a schema version bump.
- `planned.json` must never be written by this subsystem under any circumstances.
