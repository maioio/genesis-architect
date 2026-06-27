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

Supported rules (all optional; only those present are checked):
  min_architecture_score        int    score.total must be >= this
  max_critical_anti_patterns     int    count of CRITICAL anti-patterns <= this
  max_high_anti_patterns         int    count of HIGH anti-patterns <= this
  allow_circular_dependencies    bool   if False, cycle_count must be 0
  max_drift_score                number drift overall_score <= this
  max_stale_candidates           int    drift stale_count <= this
  max_vagrant_candidates         int    drift vagrant_count <= this
  min_source_anchor_coverage     number anchor coverage fraction (0..1) >= this
  max_risk_level                 str    project_risk_level <= this (none<low<medium<high<critical)
  require_recovery_report        bool   if True, a recovery report must be producible
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_RISK_ORDER = ["none", "low", "medium", "high", "critical"]


@dataclass
class RuleResult:
    rule: str
    passed: bool
    expected: object
    actual: object
    message: str


@dataclass
class CheckReport:
    passed: bool = True
    results: list[RuleResult] = field(default_factory=list)
    rules_file: str = ""
    notes: list[str] = field(default_factory=list)

    def add(self, r: RuleResult) -> None:
        self.results.append(r)
        if not r.passed:
            self.passed = False


# ---------------------------------------------------------------------------
# Rules file loading (dependency-light)
# ---------------------------------------------------------------------------

def load_rules(project_path: str | Path) -> tuple[dict, str]:
    """Load rules from .genesis/rules.json (preferred) or rules.yml (if PyYAML).

    Returns (rules_dict, path_used). Empty dict if no rules file exists.
    """
    root = Path(project_path).resolve()
    genesis = root / ".genesis"
    json_path = genesis / "rules.json"
    yml_path = genesis / "rules.yml"

    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8")), str(json_path)
    if yml_path.exists():
        try:
            import yaml  # optional - only if installed
        except ImportError:
            raise RuntimeError(
                f"{yml_path} found but PyYAML is not installed. "
                f"Use .genesis/rules.json instead, or install pyyaml."
            )
        return yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}, str(yml_path)
    return {}, ""


# ---------------------------------------------------------------------------
# Gathering the facts to check (read-only, from existing engines)
# ---------------------------------------------------------------------------

def gather_facts(project_path: str | Path) -> dict:
    """Collect the metrics rules can check, from existing Genesis outputs.

    Read-only: calls scorers/reporters that do not mutate project state.
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

    return facts


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

    return report


def run_check(project_path: str | Path) -> CheckReport:
    """Top-level: load rules, gather facts, evaluate. Read-only."""
    rules, path_used = load_rules(project_path)
    if not rules:
        report = CheckReport(passed=True, rules_file="")
        report.notes.append("No rules file (.genesis/rules.json) found - nothing to check.")
        return report
    facts = gather_facts(project_path)
    report = evaluate(rules, facts)
    report.rules_file = path_used
    return report


def format_report(report: CheckReport) -> str:
    """Human-readable pass/fail output."""
    lines = []
    if not report.rules_file:
        lines.append("genesis check: " + (report.notes[0] if report.notes else "no rules"))
        return "\n".join(lines)
    lines.append(f"genesis check  (rules: {report.rules_file})")
    for r in report.results:
        mark = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{mark}] {r.rule}: {r.message}")
    lines.append("")
    lines.append("RESULT: " + ("PASS - all gates satisfied" if report.passed
                               else "FAIL - one or more gates violated"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry: `genesis gate` (and `python -m genesis_architect_pro.rules_engine`)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Run the architecture regression gate. Exit 0 on pass, 1 on fail, 2 on error.

    No rules file present is treated as a pass (nothing to enforce) with exit 0.
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

    return 0 if report.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
