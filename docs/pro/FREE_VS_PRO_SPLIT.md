# Genesis — Free vs. Pro Feature Split
<!-- Updated after architect/scryer audit — 2026-06-27 -->

## Design Principle

**Free** = enough to be genuinely useful and shareable, creates a pull into Pro.
**Pro** = the layer that makes Genesis irreplaceable for teams and enterprises.

The split is not artificial. Free delivers static analysis + basic reporting. Pro delivers temporal intelligence, living architecture models, and automated governance.

---

## Free Tier

### Analysis
- Import graph construction (Python, TypeScript, JavaScript)
- Cycle detection
- Layer classification (5 layers: API, Service, Data, UI, Infrastructure)
- Dead code detection (fan-in=0 modules)
- Module boundary mapping

### Scoring
- 4-metric architecture score (modularity, coupling, cohesion, layering)
- Adaptive scoring profiles (6 profiles: default, frontend-spa, backend-monolith, microservices, data-pipeline, library)
- Score history persistence (.genesis/score_history.jsonl)
- Score label (EXCELLENT / GOOD / FAIR / POOR / CRITICAL)
- Basic trend arrow (up/down from previous run)

### Anti-Pattern Detection (all 7 detectors)
- God Class (excessive fan-out)
- Hub File (excessive fan-in)
- Circular Dependency (DFS cycle detection)
- Dead Code (orphan modules)
- Feature Envy (>65% imports from one module)
- Leaky Abstraction (layer violation)
- Shotgun Surgery (small utility imported by many)

### Fragility Classification
- STABLE / FRAGILE / VOLATILE per module
- Combines anti-patterns + churn + test-coverage proxy

### Git Analysis (basic)
- Per-file commit count
- Fix-commit ratio
- Last-touched date
- Churn level: HIGH / MEDIUM / LOW / STALE

### Reporting
- CLI text report (colored, structured)
- JSON output (`--json` flag)
- **NEW (Free):** Annotated project structure scanner (manifest/infra/env file callouts)
- **NEW (Free):** Bus factor per file (distinct authors)
- **NEW (Free):** Weekly commit timeline (week-by-week snapshot)
- **NEW (Free):** Score sparkline (ASCII trend in CLI)
- **NEW (Free):** Python stdlib filter (complete, 100+ names)

### Refactoring Planner (basic)
- 5 built-in rules (hub-splitter, god-class-splitter, cycle-breaker, dead-code, layer-fix)
- Operations list per step (CREATE / MODIFY / DELETE / MOVE)
- Estimated complexity (LOW / MEDIUM / HIGH)

### C4 Generation
- Mermaid diagrams from evidence.json (L1 Context, L2 Container, L3 Component)
- No source anchoring (Free)

### CLI
- `genesis score [path]`
- `genesis analyze [path]`
- `genesis refactor [path] --plan`
- `genesis git [path]`
- `genesis c4 [path]`
- `genesis structure [path]` **NEW**

### Infrastructure
- Zero external runtime dependencies (stdlib-only Python)
- Pre-commit hook (generic, fail-on-CRITICAL)
- GitHub Actions CI job (basic — run and report score)

---

## Pro Tier

All Free features plus:

### Architecture Model (Living Specification)
- **Dual-layer model:** planned (`.genesis/planned.json`) vs. committed (`model.json`)
- **Model diff engine:** typed diff (Added / Deleted / Moved / Reworded / MembersChanged) between any two model states
- **Stable element IDs:** reparent = `Moved`, not delete+add
- **C4 model data structure:** Person → System → Container → Component → Symbol + links + groups
- **Source map:** symbol/responsibility → file + line range anchoring
- **Drift flags:** `vagrant` (code-discovered, awaiting verdict) and `stale` (committed claim, code no longer backs it)
- **Reconcile drift:** advance drift anchor after review; fingerprint prevents re-surfacing

### Temporal Intelligence
- **WLS Decay Regressor:** weighted least-squares regression, exponential recency weights (half-life: 8 weeks), R², t-statistic, 95% confidence intervals
- **Score trajectory:** per-week predictions with lowerBound / upperBound / confidence
- **Threshold crossing prediction:** weeks until score crosses critical threshold (default: 40/100)
- **Temporal Scorer:** static score adjusted by churn trend + commit acceleration velocity
- **ForecastV2:** per-module risk classification (low / medium / high / critical) with actionable recommendations
- **Module-level decay rankings:** worst-declining modules, predicted scores at 4 / 8 / 12 weeks

### Confidence Layer
- **Confidence annotations on every output:** `confidence: float`, `basis: str` on every score, anti-pattern, forecast, and recommendation
- **R² quality indicator** on all regression-based predictions
- **Signal count** (how many data points back each finding)

### Hotspot Intelligence
- **Active hotspot warnings with prescriptive actions:** top 3 hotspots with specific refactor recommendation + estimated score delta
- **Change coupling detection:** file-pair co-change analysis with confidence (`cochangeCount / maxCommits`), top 50 pairs
- **Module-level coupling:** which modules co-evolve (not just files)
- **Predictive coupling:** if file A changed and A+B always change together, flag B for review

### Architecture Regression Test DSL
- **`.genesis.rules.yml` extended DSL:**
  ```yaml
  assert:
    score_above: 70
    no_circular_deps: true
    bus_factor_min: 2
    coupling_below: 0.3
    score_not_declining_over: 4_weeks
    no_anti_pattern: [God Class, Shotgun Surgery]
    banned_imports: [legacy/*, v1/*]
  thresholds:
    max_critical_anti_patterns: 0
    max_high_anti_patterns: 3
  ```
- **Temporal assertions:** `score_not_declining_over`, `churn_below_over`
- **Per-module overrides:** different rules for different paths

### Prompt Budget Manager
- Operation classification: `core-target` (always full), `important-context` (if budget), `consumer-ref` (abbreviated)
- File abbreviation: first 20 lines + exported interfaces + last 5 lines
- Model-specific token budgets (Claude: 60k, GPT-4: 30k, Gemini: 40k, fallback: 8k)
- Token estimation (1 token / 4 chars)
- Directive for LLM to return each file in separate code blocks

### Partial Re-analysis Scoping
- `compute_affected_scope(step)` → `{changed_files, consumer_files}`
- Re-analysis after refactor step limited to affected scope only
- Pre-built `DependencyIndex` (`incomingByFile`, `outgoingByFile`) for O(1) lookups

### Cycle Breaking Intelligence
- For each detected cycle: propose minimal interface extraction
- Identify lowest-dependency cycle member as extraction candidate
- Generate specific interface name and placement suggestion

### Refactoring (Pro-level)
- **Human gate:** interactive approval per step (colored ANSI, rationale displayed, auto-mode flag)
- **Offline prompt generator:** generate refactoring prompts for export/offline use
- **Score estimation after applying all steps:** pre-compute expected score before committing
- **Plugin custom refactoring rules:** register external rule classes

### Reporting
- **HTML self-contained reporter:** single `.html` file with inline CSS/JS, sections: header, overview, score, anti-patterns, layers, refactoring-plan, suggestions, forecast
- **Architecture velocity dashboard:** score per week per module, churn trends, anti-pattern evolution, bus factor, predicted score with confidence bands
- **Benchmark comparison:** run against known OSS projects (axios, flask, fastapi, requests) to validate score calibration

### CI / CD Integration
- **GitHub Actions adapter (Pro):** fail PR on rules violation; post report as PR comment; `genesis-check.yml` workflow template
- **Pre-commit boundary enforcement (Pro):** project-specific hook, staged-files-only analysis, specific rule + file in error message
- **Docker image:** `genesis-pro:latest` for hermetic CI runs

### Git Analysis (Pro)
- **Git cache layer:** persistent cache keyed by `(projectPath, dateRange, fileHash)`; invalidates only changed files' descendants
- **Co-change confidence matrix:** full pairwise confidence table exportable as JSON / CSV

### Knowledge Base (Pro)
- **Violation persistence:** store every rule violation with timestamp, severity, file
- **Self-improving suggestions:** after N analyses, suggest tightening rules based on patterns
- **Cross-project benchmarking:** compare project score against anonymized Pro user aggregate

### Agent Generation (Pro)
- Generated `.agent/` directory with role-specific markdown agents (orchestrator, QA, security, backend, tech-debt controller)
- Pre-built templates: ADR, BDD, C4, TDD, Threat Model
- Hooks: pre-commit, pre-push, post-analysis
- Quality gate guard configuration

---

## License Gate

Removed. There is no license gate — `license.py` was deleted and every Pro
feature runs unconditionally, same as Free. The Free/Pro split above now
describes packaging (`genesis-architect` vs. `genesis-architect-pro`), not
an access boundary.
