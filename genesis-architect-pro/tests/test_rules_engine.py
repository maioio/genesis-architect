"""Tests for rules_engine - the genesis gate architecture regression check."""
import json
from pathlib import Path


from genesis_architect_pro.rules_engine import (
    DEFAULT_RULES, KNOWN_RULE_KEYS, load_rules, evaluate, run_check, format_report, main,
    unknown_rule_keys, _risk_rank,
)
from genesis_architect_pro.gde_engine_adapters import (
    gde_run_rules_engine, gde_run_architecture_scorer,
)
from genesis_architect_pro.gde_types import SessionContext, EngineResult, EngineStatus, GDEMode


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


class TestTemporalRules:
    """max_score_decline / max_cycle_count_increase - compare against
    prior_history[-1], the pre-this-run snapshot (see ARCHITECTURE_REGRESSION_
    TEMPORAL_DESIGN.md)."""

    def test_score_regression_fails(self):
        rep = evaluate({"max_score_decline": 5},
                        {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]})
        (res,) = [r for r in rep.results if r.rule == "max_score_decline"]
        assert not res.passed and res.status == "fail" and res.actual == 10
        assert not rep.passed

    def test_score_regression_passes_within_budget(self):
        rep = evaluate({"max_score_decline": 15},
                        {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]})
        (res,) = [r for r in rep.results if r.rule == "max_score_decline"]
        assert res.passed and res.status == "pass"
        assert rep.passed

    def test_cycle_regression_fails(self):
        rep = evaluate({"max_cycle_count_increase": 1},
                        {"cycle_count": 5, "prior_history": [{"total": 0, "cycle_count": 2}]})
        (res,) = [r for r in rep.results if r.rule == "max_cycle_count_increase"]
        assert not res.passed and res.actual == 3
        assert not rep.passed

    def test_cycle_regression_passes(self):
        rep = evaluate({"max_cycle_count_increase": 5},
                        {"cycle_count": 5, "prior_history": [{"total": 0, "cycle_count": 2}]})
        (res,) = [r for r in rep.results if r.rule == "max_cycle_count_increase"]
        assert res.passed
        assert rep.passed

    def test_improvement_passes_even_a_zero_threshold(self):
        # Score went UP: decline is negative, always <= 0.
        rep = evaluate({"max_score_decline": 0},
                        {"architecture_score": 80, "prior_history": [{"total": 70, "cycle_count": 0}]})
        assert rep.passed

    def test_exact_threshold_boundary_passes(self):
        # decline == max_score_decline exactly -> pass ("<=", not "<").
        rep = evaluate({"max_score_decline": 10},
                        {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]})
        (res,) = rep.results
        assert res.passed and res.actual == 10

    def test_one_point_past_the_boundary_fails(self):
        rep = evaluate({"max_score_decline": 9},
                        {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]})
        (res,) = rep.results
        assert not res.passed

    def test_zero_threshold_blocks_any_decline(self):
        rep = evaluate({"max_score_decline": 0},
                        {"architecture_score": 69, "prior_history": [{"total": 70, "cycle_count": 0}]})
        assert not rep.passed

    def test_zero_threshold_allows_no_change(self):
        rep = evaluate({"max_score_decline": 0},
                        {"architecture_score": 70, "prior_history": [{"total": 70, "cycle_count": 0}]})
        assert rep.passed

    def test_no_prior_history_is_insufficient_not_pass_or_fail(self):
        rep = evaluate({"max_score_decline": 5, "max_cycle_count_increase": 1},
                        {"architecture_score": 60, "cycle_count": 5, "prior_history": []})
        assert rep.passed  # insufficient_history keeps passed=True, non-blocking
        statuses = {r.rule: r.status for r in rep.results}
        assert statuses == {"max_score_decline": "insufficient_history",
                             "max_cycle_count_increase": "insufficient_history"}

    def test_missing_prior_history_key_is_also_insufficient(self):
        # facts with no "prior_history" key at all, not just an empty list.
        rep = evaluate({"max_score_decline": 5}, {"architecture_score": 60})
        (res,) = rep.results
        assert res.status == "insufficient_history" and res.passed

    def test_one_prior_snapshot_is_evaluated_as_the_baseline(self):
        rep = evaluate({"max_score_decline": 5},
                        {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]})
        (res,) = rep.results
        assert res.status in ("pass", "fail")  # evaluated, not insufficient
        assert res.actual == 10

    def test_baseline_is_the_last_prior_snapshot_not_the_first(self):
        history = [{"total": 40, "cycle_count": 0}, {"total": 70, "cycle_count": 0}]
        rep = evaluate({"max_score_decline": 5}, {"architecture_score": 60, "prior_history": history})
        (res,) = rep.results
        assert res.actual == 10  # 70 - 60 (prior[-1]), never 40 - 60 (prior[0])

    def test_negative_score_threshold_is_invalid_and_fails_explicitly(self):
        rep = evaluate({"max_score_decline": -1},
                        {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]})
        (res,) = rep.results
        assert not res.passed and res.status == "fail"
        assert "invalid rule value" in res.message

    def test_negative_cycle_threshold_is_invalid(self):
        rep = evaluate({"max_cycle_count_increase": -1},
                        {"cycle_count": 5, "prior_history": [{"total": 0, "cycle_count": 2}]})
        (res,) = rep.results
        assert not res.passed and res.status == "fail"
        assert "invalid rule value" in res.message

    def test_non_numeric_threshold_is_invalid(self):
        rep = evaluate({"max_score_decline": "five"},
                        {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]})
        (res,) = rep.results
        assert not res.passed and "invalid rule value" in res.message

    def test_bool_threshold_is_invalid(self):
        # bool is an int subclass in Python - must be rejected explicitly.
        rep = evaluate({"max_score_decline": True},
                        {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]})
        (res,) = rep.results
        assert not res.passed and "invalid rule value" in res.message

    def test_invalid_threshold_fails_even_with_no_history(self):
        # Threshold validation happens before the history-availability branch.
        rep = evaluate({"max_score_decline": -1}, {"architecture_score": 60, "prior_history": []})
        (res,) = rep.results
        assert res.status == "fail" and not res.passed

    def test_json_report_carries_status_additively(self):
        import dataclasses
        rep = evaluate({"max_score_decline": 5}, {"architecture_score": 60, "prior_history": []})
        d = dataclasses.asdict(rep)
        assert d["results"][0]["status"] == "insufficient_history"
        assert d["results"][0]["passed"] is True

    def test_existing_static_rules_are_unaffected_by_temporal_rules(self):
        rep = evaluate(
            {"min_architecture_score": 50, "max_score_decline": 5},
            {"architecture_score": 60, "prior_history": [{"total": 70, "cycle_count": 0}]},
        )
        by_rule = {r.rule: r.passed for r in rep.results}
        assert by_rule["min_architecture_score"] is True
        assert by_rule["max_score_decline"] is False

    def test_human_output_does_not_label_insufficient_history_as_pass(self, tmp_path):
        _project(tmp_path, {"max_score_decline": 5})  # no score_history.jsonl on disk
        out = format_report(run_check(tmp_path))
        assert "INSUFFICIENT_HISTORY" in out
        assert "[PASS] max_score_decline" not in out
        assert "RESULT: PASS (enforceable rules)" in out


class TestStandaloneDiskHistoryPath:
    """run_check(project_path) with no prior_history argument: gather_facts()
    falls back to reading .genesis/score_history.jsonl straight off disk."""

    def test_standalone_path_reads_prior_history_from_disk(self, tmp_path):
        _project(tmp_path, {"max_score_decline": 5})
        (tmp_path / ".genesis" / "score_history.jsonl").write_text(
            json.dumps({"total": 95, "cycle_count": 0}) + "\n", encoding="utf-8")
        report = run_check(tmp_path)
        (res,) = [r for r in report.results if r.rule == "max_score_decline"]
        assert res.status in ("pass", "fail")  # a baseline existed on disk

    def test_standalone_path_no_history_file_is_insufficient(self, tmp_path):
        _project(tmp_path, {"max_score_decline": 5})
        report = run_check(tmp_path)
        (res,) = [r for r in report.results if r.rule == "max_score_decline"]
        assert res.status == "insufficient_history"

    def test_malformed_history_lines_are_skipped_not_fatal(self, tmp_path):
        _project(tmp_path, {"max_score_decline": 5})
        (tmp_path / ".genesis" / "score_history.jsonl").write_text(
            json.dumps({"total": 95, "cycle_count": 0}) + "\n" + "{not valid json\n",
            encoding="utf-8")
        report = run_check(tmp_path)  # must not raise
        (res,) = [r for r in report.results if r.rule == "max_score_decline"]
        assert res.status in ("pass", "fail")  # the good line still forms a baseline

    def test_unreadable_history_file_is_insufficient_not_a_crash(self, tmp_path):
        _project(tmp_path, {"max_score_decline": 5})
        # Invalid UTF-8 bytes -> UnicodeDecodeError on the whole-file read;
        # load_score_history() treats this as "no history", not a crash.
        (tmp_path / ".genesis" / "score_history.jsonl").write_bytes(b"\xff\xfe\x00\x01garbage")
        report = run_check(tmp_path)  # must not raise
        (res,) = [r for r in report.results if r.rule == "max_score_decline"]
        assert res.status == "insufficient_history"


class TestGDETemporalAdapters:
    """GDE-path wiring: gde_run_rules_engine() must use the architecture_scorer
    engine's output exclusively, never falling back to disk history."""

    def _ctx_with_scorer_output(self, tmp_path, prior_history):
        ctx = SessionContext(mode=GDEMode.GATE, project_dir=tmp_path)
        ctx.engine_results["architecture_scorer"] = EngineResult(
            engine_id="architecture_scorer", status=EngineStatus.SUCCESS,
            output={"prior_history": prior_history},
        )
        return ctx

    def test_gde_prior_history_path_uses_the_injected_snapshot(self, tmp_path):
        _project(tmp_path, {"max_score_decline": 5})
        ctx = self._ctx_with_scorer_output(tmp_path, [{"total": 95, "cycle_count": 0}])
        out = gde_run_rules_engine(ctx)
        assert "INSUFFICIENT_HISTORY" not in out["rules_report"]
        assert "max_score_decline" in out["rules_report"]

    def test_gde_missing_upstream_history_does_not_fall_back_to_disk(self, tmp_path):
        _project(tmp_path, {"max_score_decline": 5})
        genesis = tmp_path / ".genesis"
        genesis.mkdir(exist_ok=True)
        # Real history sits on disk, but no "architecture_scorer" engine result
        # exists in ctx - the adapter must not reach for the disk file anyway.
        (genesis / "score_history.jsonl").write_text(
            json.dumps({"total": 95, "cycle_count": 0}) + "\n", encoding="utf-8")
        ctx = SessionContext(mode=GDEMode.GATE, project_dir=tmp_path)
        out = gde_run_rules_engine(ctx)
        assert "INSUFFICIENT_HISTORY [max_score_decline]" in " ".join(out["_warnings"])
        assert "INSUFFICIENT_HISTORY" in out["rules_report"]

    def test_gde_insufficient_history_surfaces_as_a_warning(self, tmp_path):
        _project(tmp_path, {"max_score_decline": 5})
        ctx = self._ctx_with_scorer_output(tmp_path, [])  # explicit empty, not missing
        out = gde_run_rules_engine(ctx)
        assert any(w.startswith("INSUFFICIENT_HISTORY [max_score_decline]")
                   for w in out["_warnings"])

    def test_gde_architecture_scorer_prior_history_excludes_its_own_run(self, tmp_path):
        _project(tmp_path)
        ctx1 = SessionContext(mode=GDEMode.GATE, project_dir=tmp_path)
        out1 = gde_run_architecture_scorer(ctx1)
        assert out1["prior_history"] == []  # nothing on disk yet, before this run's append

        ctx2 = SessionContext(mode=GDEMode.GATE, project_dir=tmp_path)
        out2 = gde_run_architecture_scorer(ctx2)
        # Exactly ctx1's appended record - never ctx2's own just-computed score
        # (which the unrelated "history" key would already include).
        assert len(out2["prior_history"]) == 1

    def test_engine_dependency_invariant_rules_engine_requires_architecture_scorer(self):
        from genesis_architect_pro.engine_bootstrap import ensure_registered
        from genesis_architect_pro.engine_registry import get_default_registry
        ensure_registered()
        reg = get_default_registry()
        descriptor = reg.require("rules_engine")
        assert "architecture_scorer" in descriptor.requires
