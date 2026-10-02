"""Tests for rules_engine - the genesis gate architecture regression check."""
import json
from pathlib import Path


from genesis_architect_pro.rules_engine import (
    DEFAULT_RULES, KNOWN_RULE_KEYS, load_rules, evaluate, run_check, format_report, main,
    unknown_rule_keys, _risk_rank,
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
    def test_no_file_falls_back_to_the_default_ruleset(self, tmp_path):
        """Previously this returned {}, so a project with no policy evaluated
        nothing and rendered identically to one passing every check. The
        default ruleset makes the difference visible; shadow mode keeps it
        from blocking anyone who never opted in."""
        from genesis_architect_pro.rules_engine import DEFAULT_RULES

        rules, path, source = load_rules(tmp_path)
        assert rules == DEFAULT_RULES
        assert path == ""
        assert source == "default"

    def test_loads_json(self, tmp_path):
        _project(tmp_path, {"min_architecture_score": 50})
        rules, path, source = load_rules(tmp_path)
        assert rules["min_architecture_score"] == 50
        assert path.endswith("rules.json")
        assert source == "file"


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


class TestUnknownRuleKeys:
    """evaluate() only looks for names it knows. An unknown key used to be
    skipped without a trace, so a policy of nothing but typos passed."""

    def test_unknown_key_fails_and_says_not_evaluated(self):
        rep = evaluate({"max_widgets": 0}, {})
        assert not rep.passed
        (res,) = rep.results
        assert res.rule == "max_widgets"
        assert "unknown rule" in res.message and "not evaluated" in res.message

    def test_keys_from_the_old_guide_examples_fail(self):
        # docs/pro/guide/27 and 41 used to ship these; none was ever evaluated
        for key, value in (("max_cycles", 0), ("max_god_classes", 2), ("fail_on_drift", True)):
            rep = evaluate({key: value}, {"cycle_count": 5})
            assert not rep.passed, key
            assert rep.hard_failure_reason == key

    def test_known_rules_still_evaluated_next_to_an_unknown_one(self):
        rep = evaluate({"min_architecture_score": 50, "typo_rule": 1}, {"architecture_score": 80})
        by_rule = {r.rule: r.passed for r in rep.results}
        assert by_rule == {"min_architecture_score": True, "typo_rule": False}

    def test_close_match_is_suggested(self):
        rep = evaluate({"min_architecture_scor": 50}, {"architecture_score": 80})
        assert "did you mean 'min_architecture_score'" in rep.results[0].message

    def test_no_suggestion_when_nothing_is_close(self):
        rep = evaluate({"zzzz": 1}, {})
        assert "did you mean" not in rep.results[0].message

    def test_annotation_keys_are_ignored(self):
        rep = evaluate({"_comment": "ratchet up later", "$schema": "x",
                        "min_architecture_score": 50}, {"architecture_score": 80})
        assert rep.passed and [r.rule for r in rep.results] == ["min_architecture_score"]

    def test_non_string_key_is_reported_not_crashed(self):
        # rules.yml can produce non-string keys
        assert unknown_rule_keys({5: 1, True: 2, "_x": 3}) == ["5", "True"]

    def test_every_known_key_is_accepted(self):
        assert unknown_rule_keys(dict.fromkeys(KNOWN_RULE_KEYS, 0)) == []

    def test_default_rules_are_known(self):
        assert unknown_rule_keys(DEFAULT_RULES) == []

    def test_known_keys_cover_every_key_the_engine_reads(self):
        import re
        from genesis_architect_pro import rules_engine
        source = Path(rules_engine.__file__).read_text(encoding="utf-8")
        read = set(re.findall(
            r'rules(?:\.get\(|\[)"([a-z_]+)"|"([a-z_]+)" in rules'
            r'|_window_days\(rules, "([a-z_]+)"\)', source))
        read = {name for groups in read for name in groups if name}
        assert read, "pattern no longer matches the engine source"
        assert read <= KNOWN_RULE_KEYS, read - KNOWN_RULE_KEYS

    def test_every_known_key_is_documented(self):
        from genesis_architect_pro import rules_engine
        missing = [k for k in sorted(KNOWN_RULE_KEYS) if k not in rules_engine.__doc__]
        assert not missing

    def test_non_object_rules_fail(self):
        rep = evaluate(["min_architecture_score"], {"architecture_score": 80})
        assert not rep.passed
        assert rep.results[0].rule == "rules_file" and "nothing was evaluated" in rep.results[0].message

    def test_main_exits_1_for_a_policy_of_unknown_keys(self, tmp_path):
        _project(tmp_path, {"max_cycles": 0})
        assert main([str(tmp_path)]) == 1
        (tmp_path / ".genesis" / "rules.json").write_text(json.dumps(["max_cycles"]))
        assert main([str(tmp_path)]) == 1
