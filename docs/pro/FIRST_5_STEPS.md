# Genesis PRO — First 5 Implementation Steps
<!-- Exact specifications. No code written until approved. -->
<!-- Date: 2026-06-27 -->

Each step is atomic and independently testable. Steps are ordered so later steps build on earlier ones but never require them for their own tests to pass.

---

## Step 1: Python Stdlib Filter + Bus Factor + Weekly Timeline

**What:** Three small additions to `import_graph.py` and `git_analyzer.py` that have zero dependencies and unblock everything else.

**Files changed:**
- `src/genesis_architect_pro/import_graph.py` — add stdlib filter
- `src/genesis_architect_pro/git_analyzer.py` — add bus factor + weekly timeline

**Exact changes:**

### 1a. `import_graph.py` — Python Stdlib Filter

Add at module level:
```python
PYTHON_STDLIB: frozenset[str] = frozenset({
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio", "asyncore",
    "atexit", "base64", "bdb", "binascii", "bisect", "builtins", "bz2",
    "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs",
    "codeop", "collections", "colorsys", "compileall", "concurrent", "configparser",
    "contextlib", "contextvars", "copy", "copyreg", "csv", "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis", "distutils",
    "doctest", "email", "encodings", "enum", "errno", "faulthandler", "fcntl",
    "filecmp", "fileinput", "fnmatch", "fractions", "ftplib", "functools", "gc",
    "getopt", "getpass", "gettext", "glob", "grp", "gzip", "hashlib", "heapq",
    "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "importlib",
    "inspect", "io", "ipaddress", "itertools", "json", "keyword", "linecache",
    "locale", "logging", "lzma", "mailbox", "marshal", "math", "mimetypes",
    "mmap", "multiprocessing", "netrc", "numbers", "operator", "os", "pathlib",
    "pdb", "pickle", "pkgutil", "platform", "pprint", "profile", "pty",
    "pwd", "queue", "random", "re", "readline", "resource", "runpy",
    "sched", "secrets", "select", "shelve", "shlex", "shutil", "signal",
    "site", "smtplib", "socket", "socketserver", "sqlite3", "ssl", "stat",
    "statistics", "string", "struct", "subprocess", "sys", "sysconfig",
    "tarfile", "tempfile", "textwrap", "threading", "time", "timeit",
    "tkinter", "token", "tokenize", "tomllib", "trace", "traceback",
    "tracemalloc", "types", "typing", "unicodedata", "unittest", "urllib",
    "uuid", "venv", "warnings", "wave", "weakref", "webbrowser", "xml",
    "xmlrpc", "zipfile", "zipimport", "zlib", "_thread",
    # Python 3.11+ additions
    "tomllib", "zoneinfo",
})

def is_stdlib_import(module_name: str) -> bool:
    """Return True if module_name is a Python standard library module."""
    top_level = module_name.split(".")[0]
    return top_level in PYTHON_STDLIB
```

Apply in `_parse_python_imports()` (wherever Python imports are extracted from AST):
```python
# Filter out stdlib imports
imports = [m for m in raw_imports if not is_stdlib_import(m)]
```

### 1b. `git_analyzer.py` — Bus Factor

In `_git_log()`, capture author alongside commit hash and subject.
Change `--format=%H|%s` to `--format=%H|%an|%s` and update parser.

In `per_module_churn()`:
- Change `file_fix_commits` to also track `file_authors: dict[str, set[str]]`
- In result dict per file, add:
  ```python
  "authors": sorted(file_authors.get(rel_path, set())),
  "bus_factor": len(file_authors.get(rel_path, set())),
  ```

### 1c. `git_analyzer.py` — Weekly Timeline

Add `WeeklySnapshot` dataclass:
```python
@dataclass
class WeeklySnapshot:
    week_start: str   # ISO date of Monday
    commits: int
    churn_lines: int  # additions + deletions (requires --numstat)
    active_files: int
```

Add `build_timeline(commits: list[dict], period_weeks: int = 12) -> list[WeeklySnapshot]`:
- `_to_monday(dt: datetime) -> str` — normalize to ISO date of that week's Monday
- Fill all `period_weeks` weeks with zero-entries; overwrite with real data
- Sort ascending by `week_start`

Add `render_sparkline(snapshots: list[WeeklySnapshot], metric: str = "commits", width: int = 20) -> str`:
- Normalize `metric` values to 0–8 range
- Characters: ` ▁▂▃▄▅▆▇█`
- Returns single-line string like `▁▁▂▃▄▄▇█▅▃▁▁`

**Note:** Weekly timeline requires `--numstat` in `git log`. Update `_git_log()` to add `--numstat` and parse additions/deletions per file. Parser must handle the numstat format (`N\tM\tfilename`).

---

**Tests for Step 1:**

File: `tests/test_stdlib_filter.py`
```python
def test_os_is_stdlib():
    assert is_stdlib_import("os") is True

def test_os_path_is_stdlib():
    assert is_stdlib_import("os.path") is True

def test_requests_is_not_stdlib():
    assert is_stdlib_import("requests") is False

def test_numpy_is_not_stdlib():
    assert is_stdlib_import("numpy") is False

def test_typing_is_stdlib():
    assert is_stdlib_import("typing") is True

def test_tomllib_is_stdlib():
    assert is_stdlib_import("tomllib") is True

def test_empty_string_is_not_stdlib():
    assert is_stdlib_import("") is False
```

File: `tests/test_bus_factor.py`
```python
def test_single_author_bus_factor_one(tmp_path):
    # Commit all files from one author → bus_factor=1 for each file
    ...

def test_two_authors_bus_factor_two(tmp_path):
    # Two different authors commit same file → bus_factor=2
    ...

def test_bus_factor_in_output_dict(tmp_path):
    result = per_module_churn(tmp_path)
    for file_data in result.values():
        assert "bus_factor" in file_data
        assert isinstance(file_data["bus_factor"], int)
        assert file_data["bus_factor"] >= 1

def test_authors_list_sorted(tmp_path):
    result = per_module_churn(tmp_path)
    for file_data in result.values():
        assert file_data["authors"] == sorted(file_data["authors"])
```

File: `tests/test_weekly_timeline.py`
```python
def test_timeline_has_all_weeks():
    snapshots = build_timeline(commits=[], period_weeks=4)
    assert len(snapshots) == 4

def test_timeline_sorted_ascending():
    snapshots = build_timeline(commits=[], period_weeks=4)
    dates = [s.week_start for s in snapshots]
    assert dates == sorted(dates)

def test_timeline_fills_zero_weeks():
    snapshots = build_timeline(commits=[], period_weeks=4)
    assert all(s.commits == 0 for s in snapshots)

def test_sparkline_length_matches_width():
    snapshots = [WeeklySnapshot(f"2026-0{i}-01", i, i*10, i) for i in range(1, 9)]
    line = render_sparkline(snapshots, width=8)
    assert len(line) == 8

def test_sparkline_uses_block_chars():
    snapshots = [WeeklySnapshot("2026-01-01", 5, 50, 5)]
    line = render_sparkline(snapshots, width=1)
    assert line in " ▁▂▃▄▅▆▇█"
```

---

## Step 2: Confidence Annotations on Every Output

**What:** Add `confidence: float` and `basis: str` to every analysis output. No new analysis logic — retrofit existing outputs.

**Files changed:**
- `src/genesis_architect_pro/antipattern_detector.py`
- `src/genesis_architect_pro/architecture_scorer.py`
- `src/genesis_architect_pro/refactoring_planner.py`

**Exact changes:**

### 2a. `AntiPattern` dataclass — add fields

```python
@dataclass
class AntiPattern:
    id: str
    type: str
    severity: str
    file: str
    description: str
    metrics: dict = field(default_factory=dict)
    affected_modules: list[str] = field(default_factory=list)
    suggested_fix: str = ""
    confidence: float = 1.0      # NEW: 0.0–1.0
    basis: str = ""              # NEW: human-readable explanation
```

### 2b. Confidence computation per detector

Add `_compute_antipattern_confidence(detector_type: str, metrics: dict) -> tuple[float, str]`:
```python
def _compute_antipattern_confidence(detector_type: str, metrics: dict) -> tuple[float, str]:
    """Returns (confidence, basis) for a detected anti-pattern."""
    if detector_type == "god-class":
        fan_out = metrics.get("fan_out", 0)
        threshold = metrics.get("threshold", 15)
        excess = fan_out - threshold
        confidence = min(1.0, 0.6 + (excess / threshold) * 0.4)
        basis = f"fan_out={fan_out}, threshold={threshold}, excess={excess}"

    elif detector_type == "circular-dep":
        length = metrics.get("cycle_length", 2)
        # Shorter cycles are more certain (direct A→B→A is unambiguous)
        confidence = 1.0 if length == 2 else 0.9
        basis = f"cycle_length={length}"

    elif detector_type == "dead-code":
        lines = metrics.get("lines", 0)
        # Larger dead files are more concerning but also more likely to be dynamic imports
        confidence = 0.6 if lines > 100 else 0.8
        basis = f"fan_in=0, lines={lines}, may be dynamically imported"

    elif detector_type in ("feature-envy", "shotgun-surgery", "hub-file", "leaky-abstraction"):
        confidence = 0.85
        basis = f"static graph analysis: {metrics}"

    else:
        confidence = 0.75
        basis = "static graph analysis"

    return round(confidence, 2), basis
```

Apply in each detector: after creating `AntiPattern`, set `confidence, basis = _compute_antipattern_confidence(type, metrics)`.

### 2c. `architecture_scorer.py` — add confidence to result dict

Add `_compute_score_confidence(module_count: int, cycle_count: int, history_entries: int) -> tuple[float, str]`:
```python
def _compute_score_confidence(module_count: int, cycle_count: int, history_entries: int) -> tuple[float, str]:
    base = 0.7
    # More modules → more representative
    if module_count >= 20: base += 0.1
    if module_count >= 50: base += 0.1
    # No history → lower confidence in trend
    if history_entries == 0: base -= 0.1
    basis = f"{module_count} modules analyzed"
    if history_entries > 0:
        basis += f", {history_entries} historical runs"
    return round(min(1.0, max(0.1, base)), 2), basis
```

Add `confidence` and `basis` keys to result dict returned by `score_project()`.

### 2d. `refactoring_planner.py` — add confidence to each step

Each `RefactoringStep` gets:
```python
confidence: float = 0.8
basis: str = ""
```
Set based on the anti-pattern severity that triggered the step: CRITICAL → 0.95, HIGH → 0.85, MEDIUM → 0.75, LOW → 0.60.

---

**Tests for Step 2:**

File: `tests/test_confidence_annotations.py`
```python
def test_antipattern_has_confidence_field(tmp_path):
    report = detect_all(tmp_path)
    for pattern in report.patterns:
        assert hasattr(pattern, "confidence")
        assert 0.0 <= pattern.confidence <= 1.0

def test_antipattern_has_basis_field(tmp_path):
    report = detect_all(tmp_path)
    for pattern in report.patterns:
        assert hasattr(pattern, "basis")
        assert isinstance(pattern.basis, str)

def test_circular_dep_confidence_is_1(tmp_path):
    # Create A→B→A cycle
    # detect → find circular dep
    # Assert confidence == 1.0 for 2-node cycle
    ...

def test_dead_code_confidence_below_circular(tmp_path):
    # dead code confidence < 1.0 (dynamic import uncertainty)
    ...

def test_score_result_has_confidence():
    result = score_project(".")
    assert "confidence" in result
    assert "basis" in result
    assert 0.0 <= result["confidence"] <= 1.0

def test_confidence_higher_with_more_modules(tmp_path):
    # Create project with 50+ modules
    # Score it, assert confidence > score of 5-module project
    ...

def test_refactoring_step_has_confidence():
    plan = generate_plan(".")
    for step in plan.steps:
        assert hasattr(step, "confidence")
        assert 0.0 <= step.confidence <= 1.0

def test_critical_antipattern_step_high_confidence():
    # Ensure CRITICAL-severity trigger → step confidence >= 0.9
    ...
```

---

## Step 3: DependencyIndex + Partial Re-analysis Scoping

**What:** Pre-compute O(1) lookup maps so all rules run faster; compute affected scope after a refactor step.

**Files changed:**
- `src/genesis_architect_pro/import_graph.py` — add `DependencyIndex`, `build_dependency_index()`
- `src/genesis_architect_pro/refactoring_planner.py` — pre-build index, pass to rules; add `compute_affected_scope()`

**Exact changes:**

### 3a. `import_graph.py` — DependencyIndex

```python
from dataclasses import dataclass, field

@dataclass
class DependencyIndex:
    """Pre-computed O(1) lookup maps for the dependency graph."""
    # file → set of files that import it (incoming edges)
    incoming: dict[str, set[str]] = field(default_factory=dict)
    # file → set of files it imports (outgoing edges)
    outgoing: dict[str, set[str]] = field(default_factory=dict)

def build_dependency_index(modules: dict) -> DependencyIndex:
    """
    Build incoming and outgoing edge maps in a single O(E) pass.

    modules: dict from import_graph.json, each entry has "imports" list.
    """
    incoming: dict[str, set[str]] = {}
    outgoing: dict[str, set[str]] = {}

    for mod, data in modules.items():
        imports = data.get("imports", [])
        outgoing[mod] = set(imports)
        for dep in imports:
            if dep not in incoming:
                incoming[dep] = set()
            incoming[dep].add(mod)

    return DependencyIndex(incoming=incoming, outgoing=outgoing)
```

### 3b. `refactoring_planner.py` — AffectedScope

```python
from dataclasses import dataclass

@dataclass
class AffectedScope:
    """Files directly affected by a refactoring step + their importers."""
    changed_files: list[str]
    consumer_files: list[str]

def compute_affected_scope(step: RefactoringStep, index: DependencyIndex) -> AffectedScope:
    """
    Compute the minimal set of files to re-analyze after applying a step.

    changed_files: files created/modified/deleted/moved by this step
    consumer_files: files that import any changed file (one hop)
    """
    changed: set[str] = set()
    for op in step.operations:
        changed.add(op["path"])
        if op.get("new_path"):
            changed.add(op["new_path"])

    consumers: set[str] = set()
    for f in changed:
        for importer in index.incoming.get(f, set()):
            if importer not in changed:
                consumers.add(importer)

    return AffectedScope(
        changed_files=sorted(changed),
        consumer_files=sorted(consumers),
    )
```

Update `generate_plan()` to:
1. Build `DependencyIndex` before running rules
2. Store index on plan result: `plan.index = index`
3. Pass index to each rule's `analyze()` call (rules that currently do O(E) scans use index instead)

---

**Tests for Step 3:**

File: `tests/test_dependency_index.py`
```python
def test_build_index_incoming_edges():
    modules = {
        "a": {"imports": ["b", "c"]},
        "b": {"imports": []},
        "c": {"imports": []},
    }
    idx = build_dependency_index(modules)
    assert "a" in idx.incoming.get("b", set())
    assert "a" in idx.incoming.get("c", set())

def test_build_index_outgoing_edges():
    modules = {"a": {"imports": ["b"]}, "b": {"imports": []}}
    idx = build_dependency_index(modules)
    assert idx.outgoing["a"] == {"b"}
    assert idx.outgoing["b"] == set()

def test_build_index_empty_modules():
    idx = build_dependency_index({})
    assert idx.incoming == {}
    assert idx.outgoing == {}

def test_build_index_single_pass():
    # Verify O(E) behavior: no quadratic scanning
    # Build large graph, assert index.incoming[x] correct for all x
    modules = {f"m{i}": {"imports": [f"m{i-1}"]} for i in range(1, 101)}
    modules["m0"] = {"imports": []}
    idx = build_dependency_index(modules)
    assert len(idx.incoming) == 100
```

File: `tests/test_affected_scope.py`
```python
def test_affected_scope_includes_changed_file():
    step = make_step(operations=[{"type": "MODIFY", "path": "src/a.py"}])
    idx = make_index({"src/b.py": {"imports": ["src/a.py"]}})
    scope = compute_affected_scope(step, idx)
    assert "src/a.py" in scope.changed_files

def test_affected_scope_includes_consumers():
    step = make_step(operations=[{"type": "MODIFY", "path": "src/a.py"}])
    idx = build_dependency_index({
        "src/b.py": {"imports": ["src/a.py"]},
        "src/c.py": {"imports": ["src/a.py"]},
    })
    scope = compute_affected_scope(step, idx)
    assert "src/b.py" in scope.consumer_files
    assert "src/c.py" in scope.consumer_files

def test_affected_scope_excludes_unrelated():
    step = make_step(operations=[{"type": "MODIFY", "path": "src/a.py"}])
    idx = build_dependency_index({
        "src/b.py": {"imports": ["src/a.py"]},
        "src/z.py": {"imports": ["src/y.py"]},
    })
    scope = compute_affected_scope(step, idx)
    assert "src/z.py" not in scope.consumer_files
    assert "src/y.py" not in scope.consumer_files

def test_affected_scope_move_op_includes_new_path():
    step = make_step(operations=[{
        "type": "MOVE", "path": "src/a.py", "new_path": "src/auth/a.py"
    }])
    idx = build_dependency_index({})
    scope = compute_affected_scope(step, idx)
    assert "src/a.py" in scope.changed_files
    assert "src/auth/a.py" in scope.changed_files

def test_consumer_is_not_counted_as_changed():
    step = make_step(operations=[{"type": "MODIFY", "path": "src/a.py"}])
    idx = build_dependency_index({"src/b.py": {"imports": ["src/a.py"]}})
    scope = compute_affected_scope(step, idx)
    assert "src/b.py" not in scope.changed_files
    assert "src/b.py" in scope.consumer_files
```

---

## Step 4: WLS Decay Regressor with Confidence Intervals

**What:** New module implementing weighted least-squares regression on score history. The statistical backbone for all temporal intelligence.

**Files changed:**
- `src/genesis_architect_pro/decay_regressor.py` — new module
- `src/genesis_architect_pro/architecture_scorer.py` — call regressor in `print_score_report()` when history ≥ 3

**Module: `decay_regressor.py`**

Full specification (implement exactly as designed):

```python
"""
decay_regressor.py - Genesis Architect PRO

Weighted least-squares regression on architecture score history.
Predicts future score decay with confidence intervals.

Algorithm:
  1. Load score history (week_offset, score) pairs
  2. Apply exponential recency weights (half-life: 8 weeks)
  3. Fit weighted linear regression (WLS)
  4. Compute R², t-statistic, 95% confidence intervals
  5. Generate trajectory (per-week predictions)
  6. Predict weeks until score crosses critical threshold

All math uses only Python stdlib (no numpy/scipy).
"""

import math
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone

# Configuration defaults
DEFAULT_RECENCY_HALF_LIFE = 8      # weeks
DEFAULT_HORIZON_WEEKS = 12
DEFAULT_CRITICAL_THRESHOLD = 40
DEFAULT_MIN_DATA_POINTS = 3
```

Key dataclasses and their fields (all as specified in roadmap item 1.4):
- `ScoreDataPoint(week_offset, score, weight=None)`
- `RegressionResult(slope, intercept, r_squared, data_points, slope_std_error, is_significant)`
- `ScorePrediction(week_offset, predicted_score, lower_bound, upper_bound, confidence)`
- `DecayForecast(current_score, predicted_score, score_delta, weekly_delta, weeks_to_threshold, threshold, confidence, regression, trajectory, summary)`

`DecayRegressor` class with methods:
- `apply_weights(data)` — exponential decay: `weight = exp(-ln2/half_life × (max_week - week))`
- `fit_weighted_regression(data)` — WLS with det check, R², t-statistic
- `generate_trajectory(regression, start_week, end_week)` — confidence decays as `r² × exp(-0.1 × distance)`
- `_compute_weeks_to_threshold(regression, last_week, current_score)` — linear crossing: `(threshold - intercept) / slope`; Infinity if slope ≥ 0
- `_compute_overall_confidence(regression, n_points)` — base=R², bonus for data count, penalty for non-significance
- `forecast(data) -> DecayForecast | None` — full pipeline
- `_clamp_score(x) -> float` — `max(0, min(100, round(x, 1)))`

Convenience function:
```python
def forecast_from_history(history: list[dict], config=None) -> DecayForecast | None:
    """Load from score_history.jsonl records and run forecast."""
    # Convert records to ScoreDataPoint using timestamp → week_offset
    # Call DecayRegressor.forecast()
```

---

**Tests for Step 4:**

File: `tests/test_decay_regressor.py`
```python
def test_apply_weights_most_recent_highest():
    data = [
        ScoreDataPoint(week_offset=0, score=80),
        ScoreDataPoint(week_offset=4, score=75),
        ScoreDataPoint(week_offset=8, score=70),
    ]
    reg = DecayRegressor()
    weighted = reg.apply_weights(data)
    # Most recent (week_offset=8) should have weight=1.0
    assert weighted[-1].weight == pytest.approx(1.0, abs=0.01)
    assert weighted[0].weight < weighted[1].weight < weighted[2].weight

def test_fit_regression_known_linear():
    # Perfect linear data: score = -1 × week + 80
    data = [ScoreDataPoint(i, 80 - i, 1.0) for i in range(10)]
    reg = DecayRegressor()
    result = reg.fit_weighted_regression(data)
    assert result.slope == pytest.approx(-1.0, abs=0.01)
    assert result.intercept == pytest.approx(80.0, abs=0.1)
    assert result.r_squared == pytest.approx(1.0, abs=0.001)

def test_r_squared_perfect_fit():
    data = [ScoreDataPoint(i, 70.0, 1.0) for i in range(5)]  # flat line
    reg = DecayRegressor()
    result = reg.fit_weighted_regression(data)
    assert result.r_squared == pytest.approx(1.0, abs=0.01)

def test_t_statistic_significant_decline():
    # Strong negative trend → significant
    data = [ScoreDataPoint(i, 80 - i * 3, 1.0) for i in range(8)]
    reg = DecayRegressor()
    result = reg.fit_weighted_regression(data)
    assert result.is_significant is True

def test_t_statistic_noise_not_significant():
    import random
    random.seed(42)
    data = [ScoreDataPoint(i, 70 + random.uniform(-1, 1), 1.0) for i in range(5)]
    reg = DecayRegressor()
    result = reg.fit_weighted_regression(data)
    assert result.is_significant is False

def test_confidence_intervals_widen_with_distance():
    data = [ScoreDataPoint(i, 80 - i, 1.0) for i in range(8)]
    reg = DecayRegressor()
    regression = reg.fit_weighted_regression(data)
    trajectory = reg.generate_trajectory(regression, start_week=7, end_week=19)
    widths = [(p.upper_bound - p.lower_bound) for p in trajectory]
    # Width should increase (or stay equal) as we project further
    assert all(widths[i] <= widths[i+1] for i in range(len(widths)-1))

def test_threshold_crossing_negative_slope():
    # slope=-2/week, current=80, threshold=40 → 20 weeks
    data = [ScoreDataPoint(i, 80 - i * 2, 1.0) for i in range(5)]
    reg = DecayRegressor()
    forecast = reg.forecast(data)
    assert forecast is not None
    assert forecast.weeks_to_threshold < math.inf

def test_threshold_crossing_stable_returns_infinity():
    data = [ScoreDataPoint(i, 75.0, 1.0) for i in range(5)]
    reg = DecayRegressor()
    forecast = reg.forecast(data)
    assert forecast is not None
    assert forecast.weeks_to_threshold == math.inf

def test_forecast_returns_none_insufficient_data():
    data = [ScoreDataPoint(0, 80, 1.0), ScoreDataPoint(1, 79, 1.0)]
    reg = DecayRegressor(config=DecayRegressorConfig(min_data_points=3))
    assert reg.forecast(data) is None

def test_forecast_summary_is_human_readable():
    data = [ScoreDataPoint(i, 80 - i, 1.0) for i in range(8)]
    reg = DecayRegressor()
    forecast = reg.forecast(data)
    assert forecast is not None
    assert isinstance(forecast.summary, str)
    assert len(forecast.summary) > 20

def test_clamp_score_bounds():
    reg = DecayRegressor()
    assert reg._clamp_score(-5) == 0.0
    assert reg._clamp_score(105) == 100.0
    assert reg._clamp_score(75.5) == 75.5
```

---

## Step 5: Dual-Layer Model Store (planned vs. committed)

**What:** New module that implements the planned/committed architecture model split. This is the architectural foundation for all design-first features.

**Files changed:**
- `src/genesis_architect_pro/model_store.py` — new module

**Module: `model_store.py`**

```python
"""
model_store.py - Genesis Architect PRO

Dual-layer architecture model: planned vs. committed.

  committed (model.json):   verified architecture — code backs every claim
  planned (planned.json):   intent — what we will build; not yet in code

The two layers diverge when the agent or user proposes architecture changes.
mark_implemented() folds planned nodes into committed once code backs them.

All persistence is in .genesis/ at the project root.
"""
```

Exact dataclass structure:
```python
@dataclass
class ModelResponsibility:
    id: str
    statement: str
    vagrant: bool = False     # discovered in code, awaiting user verdict
    stale: bool = False       # committed claim, code no longer backs it
    last_touched_at: str | None = None  # ISO datetime

@dataclass
class ModelNode:
    id: str
    kind: str                 # person | system | container | component | symbol
    name: str
    parent_id: str | None = None
    technology: str | None = None
    description: str | None = None
    responsibilities: list[ModelResponsibility] = field(default_factory=list)
    external: bool = False
    vagrant: bool = False

@dataclass
class ModelLink:
    id: str
    src: str
    dst: str
    label: str = ""
    method: str | None = None

@dataclass
class ModelGroup:
    id: str
    name: str
    member_ids: list[str] = field(default_factory=list)
    description: str | None = None
    responsibilities: list[ModelResponsibility] = field(default_factory=list)

@dataclass
class ArchModel:
    nodes: list[ModelNode] = field(default_factory=list)
    links: list[ModelLink] = field(default_factory=list)
    groups: list[ModelGroup] = field(default_factory=list)
    source_map: dict[str, list[dict]] = field(default_factory=dict)
    # source_map: {responsibility_id: [{pattern, line, end_line, symbol}]}
    version: str = "1"
```

`ModelStore` class:
```python
class ModelStore:
    def __init__(self, project_path: Path):
        self.genesis_dir = project_path / ".genesis"
        self.committed_path = self.genesis_dir / "model.json"
        self.planned_path = self.genesis_dir / "planned.json"

    def load_committed(self) -> ArchModel: ...
    def load_planned(self) -> ArchModel: ...
    def save_committed(self, model: ArchModel) -> None: ...
    def save_planned(self, model: ArchModel) -> None: ...

    def mark_implemented(self, node_ids: list[str]) -> None:
        """
        Fold the specified nodes from planned into committed.

        For each node_id in node_ids:
          1. Find node in planned
          2. If node exists in committed: merge responsibilities (add new, keep existing)
          3. If node not in committed: add it wholesale
          4. Copy source_map entries for affected responsibilities
        """
        ...

    def is_planned_diverged(self) -> bool:
        """True when planned.json differs from model.json in any meaningful way."""
        ...

    def _to_dict(self, model: ArchModel) -> dict: ...
    def _from_dict(self, data: dict) -> ArchModel: ...
```

Implementation rules:
- `load_committed()` returns empty `ArchModel()` if `model.json` does not exist (first run)
- `load_planned()` returns `load_committed()` if `planned.json` does not exist (no divergence yet)
- `save_*` creates `.genesis/` if it does not exist
- `mark_implemented()` modifies both committed and planned: removes fulfilled nodes from planned after merging into committed
- `is_planned_diverged()` compares node/link/group IDs + responsibility statements (not full deep equality — just structural divergence check)
- All persistence uses `json.dumps(indent=2)` for human-readable files
- `version` field: if loaded JSON has different version, warn but do not crash

---

**Tests for Step 5:**

File: `tests/test_model_store.py`
```python
def test_load_committed_empty_if_missing(tmp_path):
    store = ModelStore(tmp_path)
    model = store.load_committed()
    assert isinstance(model, ArchModel)
    assert model.nodes == []
    assert model.links == []

def test_load_planned_returns_committed_when_no_planned(tmp_path):
    store = ModelStore(tmp_path)
    committed = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
    store.save_committed(committed)
    planned = store.load_planned()
    assert len(planned.nodes) == 1
    assert planned.nodes[0].id == "n1"

def test_save_and_load_roundtrip(tmp_path):
    store = ModelStore(tmp_path)
    model = ArchModel(
        nodes=[ModelNode("n1", "container", "Auth", responsibilities=[
            ModelResponsibility("r1", "validates JWT tokens")
        ])],
        links=[ModelLink("l1", "n1", "n2", "calls")],
    )
    store.save_committed(model)
    loaded = store.load_committed()
    assert loaded.nodes[0].id == "n1"
    assert loaded.nodes[0].name == "Auth"
    assert loaded.nodes[0].responsibilities[0].statement == "validates JWT tokens"
    assert loaded.links[0].id == "l1"

def test_committed_and_planned_are_independent(tmp_path):
    store = ModelStore(tmp_path)
    committed = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
    planned = ArchModel(nodes=[
        ModelNode("n1", "container", "Auth"),
        ModelNode("n2", "container", "Billing"),   # planned addition
    ])
    store.save_committed(committed)
    store.save_planned(planned)
    loaded_committed = store.load_committed()
    loaded_planned = store.load_planned()
    assert len(loaded_committed.nodes) == 1
    assert len(loaded_planned.nodes) == 2

def test_mark_implemented_folds_node(tmp_path):
    store = ModelStore(tmp_path)
    committed = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
    planned = ArchModel(nodes=[
        ModelNode("n1", "container", "Auth"),
        ModelNode("n2", "container", "Billing"),
    ])
    store.save_committed(committed)
    store.save_planned(planned)
    store.mark_implemented(["n2"])
    loaded = store.load_committed()
    ids = [n.id for n in loaded.nodes]
    assert "n2" in ids

def test_mark_implemented_removes_from_planned(tmp_path):
    store = ModelStore(tmp_path)
    committed = ArchModel()
    planned = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
    store.save_committed(committed)
    store.save_planned(planned)
    store.mark_implemented(["n1"])
    loaded_planned = store.load_planned()
    planned_ids = [n.id for n in loaded_planned.nodes]
    assert "n1" not in planned_ids

def test_is_planned_diverged_true_when_different(tmp_path):
    store = ModelStore(tmp_path)
    committed = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
    planned = ArchModel(nodes=[
        ModelNode("n1", "container", "Auth"),
        ModelNode("n2", "container", "Billing"),
    ])
    store.save_committed(committed)
    store.save_planned(planned)
    assert store.is_planned_diverged() is True

def test_is_planned_diverged_false_when_same(tmp_path):
    store = ModelStore(tmp_path)
    model = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
    store.save_committed(model)
    store.save_planned(model)
    assert store.is_planned_diverged() is False

def test_genesis_dir_created_if_missing(tmp_path):
    store = ModelStore(tmp_path)
    model = ArchModel()
    store.save_committed(model)
    assert (tmp_path / ".genesis" / "model.json").exists()

def test_vagrant_responsibility_roundtrip(tmp_path):
    store = ModelStore(tmp_path)
    model = ArchModel(nodes=[ModelNode("n1", "container", "Auth", responsibilities=[
        ModelResponsibility("r1", "handles auth", vagrant=True)
    ])])
    store.save_committed(model)
    loaded = store.load_committed()
    assert loaded.nodes[0].responsibilities[0].vagrant is True

def test_stale_responsibility_roundtrip(tmp_path):
    store = ModelStore(tmp_path)
    model = ArchModel(nodes=[ModelNode("n1", "container", "Auth", responsibilities=[
        ModelResponsibility("r1", "old claim", stale=True)
    ])])
    store.save_committed(model)
    loaded = store.load_committed()
    assert loaded.nodes[0].responsibilities[0].stale is True
```

---

## Approval Checkpoint

No code is written until these 5 step specifications are approved.

Each step is self-contained. Steps 1, 2, 3 can begin in parallel. Steps 4 and 5 can begin in parallel with each other after Step 1 (timeline data) is done.

Dependencies:
```
Step 1 (stdlib filter + bus factor + timeline)  →  no deps
Step 2 (confidence annotations)                 →  no deps
Step 3 (DependencyIndex + AffectedScope)        →  Step 1 (bus factor, for import_graph alignment)
Step 4 (WLS Decay Regressor)                    →  Step 1 (weekly timeline for week_offset)
Step 5 (ModelStore dual-layer)                  →  no deps (pure new module)

Later steps in the roadmap depend on Steps 4 and 5 (Temporal Scorer, Model Diff, etc.)
```
