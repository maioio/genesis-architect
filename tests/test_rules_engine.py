"""Tests for rules_engine - the genesis gate architecture regression check."""
import json
from pathlib import Path


from genesis_architect_pro.rules_engine import (
    load_rules, evaluate, run_check, format_report, main,
    _risk_rank,
)


def _project(tmp_path: Path, rules: dict | None = None) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("import os\n")
    if rules is not None:
        g = tmp_path / ".genesis"
        g.mkdir(exist_ok=True)
        (g / "rules.json").write_text(json.dumps(rules))
    return tmp_path


class TestLoadRules:
    def test_no_file_returns_empty(self, tmp_path):
        rules, path = load_rules(tmp_path)
        assert rules == {} and path == ""

    def test_loads_json(self, tmp_path):
        _project(tmp_path, {"min_architecture_score": 50})
        rules, path = load_rules(tmp_path)
        assert rules["min_architecture_score"] == 50
        assert path.endswith("rules.json")


class TestEvaluate:
    def test_only_present_rules_checked(self):
        rep = evaluate({"min_architecture_score": 50}, {"architecture_score": 80})
        assert len(rep.results) == 1
        assert rep.passed

    def test_min_score_fail(self):
        rep = evaluate({"min_architecture_score": 90}, {"architecture_score": 50})
        assert not rep.passed

    def test_circular_dep_not_allowed(self):
        rep = evaluate({"allow_circular_dependencies": False}, {"cycle_count": 2})
        assert not rep.passed

    def test_circular_dep_allowed(self):
        rep = evaluate({"allow_circular_dependencies": True}, {"cycle_count": 2})
        assert rep.passed

    def test_max_critical_anti_patterns(self):
        assert evaluate({"max_critical_anti_patterns": 0}, {"critical_anti_patterns": 0}).passed
        assert not evaluate({"max_critical_anti_patterns": 0}, {"critical_anti_patterns": 3}).passed

    def test_max_drift_score(self):
        assert evaluate({"max_drift_score": 30}, {"drift_score": 10}).passed
        assert not evaluate({"max_drift_score": 30}, {"drift_score": 75}).passed

    def test_max_risk_level_ordering(self):
        assert evaluate({"max_risk_level": "medium"}, {"risk_level": "low"}).passed
        assert not evaluate({"max_risk_level": "low"}, {"risk_level": "high"}).passed

    def test_require_recovery_report(self):
        assert evaluate({"require_recovery_report": True}, {"recovery_report_available": True}).passed
        assert not evaluate({"require_recovery_report": True}, {"recovery_report_available": False}).passed

    def test_min_anchor_coverage(self):
        assert evaluate({"min_source_anchor_coverage": 0.5}, {"source_anchor_coverage": 0.8}).passed
        assert not evaluate({"min_source_anchor_coverage": 0.5}, {"source_anchor_coverage": 0.2}).passed
        # missing coverage = fail (cannot prove it meets the bar)
        assert not evaluate({"min_source_anchor_coverage": 0.5}, {}).passed


class TestRiskRank:
    def test_ordering(self):
        assert _risk_rank("none") < _risk_rank("low") < _risk_rank("high") < _risk_rank("critical")

    def test_unknown_is_worst(self):
        assert _risk_rank("bogus") >= _risk_rank("critical")


class TestRunCheckAndMain:
    def test_no_rules_passes(self, tmp_path):
        _project(tmp_path)  # no rules file
        rep = run_check(tmp_path)
        assert rep.passed and rep.rules_file == ""

    def test_passing_project(self, tmp_path):
        _project(tmp_path, {"min_architecture_score": 10, "allow_circular_dependencies": False})
        assert run_check(tmp_path).passed

    def test_failing_project(self, tmp_path):
        _project(tmp_path, {"min_architecture_score": 999})
        assert not run_check(tmp_path).passed

    def test_main_exit_codes(self, tmp_path):
        _project(tmp_path, {"min_architecture_score": 10})
        assert main([str(tmp_path)]) == 0
        (tmp_path / ".genesis" / "rules.json").write_text(json.dumps({"min_architecture_score": 999}))
        assert main([str(tmp_path)]) == 1

    def test_main_no_rules_exit_zero(self, tmp_path):
        _project(tmp_path)
        assert main([str(tmp_path)]) == 0


class TestFormat:
    def test_format_shows_pass_fail(self, tmp_path):
        _project(tmp_path, {"min_architecture_score": 999})
        out = format_report(run_check(tmp_path))
        assert "FAIL" in out and "RESULT:" in out
