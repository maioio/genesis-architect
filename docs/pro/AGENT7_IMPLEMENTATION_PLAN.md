# Agent 7 — Implementation Plan
<!-- Genesis PRO: the intelligence agent that builds itself -->
<!-- Date: 2026-06-27 | Status: PLANNING -->

## What is Agent 7?

Agent 7 is the Genesis PRO agent that a developer activates inside their project to:
1. Perform deep codebase analysis (scoring, anti-patterns, fragility, temporal forecasting)
2. Maintain a living architecture model (planned vs. committed, drift detection)
3. Generate and enforce governance rules (regression tests, pre-commit hooks, CI gates)
4. Produce intelligence reports (HTML, JSON) and prescriptive actions
5. Self-improve its rules over time based on project history

The name "Agent 7" reflects that it is the 7th phase in the Genesis workflow (after the 6-phase research-first scaffold). It activates once a project is live and needs continuous architectural governance.

---

## Agent 7 Trigger Conditions

Agent 7 is invoked when:
- User runs `genesis analyze [path]` (full analysis pass)
- User runs `genesis forecast [path]` (temporal intelligence)
- User runs `genesis check [path]` (rules validation)
- User runs `genesis drift [path]` (drift detection)
- User runs `genesis report [path] --html` (HTML reporter)
- GitHub Actions runs `genesis-check.yml` on PR
- Pre-commit hook triggers on staged boundary violations

---

## Agent 7 Architecture

```
genesis analyze [path]
        │
        ▼
┌───────────────────────┐
│  Phase 0: Probe       │  is_codebase? language? profile? git?
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Phase 1: Graph       │  import_graph.py → DependencyIndex
│  (Free)               │  structure_scanner.py → annotated tree
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Phase 2: Static      │  architecture_scorer.py + confidence
│  Analysis (Free)      │  antipattern_detector.py + confidence
│                       │  fragility_classifier.py
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Phase 3: Git         │  git_analyzer.py (churn + bus factor +
│  Intelligence (Free   │    weekly timeline + change coupling)
│  basic / Pro full)    │  git cache layer
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐    (Pro gate)
│  Phase 4: Temporal    │  decay_regressor.py → forecast
│  Intelligence (Pro)   │  temporal_scorer.py → velocity scores
│                       │  forecast_v2.py → module risk rankings
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐    (Pro gate)
│  Phase 5: Model       │  model_store.py → planned vs committed
│  Management (Pro)     │  drift_detector_v2.py → vagrant/stale
│                       │  source_anchor.py → file+line anchors
│                       │  model_diff.py → what changed
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐    (Pro gate)
│  Phase 6: Governance  │  rules_dsl.py → evaluate assertions
│  (Pro)                │  hotspot_advisor.py → prescriptions
│                       │  rules_suggester.py → self-improvement
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Phase 7: Report      │  CLI text (Free)
│                       │  JSON (Free)
│                       │  HTML self-contained (Pro)
│                       │  Architecture velocity dashboard (Pro)
└───────────────────────┘
```

---

## Agent 7 Data Flow

### Inputs
| Input | Source | Required |
|-------|--------|---------|
| `project_path` | CLI arg | Yes |
| `language` | evidence.json or auto-detect | No |
| `profile` | evidence.json or CLI `--profile` | No |
| `license_key` | env `GENESIS_PRO_KEY` or `~/.genesis/license` | Pro only |
| `rules_path` | `.genesis.rules.yml` at project root | No |

### Outputs
| Output | Format | Tier |
|--------|--------|------|
| Score + breakdown | dict / CLI / JSON | Free |
| Anti-pattern report | dict / CLI / JSON | Free |
| Fragility map | dict / CLI / JSON | Free |
| Git churn report | dict / CLI / JSON | Free |
| Refactoring plan | dict / CLI / JSON | Free |
| Annotated structure | text / CLI | Free |
| Decay forecast | dict / CLI / JSON | Pro |
| Temporal scores | dict / CLI / JSON | Pro |
| Module risk rankings | dict / CLI / JSON | Pro |
| Drift report (vagrant/stale) | dict / CLI / JSON | Pro |
| Model diff | dict / CLI | Pro |
| Hotspot prescriptions | dict / CLI / JSON | Pro |
| Rules validation result | dict / CLI / JSON | Pro |
| HTML report | `.html` | Pro |

### Intermediate State (persisted to `.genesis/`)
| File | Content | Updated |
|------|---------|---------|
| `import_graph.json` | Full dependency graph | Per analysis |
| `score_history.jsonl` | Time-series score records | Per analysis |
| `git_cache_{N}d.json` | Git log cache | Per analysis (6h TTL) |
| `model.json` | Committed architecture model | On `mark_implemented` |
| `planned.json` | Planned architecture model | On agent edits |
| `source_map.json` | Responsibility → file+line | On anchor |
| `drift_state.json` | Last drift reconciliation anchor | On reconcile |
| `violations.jsonl` | Rule violation history | Per rules check |

---

## Agent 7 MCP Tools

When Genesis PRO is used as an MCP server (`genesis serve`), Agent 7 exposes:

| Tool | Description | Tier |
|------|-------------|------|
| `analyze_project` | Full analysis, returns score + anti-patterns + fragility | Free |
| `get_score` | Quick score lookup with breakdown | Free |
| `get_anti_patterns` | Anti-pattern list with severities | Free |
| `get_structure` | Annotated project structure tree | Free |
| `suggest_refactoring` | Prioritized refactoring plan | Free |
| `get_forecast` | Decay forecast with confidence intervals | Pro |
| `get_module_risks` | Per-module risk rankings | Pro |
| `get_drift` | Vagrant + stale responsibility list | Pro |
| `get_model_diff` | Planned vs. committed diff | Pro |
| `get_hotspots` | Top hotspots with prescriptions | Pro |
| `check_rules` | Evaluate `.genesis.rules.yml` assertions | Pro |
| `suggest_rules` | Recommend new governance rules from history | Pro |
| `mark_implemented` | Fold planned node into committed | Pro |
| `anchor_responsibility` | Map responsibility to file+line | Pro |
| `flag_drift` | Mark responsibility as vagrant or stale | Pro |
| `reconcile_drift` | Advance drift anchor after review | Pro |

---

## Agent 7 Quality Gates

Before producing any output, Agent 7 enforces:

1. **Minimum data quality:** refuses to produce forecasts with < 3 history entries; uses `confidence < 0.2` warning instead
2. **Confidence floor:** any output with `confidence < 0.3` is labeled `LOW CONFIDENCE` in CLI and HTML
3. **Stale graph detection:** warns if `import_graph.json` is > 24 hours old
4. **Git repo check:** gracefully degrades temporal features if not in a git repo
5. **License gate:** Pro features return `ProFeatureError` with upgrade message if key is invalid

---

## Agent 7 Self-Improvement Loop

After each analysis run:
1. Append to `score_history.jsonl`
2. Append violations to `violations.jsonl`
3. If ≥ 5 analyses in history: run `rules_suggester.py`
4. If suggestions exist: append to `.genesis/rule_suggestions.json`
5. CLI displays: "Agent 7 has 3 new rule suggestions. Run `genesis suggest` to review."

---

## Agent 7 Integration Points

### With Claude Code (MCP)
- Agent 7 runs as MCP server: `genesis serve --mcp`
- Claude Code calls tools directly (no subprocess)
- Session state maintained across tool calls via `active_project` in server state

### With GitHub Actions
- `genesis-check.yml` installs Python, runs `genesis check`, posts result to PR
- Failure message links to full HTML report artifact

### With Pre-commit
- `genesis hook install [path]` writes `.git/hooks/pre-commit`
- Hook calls `genesis check --staged-only --fast` (< 5 second target)

### With VSCode (future)
- Language server protocol adapter over genesis JSON output
- Inline anti-pattern annotations
- Score status bar item

---

## Agent 7 Error Handling Contract

| Error Condition | Behavior |
|----------------|----------|
| Project not found | `sys.exit(1)` with clear path message |
| Not a git repo | Degrades: skip temporal + git features, warn |
| Git timeout (> 30s) | Use cached data if available, warn if not |
| Import graph build failure | Partial results with `partial: true` flag |
| LLM context overflow | Prompt budget manager truncates automatically |
| Invalid license | Pro features disabled, clear upgrade message |
| Rules file invalid YAML | Detailed parse error with line number |
| Forecast insufficient data | Returns `None`, does not crash |
| Source anchor invalid path | Validation error per anchor, skip invalid |
