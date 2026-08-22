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
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_RISK_ORDER = ["none", "low", "medium", "high", "critical"]

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

def gather_facts(project_path: str | Path) -> dict:
    """Collect the metrics rules can check.

    Two tiers, kept visibly apart because they fail differently:

    **Engine-derived** — facts computed by other Genesis engines (score,
    anti-patterns, drift). These inherit whatever those engines already know.

    **File-derived** — facts read straight off disk. This tier exists because
    the engine-derived one structurally cannot answer questions about files no
    engine models: CI workflows, lockfiles, container manifests. Without it a
    whole class of policy has nowhere to live, which is exactly why supply
    chain checks had no home before.

    Read-only: nothing here mutates project state.
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

    return report


def run_check(project_path: str | Path) -> CheckReport:
    """Top-level: load rules, gather facts, evaluate. Read-only."""
    rules, path_used, source = load_rules(project_path)
    facts = gather_facts(project_path)
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
        mark = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{mark}] {r.rule}: {r.message}")
    for note in report.notes:
        if "skipped" in note:
            lines.append(f"  [skip] {note}")

    lines.append("")
    if report.passed:
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
