"""
rules_engine.py - Genesis Architect PRO

Architecture regression gate. Reads a simple rules file and validates the
project's already-produced architecture/recovery outputs against quality gates.

Design:
- READ-ONLY. Never mutates model.json, planned.json, or any source.
- Deterministic. No LLM, no network.
- Dependency-light. Rules in `.genesis/rules.json` (stdlib json). `.genesis/
  rules.yml` is supported only if PyYAML happens to be installed (optional).
- Returns structured pass/fail; the CLI maps failures to a non-zero exit code.

Two policy modes:
- **enforcing** — the project ships `.genesis/rules.json`. Its rules are the
  policy, and a violation is a hard failure the gate acts on.
- **shadow** — no rules file. DEFAULT_RULES are evaluated and reported, but
  never escalated. Previously this case evaluated nothing at all, which
  rendered as a pass: a project with no policy looked identical to a project
  passing every check. Shadow mode makes the difference visible without
  imposing a block nobody opted into.

Supported rules (all optional; only those present are checked):
  min_architecture_score        int    score.total must be >= this
  max_critical_anti_patterns     int    count of CRITICAL anti-patterns <= this
  max_high_anti_patterns         int    count of HIGH anti-patterns <= this
  allow_circular_dependencies    bool   if False, cycle_count must be 0
  max_unpinned_actions           int    CI actions on a mutable ref <= this
  max_drift_score                number drift overall_score <= this
  max_stale_candidates           int    drift stale_count <= this
  max_vagrant_candidates         int    drift vagrant_count <= this
  min_source_anchor_coverage     number anchor coverage fraction (0..1) >= this
  max_risk_level                 str    project_risk_level <= this (none<low<medium<high<critical)
  require_recovery_report        bool   if True, a recovery report must be producible

Temporal rules (compare this run's result against the last recorded
observation in .genesis/score_history.jsonl, strictly before this run's own
score was appended; render as INSUFFICIENT_HISTORY, never a silent pass or
fail, when no prior observation exists):
  max_score_decline              number (baseline.total - current.total) <= this
  max_cycle_count_increase       int    (current.cycle_count - baseline.cycle_count) <= this

History rules (read git log / .genesis/score_history.jsonl; only gathered
when the rule is present, and skipped, never passed, when there is no data):
  bus_factor_min                 int|str  every file changed in the window has at
                                          least this many authors ("2_per_module" or 2)
    bus_factor_window_days       int      window for the above (default 90)
    bus_factor_ignore            [glob]   paths exempt from the above
  score_not_declining_over       int|str  score now >= score at the window start
                                          ("4_weeks", "28_days", or an int in weeks)
    score_decline_tolerance      number   points the score may drop (default 0)
  max_change_coupling            number   no file pair co-changes with a confidence
                                          above this (0..1)
    change_coupling_min_cochanges int     pairs seen together fewer times are noise
                                          (default 3)
    change_coupling_window_days  int      window for the above (default 90)
    change_coupling_ignore       [glob]   paths exempt (default: test files)

A rule whose value cannot be parsed fails rather than being skipped: a typo in
a policy must not read as compliance. The same holds for a key the engine does
not know (KNOWN_RULE_KEYS): it fails as "unknown rule - not evaluated", with the
closest known name as a hint. Keys starting with "_" or "$" are annotations.
"""

from __future__ import annotations

import difflib
import fnmatch
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

_RISK_ORDER = ["none", "low", "medium", "high", "critical"]

#: Rules whose facts come from git history rather than from the analysis
#: engines. gather_facts only pays for a git log when one of them is present.
HISTORY_WINDOW_DAYS = 90
COUPLING_MIN_COCHANGES = 3
#: Tests change with the code they test; that coupling is intended.
DEFAULT_COUPLING_IGNORE = (
    "test_*", "*_test.*", "*.test.*", "*.spec.*", "tests/*", "*/tests/*",
)
_BUS_FACTOR_RE = re.compile(r"^\s*(\d+)\s*(?:_?per_module)?\s*$", re.IGNORECASE)
_WINDOW_RE = re.compile(r"^\s*(\d+)\s*_?\s*(weeks?|days?)\s*$", re.IGNORECASE)

#: Evaluated when a project ships no rules file of its own. Deliberately a
#: baseline rather than an aspiration: every entry here is something whose
#: violation is a defect under any architecture, so that the default can one
#: day become enforcing without re-litigating each line.
#:
#: Reported but NOT enforced while SHADOW_BY_DEFAULT is True — see module
#: docstring. Turning that switch is a breaking change and belongs to its own
#: release, informed by what shadow mode measures.
DEFAULT_RULES: dict = {
    "allow_circular_dependencies": False,
    "max_critical_anti_patterns": 0,
    "max_unpinned_actions": 0,
}

#: While True, DEFAULT_RULES never produce a hard failure. An explicit rules
#: file is always enforcing regardless — opting in is opting in.
SHADOW_BY_DEFAULT = True

#: Every key evaluate() or gather_facts() reads: the gates and their options.
#: Any other key in a rules file is reported as a failure. evaluate() only
#: looks for the names it knows, so a misspelled or unsupported rule would
#: otherwise be skipped without a trace and the gate would pass a policy it
#: never checked. Keys starting with "_" or "$" are annotations ("_comment",
#: "$schema") and are ignored.
KNOWN_RULE_KEYS = frozenset({
    "min_architecture_score", "max_critical_anti_patterns", "max_high_anti_patterns",
    "allow_circular_dependencies", "max_unpinned_actions", "max_drift_score",
    "max_stale_candidates", "max_vagrant_candidates", "min_source_anchor_coverage",
    "max_risk_level", "require_recovery_report",
    "max_score_decline", "max_cycle_count_increase",
    "bus_factor_min", "bus_factor_window_days", "bus_factor_ignore",
    "score_not_declining_over", "score_decline_tolerance",
    "max_change_coupling", "change_coupling_min_cochanges",
    "change_coupling_window_days", "change_coupling_ignore",
})


def policy_mode(project_path: str | Path) -> tuple[str, str]:
    """Return (mode, source) for this project.

    mode   — "enforcing" | "shadow"
    source — "file" | "default"

    Consulted by engines that need to know whether to escalate a finding or
    merely report it, so the answer lives in one place rather than each caller
    re-deriving it from the presence of a file.
    """
    _rules, path_used, source = load_rules(project_path)
    if source == "file":
        return "enforcing", source
    return ("shadow" if SHADOW_BY_DEFAULT else "enforcing"), source


@dataclass
class RuleResult:
    rule: str
    passed: bool
    expected: object
    actual: object
    message: str
    #: "pass" | "fail" | "insufficient_history". Defaulted from `passed` when
    #: unset, so every existing call site keeps working unchanged. A temporal
    #: rule with no baseline sets this explicitly to "insufficient_history"
    #: while keeping passed=True, so it never escalates to a hard failure but
    #: still renders distinctly from an ordinary pass (see format_report()).
    status: str = ""

    def __post_init__(self) -> None:
        if not self.status:
            self.status = "pass" if self.passed else "fail"


@dataclass
class CheckReport:
    passed: bool = True
    results: list[RuleResult] = field(default_factory=list)
    rules_file: str = ""
    notes: list[str] = field(default_factory=list)

    #: "file" when the project declared its own rules, "default" when
    #: DEFAULT_RULES stood in.
    ruleset_source: str = "file"
    #: True when failures are reported but never escalated.
    shadow_mode: bool = False

    def add(self, r: RuleResult) -> None:
        self.results.append(r)
        if not r.passed:
            self.passed = False

    @property
    def hard_failure(self) -> bool:
        """A failure the gate should act on.

        Shadow-mode failures are real findings that were never opted into, so
        they inform without blocking. This is what RULES_FAIL consumes.
        """
        return (not self.passed) and not self.shadow_mode

    @property
    def hard_failure_reason(self) -> str:
        return ", ".join(r.rule for r in self.results if not r.passed)


# ---------------------------------------------------------------------------
# Rules file loading (dependency-light)
# ---------------------------------------------------------------------------

def load_rules(project_path: str | Path) -> tuple[dict, str, str]:
    """Load rules from .genesis/rules.json (preferred) or rules.yml (if PyYAML).

    Returns (rules_dict, path_used, source), where source is "file" when the
    project declared its own policy and "default" when DEFAULT_RULES stood in.

    The third element exists so callers can tell "passed the project's policy"
    apart from "passed a policy nobody chose". Those are different claims and
    the old two-tuple could not express the difference.
    """
    root = Path(project_path).resolve()
    genesis = root / ".genesis"
    json_path = genesis / "rules.json"
    yml_path = genesis / "rules.yml"

    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8")), str(json_path), "file"
    if yml_path.exists():
        try:
            import yaml  # optional - only if installed
        except ImportError:
            raise RuntimeError(
                f"{yml_path} found but PyYAML is not installed. "
                f"Use .genesis/rules.json instead, or install pyyaml."
            )
        return (yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {},
                str(yml_path), "file")
    return dict(DEFAULT_RULES), "", "default"


# ---------------------------------------------------------------------------
# Gathering the facts to check (read-only, from existing engines)
# ---------------------------------------------------------------------------

def gather_facts(
    project_path: str | Path,
    rules: dict | None = None,
    prior_history: list[dict] | None = None,
) -> dict:
    """Collect the metrics rules can check.

    Two tiers, kept visibly apart because they fail differently:

    **Engine-derived** — facts computed by other Genesis engines (score,
    anti-patterns, drift). These inherit whatever those engines already know.

    **File-derived** — facts read straight off disk. This tier exists because
    the engine-derived one structurally cannot answer questions about files no
    engine models: CI workflows, lockfiles, container manifests. Without it a
    whole class of policy has nowhere to live, which is exactly why supply
    chain checks had no home before.

    **History-derived** — git authorship, change coupling and the score
    history. Gathered only for the rules in *rules* that need them, since a
    git log is the slowest thing here. rules=None gathers none of it.

    `prior_history` is the pre-this-run snapshot of score_history.jsonl used
    by the temporal rules (max_score_decline, max_cycle_count_increase). The
    GDE path supplies it explicitly — captured before its own score is
    appended, so it never includes the current run's own observation.
    Standalone `genesis gate` passes None, which falls back to a direct read:
    correct by construction there, since nothing has been appended yet when
    this runs. An explicit `[]` (e.g. the GDE path with no upstream scorer
    output) is kept as-is and never triggers the disk fallback.

    Read-only: nothing here mutates project state (the git log is never
    cached to disk from here).
    """
    root = Path(project_path).resolve()
    facts: dict = {}

    # Architecture score + anti-patterns + cycles
    try:
        from genesis_architect_pro.architecture_scorer import score_project
        score = score_project(root)
        facts["architecture_score"] = score.get("total")
        facts["cycle_count"] = score.get("cycle_count", 0)
    except Exception as exc:  # noqa: BLE001
        facts["_score_error"] = str(exc)

    # Prior-history snapshot for temporal rules (max_score_decline,
    # max_cycle_count_increase). The GDE path supplies this explicitly,
    # captured before its own score is appended to score_history.jsonl; the
    # standalone path falls through to a direct read, which is already
    # correct because nothing has been appended yet when this runs.
    if prior_history is not None:
        facts["prior_history"] = prior_history
    else:
        try:
            from genesis_architect_pro.architecture_scorer import load_score_history
            facts["prior_history"] = load_score_history(root)
        except Exception:  # noqa: BLE001
            facts["prior_history"] = []

    try:
        from genesis_architect_pro.antipattern_detector import detect_all
        report = detect_all(root)
        facts["critical_anti_patterns"] = getattr(report, "critical_count", 0)
        facts["high_anti_patterns"] = getattr(report, "high_count", 0)
    except Exception as exc:  # noqa: BLE001
        facts["_antipattern_error"] = str(exc)

    # Recovery report -> drift + risk
    try:
        from genesis_architect_pro.recovery_report import generate_report_for_project
        rep = generate_report_for_project(root)
        facts["recovery_report_available"] = True
        facts["risk_level"] = getattr(rep, "project_risk_level", "none")
        drift = getattr(rep, "drift_summary", {}) or {}
        facts["drift_score"] = drift.get("overall_score", 0.0)
        facts["stale_candidates"] = drift.get("stale_count", 0)
        facts["vagrant_candidates"] = drift.get("vagrant_count", 0)
        facts["source_anchor_coverage"] = drift.get("anchor_coverage")
    except Exception as exc:  # noqa: BLE001
        facts["recovery_report_available"] = False
        facts["_recovery_error"] = str(exc)

    # --- file-derived tier ------------------------------------------------
    # Supply chain: CI actions must name an immutable revision.
    try:
        from genesis_architect_pro.supply_chain_audit import scan_workflows
        sc = scan_workflows(root)
        facts["ci_scanned"] = sc.scanned
        # None, not 0, when there is no CI to read. A project without
        # workflows has not been found compliant, and a rule comparing
        # against it must be able to tell those apart.
        facts["unpinned_actions"] = len(sc.unpinned) if sc.scanned else None
        facts["unpinnable_actions"] = len(sc.unpinnable) if sc.scanned else None
    except Exception as exc:  # noqa: BLE001
        facts["_supply_chain_error"] = str(exc)

    facts.update(_gather_history_facts(root, rules or {}))
    return facts


def _window_days(rules: dict, key: str) -> int:
    value = rules.get(key, HISTORY_WINDOW_DAYS)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return HISTORY_WINDOW_DAYS
    return value


def _min_cochanges(rules: dict) -> int:
    value = rules.get("change_coupling_min_cochanges", COUPLING_MIN_COCHANGES)
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        return COUPLING_MIN_COCHANGES
    return value


def _patterns(value, default=()) -> tuple[str, ...]:
    """A glob list from a rules value; a bare string is one pattern."""
    if value is None:
        return tuple(default)
    if isinstance(value, str):
        return (value,)
    return tuple(str(p) for p in value)


def _gather_history_facts(root: Path, rules: dict) -> dict:
    """History-derived tier. A fact left as None means "no data", never 0."""
    facts: dict = {}

    if "score_not_declining_over" in rules:
        facts["as_of"] = datetime.now(UTC).isoformat()
        try:
            from genesis_architect_pro.architecture_scorer import load_score_history
            facts["score_history"] = load_score_history(root)
        except Exception as exc:  # noqa: BLE001
            facts["_score_history_error"] = str(exc)

    if "bus_factor_min" in rules:
        facts["bus_factor_by_file"] = None
        try:
            from genesis_architect_pro.git_analyzer import per_module_churn
            churn = per_module_churn(root, days=_window_days(rules, "bus_factor_window_days"))
            # Files deleted since are part of the log but no longer anyone's
            # knowledge risk.
            by_file = {path: stats.get("bus_factor", 0) for path, stats in churn.items()
                       if (root / path).is_file()}
            if by_file:
                facts["bus_factor_by_file"] = by_file
        except Exception as exc:  # noqa: BLE001
            facts["_bus_factor_error"] = str(exc)

    if "max_change_coupling" in rules:
        facts["change_coupling"] = None
        try:
            from genesis_architect_pro.git_analyzer import (
                _git_log, _is_git_repo, change_coupling,
            )
            if _is_git_repo(root):
                commits = _git_log(root, _window_days(rules, "change_coupling_window_days"))
                if commits:
                    pairs = change_coupling(commits, top_n=100_000,
                                            min_cochanges=_min_cochanges(rules))
                    facts["change_coupling"] = [p.to_dict() for p in pairs]
        except Exception as exc:  # noqa: BLE001
            facts["_change_coupling_error"] = str(exc)

    return facts


# ---------------------------------------------------------------------------
# History rule helpers
# ---------------------------------------------------------------------------

def parse_bus_factor(value) -> int:
    """2, "2" or "2_per_module" -> 2. Raises ValueError on anything else."""
    if isinstance(value, bool):
        raise ValueError(f"expected an author count, got {value!r}")
    if isinstance(value, int):
        n = value
    else:
        m = _BUS_FACTOR_RE.match(str(value))
        if not m:
            raise ValueError(f"expected an author count like 2 or '2_per_module', got {value!r}")
        n = int(m.group(1))
    if n < 1:
        raise ValueError(f"author count must be at least 1, got {n}")
    return n


def parse_window_days(value) -> int:
    """"4_weeks" -> 28, "10_days" -> 10, 4 (weeks) -> 28. Raises ValueError."""
    if isinstance(value, bool):
        raise ValueError(f"expected a window like '4_weeks', got {value!r}")
    if isinstance(value, int):
        days = value * 7
    else:
        m = _WINDOW_RE.match(str(value))
        if not m:
            raise ValueError(f"expected a window like '4_weeks' or '28_days', got {value!r}")
        n, unit = int(m.group(1)), m.group(2).lower()
        days = n * 7 if unit.startswith("week") else n
    if days < 1:
        raise ValueError(f"window must be at least one day, got {value!r}")
    return days


def _parse_ts(value) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _matches_any(path: str, patterns) -> bool:
    path = path.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(path, p) or fnmatch.fnmatchcase(name, p)
               for p in patterns)


def score_trend(history: list[dict], window_days: int, as_of: datetime | None = None,
                current: float | None = None) -> dict | str:
    """
    Compare the score at the start of the window with the latest one.

    baseline: the newest record at or before the window start. When history
        does not reach back that far, the oldest record inside the window
        stands in and the result says how many days are covered.
    latest:   *current* (a live score) when given, else the newest record.

    Returns {baseline, latest, delta, baseline_ts, covered_days} or, when
    there is nothing to compare, a string saying why.
    """
    points = sorted(
        ((ts, float(r["total"])) for r in history
         if isinstance(r, dict) and isinstance(r.get("total"), (int, float))
         and not isinstance(r.get("total"), bool)
         and (ts := _parse_ts(r.get("timestamp"))) is not None),
        key=lambda p: p[0],
    )
    if as_of is None:
        if not points:
            return "no score history recorded"
        as_of = points[-1][0]
    points = [p for p in points if p[0] <= as_of]
    if not points:
        return "no score history recorded"

    start = as_of - timedelta(days=window_days)
    before = [p for p in points if p[0] <= start]
    inside = [p for p in points if p[0] > start]
    if before:
        baseline = before[-1]
    elif inside:
        baseline = inside[0]
    else:
        return "no score history recorded"

    if current is not None:
        latest_total = float(current)
    else:
        later = [p for p in inside if p[0] > baseline[0]]
        if not later:
            return (f"no score recorded after {baseline[0].date().isoformat()} "
                    f"in the last {window_days} days")
        latest_total = later[-1][1]

    covered = min(window_days, (as_of - baseline[0]).days)
    return {
        "baseline": baseline[1],
        "latest": latest_total,
        "delta": round(latest_total - baseline[1], 2),
        "baseline_ts": baseline[0].isoformat(),
        "covered_days": covered,
    }


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def _risk_rank(level: str) -> int:
    try:
        return _RISK_ORDER.index(str(level).lower())
    except ValueError:
        return len(_RISK_ORDER)  # unknown = worst


def evaluate(rules: dict, facts: dict) -> CheckReport:
    """Evaluate rules against gathered facts. Only present rules are checked."""
    report = CheckReport()

    def check(name, ok, expected, actual, msg):
        report.add(RuleResult(name, bool(ok), expected, actual, msg))

    if not isinstance(rules, dict):
        check("rules_file", False, "object", type(rules).__name__,
              "rules must be an object mapping rule names to values - nothing was evaluated")
        return report

    if "min_architecture_score" in rules:
        exp = rules["min_architecture_score"]
        act = facts.get("architecture_score")
        ok = act is not None and act >= exp
        check("min_architecture_score", ok, exp, act,
              f"score {act} >= {exp}" if ok else f"score {act} below minimum {exp}")

    if "max_critical_anti_patterns" in rules:
        exp = rules["max_critical_anti_patterns"]
        act = facts.get("critical_anti_patterns", 0)
        check("max_critical_anti_patterns", act <= exp, exp, act,
              f"{act} critical anti-patterns (max {exp})")

    if "max_high_anti_patterns" in rules:
        exp = rules["max_high_anti_patterns"]
        act = facts.get("high_anti_patterns", 0)
        check("max_high_anti_patterns", act <= exp, exp, act,
              f"{act} high anti-patterns (max {exp})")

    if "allow_circular_dependencies" in rules:
        allowed = rules["allow_circular_dependencies"]
        act = facts.get("cycle_count", 0)
        ok = allowed or act == 0
        check("allow_circular_dependencies", ok, allowed, act,
              f"{act} circular dependencies" + ("" if ok else " (not allowed)"))

    if "max_unpinned_actions" in rules:
        exp = rules["max_unpinned_actions"]
        act = facts.get("unpinned_actions")
        if act is None:
            # No CI was found. Skipped rather than passed: "nothing to check"
            # and "checked and clean" are different results, and only one of
            # them is evidence.
            report.notes.append(
                "max_unpinned_actions: skipped — no CI workflows found to check")
        else:
            check("max_unpinned_actions", act <= exp, exp, act,
                  f"{act} CI action(s) on a mutable ref (max {exp})")

    if "max_drift_score" in rules:
        exp = rules["max_drift_score"]
        act = facts.get("drift_score", 0.0)
        check("max_drift_score", act <= exp, exp, act,
              f"drift {act} (max {exp})")

    if "max_stale_candidates" in rules:
        exp = rules["max_stale_candidates"]
        act = facts.get("stale_candidates", 0)
        check("max_stale_candidates", act <= exp, exp, act,
              f"{act} stale candidates (max {exp})")

    if "max_vagrant_candidates" in rules:
        exp = rules["max_vagrant_candidates"]
        act = facts.get("vagrant_candidates", 0)
        check("max_vagrant_candidates", act <= exp, exp, act,
              f"{act} vagrant candidates (max {exp})")

    if "min_source_anchor_coverage" in rules:
        exp = rules["min_source_anchor_coverage"]
        act = facts.get("source_anchor_coverage")
        ok = act is not None and act >= exp
        check("min_source_anchor_coverage", ok, exp, act,
              f"anchor coverage {act} >= {exp}" if ok
              else f"anchor coverage {act} below {exp}")

    if "max_risk_level" in rules:
        exp = rules["max_risk_level"]
        act = facts.get("risk_level", "none")
        ok = _risk_rank(act) <= _risk_rank(exp)
        check("max_risk_level", ok, exp, act,
              f"risk {act} (max {exp})")

    if "require_recovery_report" in rules and rules["require_recovery_report"]:
        act = facts.get("recovery_report_available", False)
        check("require_recovery_report", act, True, act,
              "recovery report available" if act else "recovery report could not be produced")

    if "max_score_decline" in rules:
        exp = rules["max_score_decline"]
        if isinstance(exp, bool) or not isinstance(exp, (int, float)) or exp < 0:
            check("max_score_decline", False, exp, None,
                  f"invalid rule value: max_score_decline must be a non-negative "
                  f"number, got {exp!r}")
        else:
            prior = facts.get("prior_history") or []
            if not prior:
                report.add(RuleResult(
                    "max_score_decline", True, exp, None,
                    "insufficient history - no prior score recorded to compare "
                    "against; rule not evaluated",
                    status="insufficient_history",
                ))
            else:
                baseline_total = prior[-1].get("total", 0)
                current_total = facts.get("architecture_score", 0)
                decline = baseline_total - current_total
                check("max_score_decline", decline <= exp, exp, decline,
                      f"score decline {decline:g} pts (baseline {baseline_total:g} "
                      f"-> current {current_total:g}, max decline {exp:g})")

    if "max_cycle_count_increase" in rules:
        exp = rules["max_cycle_count_increase"]
        if isinstance(exp, bool) or not isinstance(exp, (int, float)) or exp < 0:
            check("max_cycle_count_increase", False, exp, None,
                  f"invalid rule value: max_cycle_count_increase must be a "
                  f"non-negative number, got {exp!r}")
        else:
            prior = facts.get("prior_history") or []
            if not prior:
                report.add(RuleResult(
                    "max_cycle_count_increase", True, exp, None,
                    "insufficient history - no prior cycle count recorded to "
                    "compare against; rule not evaluated",
                    status="insufficient_history",
                ))
            else:
                baseline_cycles = prior[-1].get("cycle_count", 0)
                current_cycles = facts.get("cycle_count", 0)
                increase = current_cycles - baseline_cycles
                check("max_cycle_count_increase", increase <= exp, exp, increase,
                      f"cycle count increase {increase:g} (baseline "
                      f"{baseline_cycles:g} -> current {current_cycles:g}, max "
                      f"increase {exp:g})")

    _evaluate_history_rules(rules, facts, report, check)

    for key in unknown_rule_keys(rules):
        close = difflib.get_close_matches(key, sorted(KNOWN_RULE_KEYS), n=1)
        check(key, False, None, None,
              "unknown rule - not evaluated; an unsupported or misspelled rule "
              "must not read as compliance"
              + (f" (did you mean '{close[0]}'?)" if close else ""))
    return report


def unknown_rule_keys(rules: dict) -> list[str]:
    """Keys of a rules dict that the engine does not evaluate, sorted."""
    return sorted(str(k) for k in rules
                  if k not in KNOWN_RULE_KEYS
                  and not (isinstance(k, str) and k.startswith(("_", "$"))))


def _evaluate_history_rules(rules: dict, facts: dict, report: CheckReport, check) -> None:
    if "bus_factor_min" in rules:
        raw = rules["bus_factor_min"]
        try:
            exp = parse_bus_factor(raw)
        except ValueError as exc:
            check("bus_factor_min", False, raw, None, f"invalid rule value: {exc}")
        else:
            by_file = facts.get("bus_factor_by_file")
            ignore = _patterns(rules.get("bus_factor_ignore"))
            if by_file:
                by_file = {p: n for p, n in by_file.items() if not _matches_any(p, ignore)}
            if not by_file:
                report.notes.append(
                    "bus_factor_min: skipped — no git history with authors to check")
            else:
                low = sorted((n, p) for p, n in by_file.items() if n < exp)
                worst = ", ".join(f"{p} ({n})" for n, p in low[:5])
                check("bus_factor_min", not low, exp, len(low),
                      f"all {len(by_file)} changed files have >= {exp} author(s)" if not low
                      else f"{len(low)} of {len(by_file)} changed files have fewer than "
                           f"{exp} author(s): {worst}" + (" ..." if len(low) > 5 else ""))

    if "score_not_declining_over" in rules:
        raw = rules["score_not_declining_over"]
        tolerance = rules.get("score_decline_tolerance", 0)
        try:
            window = parse_window_days(raw)
            if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) \
                    or tolerance < 0:
                raise ValueError(f"score_decline_tolerance must be a number >= 0, "
                                 f"got {tolerance!r}")
        except ValueError as exc:
            check("score_not_declining_over", False, raw, None, f"invalid rule value: {exc}")
        else:
            trend = score_trend(facts.get("score_history") or [], window,
                                as_of=_parse_ts(facts.get("as_of")) if facts.get("as_of") else None,
                                current=facts.get("architecture_score"))
            if isinstance(trend, str):
                report.notes.append(f"score_not_declining_over: skipped — {trend}")
            else:
                ok = trend["delta"] >= -tolerance
                span = (f" (history covers only {trend['covered_days']} of {window} days)"
                        if trend["covered_days"] < window else "")
                check("score_not_declining_over", ok, raw, trend["delta"],
                      f"score {trend['latest']:g} vs {trend['baseline']:g} on "
                      f"{trend['baseline_ts'][:10]} ({trend['delta']:+g} over {window} days"
                      + (f", tolerance {tolerance:g}" if tolerance else "") + ")" + span)

    if "max_change_coupling" in rules:
        exp = rules["max_change_coupling"]
        if isinstance(exp, bool) or not isinstance(exp, (int, float)) or not 0 <= exp <= 1:
            check("max_change_coupling", False, exp, None,
                  f"invalid rule value: expected a confidence between 0 and 1, got {exp!r}")
        else:
            pairs = facts.get("change_coupling")
            if pairs is None:
                report.notes.append(
                    "max_change_coupling: skipped — no git history to check")
            else:
                ignore = _patterns(rules.get("change_coupling_ignore"),
                                   DEFAULT_COUPLING_IGNORE)
                min_co = _min_cochanges(rules)
                kept = [p for p in pairs
                        if p.get("cochanges", 0) >= min_co
                        and not _matches_any(p["file_a"], ignore)
                        and not _matches_any(p["file_b"], ignore)]
                act = max((p["confidence"] for p in kept), default=0.0)
                over = [p for p in kept if p["confidence"] > exp]
                top = ", ".join(f"{p['file_a']} <-> {p['file_b']} ({p['confidence']:.2f})"
                                for p in over[:3])
                check("max_change_coupling", not over, exp, act,
                      f"max co-change confidence {act:.2f} across {len(kept)} pair(s) "
                      f"(max {exp})" if not over
                      else f"{len(over)} file pair(s) co-change above {exp}: {top}"
                           + (" ..." if len(over) > 3 else ""))


def run_check(
    project_path: str | Path,
    prior_history: list[dict] | None = None,
) -> CheckReport:
    """Top-level: load rules, gather facts, evaluate. Read-only."""
    rules, path_used, source = load_rules(project_path)
    facts = gather_facts(project_path, rules, prior_history=prior_history)
    report = evaluate(rules, facts)
    report.rules_file = path_used
    report.ruleset_source = source
    report.shadow_mode = (source == "default") and SHADOW_BY_DEFAULT
    if source == "default":
        report.notes.append(
            "no .genesis/rules.json — evaluating the default ruleset"
            + (" in shadow mode (reported, never blocking)" if report.shadow_mode
               else " as policy"))
    return report


def format_report(report: CheckReport) -> str:
    """Human-readable pass/fail output."""
    lines = []
    if report.ruleset_source == "file":
        lines.append(f"genesis check  (rules: {report.rules_file})")
    else:
        lines.append("genesis check  (default ruleset — no .genesis/rules.json)")
        if report.shadow_mode:
            lines.append("  MODE: SHADOW — findings are reported, nothing is blocked.")
            lines.append("  Add .genesis/rules.json to enforce a policy of your own.")

    for r in report.results:
        if r.status == "insufficient_history":
            mark = "INSUFFICIENT_HISTORY"
        else:
            mark = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{mark}] {r.rule}: {r.message}")
    for note in report.notes:
        if "skipped" in note:
            lines.append(f"  [skip] {note}")

    insufficient = [r for r in report.results if r.status == "insufficient_history"]
    lines.append("")
    if report.passed:
        if insufficient:
            lines.append(
                f"RESULT: PASS (enforceable rules) - {len(insufficient)} temporal "
                f"rule(s) not evaluated: INSUFFICIENT_HISTORY"
            )
        else:
            lines.append("RESULT: PASS - all gates satisfied")
    elif report.shadow_mode:
        failed = sum(1 for r in report.results if not r.passed)
        lines.append(f"RESULT: SHADOW - {failed} rule(s) would fail once enforcing "
                     f"(not blocking this release)")
    else:
        lines.append("RESULT: FAIL - one or more gates violated")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry: `genesis gate` (and `python -m genesis_architect_pro.rules_engine`)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Run the architecture regression gate. Exit 0 on pass, 1 on fail, 2 on error.

    No rules file means the default ruleset is evaluated in shadow mode: the
    findings are printed and the exit code stays 0.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="genesis gate",
        description="Architecture regression gate - validate rules against analysis outputs.",
    )
    parser.add_argument("project_dir", nargs="?", default=".",
                        help="Project directory (default: current)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args(argv)

    try:
        report = run_check(args.project_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"genesis gate: error - {exc}", file=sys.stderr)
        return 2

    if args.json:
        import dataclasses
        print(json.dumps(dataclasses.asdict(report), default=str, indent=2))
    else:
        print(format_report(report))

    # Shadow findings are informational. A non-zero exit here would break CI
    # over a policy the project never opted into.
    return 0 if (report.passed or report.shadow_mode) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
