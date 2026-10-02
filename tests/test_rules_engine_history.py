"""
rules_engine history rules (G-HIGH-01): bus_factor_min,
score_not_declining_over and max_change_coupling.

Missing data must be skipped (a note), never passed; an unparseable rule
value must fail, never be skipped.
"""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from genesis_architect_pro.rules_engine import (
    _gather_history_facts,
    evaluate,
    parse_bus_factor,
    parse_window_days,
    run_check,
    score_trend,
)

AS_OF = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _ago(days: int) -> str:
    return (AS_OF - timedelta(days=days)).isoformat()


def _result(report, rule):
    matches = [r for r in report.results if r.rule == rule]
    assert len(matches) == 1, f"expected one {rule} result, got {report.results}"
    return matches[0]


def _skipped(report, rule) -> bool:
    return any(n.startswith(f"{rule}: skipped") for n in report.notes)


def _pair(a, b, confidence, cochanges=5):
    return {"file_a": a, "file_b": b, "cochanges": cochanges,
            "commits_a": cochanges, "commits_b": cochanges, "confidence": confidence}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

class TestParsers:
    @pytest.mark.parametrize("value,expected", [
        (2, 2), ("2", 2), ("2_per_module", 2), ("3 per_module", 3), ("1_PER_MODULE", 1),
    ])
    def test_bus_factor_forms(self, value, expected):
        assert parse_bus_factor(value) == expected

    @pytest.mark.parametrize("value", ["two", "2_per_file", True, 0, -1, None])
    def test_bus_factor_rejects(self, value):
        with pytest.raises(ValueError):
            parse_bus_factor(value)

    @pytest.mark.parametrize("value,expected", [
        ("4_weeks", 28), ("1_week", 7), ("28_days", 28), ("10days", 10), ("2 weeks", 14), (4, 28),
    ])
    def test_window_forms(self, value, expected):
        assert parse_window_days(value) == expected

    @pytest.mark.parametrize("value", ["month", "4_months", True, 0, "0_days", None])
    def test_window_rejects(self, value):
        with pytest.raises(ValueError):
            parse_window_days(value)


# ---------------------------------------------------------------------------
# bus_factor_min
# ---------------------------------------------------------------------------

class TestBusFactorRule:
    def test_passes_when_every_file_has_enough_authors(self):
        report = evaluate({"bus_factor_min": "2_per_module"},
                          {"bus_factor_by_file": {"a.py": 2, "b.py": 3}})
        r = _result(report, "bus_factor_min")
        assert r.passed and r.actual == 0 and r.expected == 2

    def test_fails_and_names_the_worst_files(self):
        report = evaluate({"bus_factor_min": 2},
                          {"bus_factor_by_file": {"a.py": 1, "b.py": 2, "c.py": 1}})
        r = _result(report, "bus_factor_min")
        assert not r.passed and not report.passed
        assert r.actual == 2
        assert "a.py (1)" in r.message and "c.py (1)" in r.message
        assert "b.py" not in r.message

    def test_no_history_is_skipped_not_passed(self):
        report = evaluate({"bus_factor_min": 2}, {"bus_factor_by_file": None})
        assert report.results == []
        assert _skipped(report, "bus_factor_min")

    def test_ignore_globs_exempt_files(self):
        facts = {"bus_factor_by_file": {"src/a.py": 2, "docs/notes.md": 1}}
        report = evaluate({"bus_factor_min": 2, "bus_factor_ignore": ["docs/*"]}, facts)
        assert _result(report, "bus_factor_min").passed
        report = evaluate({"bus_factor_min": 2, "bus_factor_ignore": "*.md"}, facts)
        assert _result(report, "bus_factor_min").passed

    def test_everything_ignored_is_skipped(self):
        report = evaluate({"bus_factor_min": 2, "bus_factor_ignore": ["*"]},
                          {"bus_factor_by_file": {"a.py": 1}})
        assert report.results == [] and _skipped(report, "bus_factor_min")

    def test_invalid_value_fails_closed(self):
        report = evaluate({"bus_factor_min": "lots"}, {"bus_factor_by_file": {"a.py": 5}})
        r = _result(report, "bus_factor_min")
        assert not r.passed and "invalid rule value" in r.message


# ---------------------------------------------------------------------------
# score_not_declining_over
# ---------------------------------------------------------------------------

class TestScoreTrend:
    def test_decline_over_window_fails(self):
        facts = {"as_of": AS_OF.isoformat(), "score_history": [
            {"timestamp": _ago(35), "total": 80},
            {"timestamp": _ago(3), "total": 75},
        ]}
        report = evaluate({"score_not_declining_over": "4_weeks"}, facts)
        r = _result(report, "score_not_declining_over")
        assert not r.passed and r.actual == -5
        assert "75 vs 80" in r.message

    def test_live_score_is_the_latest_point(self):
        facts = {"as_of": AS_OF.isoformat(), "architecture_score": 82, "score_history": [
            {"timestamp": _ago(35), "total": 80},
            {"timestamp": _ago(3), "total": 75},
        ]}
        r = _result(evaluate({"score_not_declining_over": "4_weeks"}, facts),
                    "score_not_declining_over")
        assert r.passed and r.actual == 2

    def test_baseline_is_newest_record_before_window_start(self):
        history = [
            {"timestamp": _ago(60), "total": 90},
            {"timestamp": _ago(30), "total": 70},
            {"timestamp": _ago(1), "total": 72},
        ]
        trend = score_trend(history, 28, as_of=AS_OF)
        assert trend["baseline"] == 70 and trend["latest"] == 72 and trend["delta"] == 2

    def test_tolerance_allows_small_drop(self):
        facts = {"as_of": AS_OF.isoformat(), "score_history": [
            {"timestamp": _ago(30), "total": 80},
            {"timestamp": _ago(2), "total": 78},
        ]}
        report = evaluate({"score_not_declining_over": "4_weeks",
                           "score_decline_tolerance": 3}, facts)
        assert _result(report, "score_not_declining_over").passed
        report = evaluate({"score_not_declining_over": "4_weeks"}, facts)
        assert not _result(report, "score_not_declining_over").passed

    def test_partial_coverage_is_disclosed(self):
        facts = {"as_of": AS_OF.isoformat(), "score_history": [
            {"timestamp": _ago(10), "total": 70},
            {"timestamp": _ago(1), "total": 71},
        ]}
        r = _result(evaluate({"score_not_declining_over": "4_weeks"}, facts),
                    "score_not_declining_over")
        assert r.passed and "covers only 10 of 28 days" in r.message

    def test_empty_history_is_skipped(self):
        report = evaluate({"score_not_declining_over": "4_weeks"},
                          {"as_of": AS_OF.isoformat(), "score_history": []})
        assert report.results == [] and _skipped(report, "score_not_declining_over")

    def test_single_point_without_live_score_is_skipped(self):
        report = evaluate({"score_not_declining_over": "4_weeks"},
                          {"as_of": AS_OF.isoformat(),
                           "score_history": [{"timestamp": _ago(40), "total": 80}]})
        assert report.results == [] and _skipped(report, "score_not_declining_over")

    def test_bad_records_are_ignored(self):
        history = [
            {"timestamp": "not a date", "total": 10},
            {"timestamp": _ago(30), "total": "high"},
            {"timestamp": _ago(30), "total": True},
            "garbage",
            {"timestamp": _ago(29), "total": 80},
            {"timestamp": _ago(1), "total": 80},
        ]
        trend = score_trend(history, 28, as_of=AS_OF)
        assert trend["baseline"] == 80 and trend["delta"] == 0

    def test_naive_and_z_timestamps_are_utc(self):
        history = [
            {"timestamp": "2026-08-01T00:00:00", "total": 60},
            {"timestamp": "2026-09-27T00:00:00Z", "total": 65},
        ]
        trend = score_trend(history, 28, as_of=AS_OF)
        assert trend["delta"] == 5

    def test_as_of_defaults_to_latest_record(self):
        history = [{"timestamp": _ago(40), "total": 80}, {"timestamp": _ago(5), "total": 70}]
        trend = score_trend(history, 28)
        assert trend["baseline"] == 80 and trend["latest"] == 70

    def test_future_records_after_as_of_are_ignored(self):
        history = [{"timestamp": _ago(40), "total": 80},
                   {"timestamp": _ago(5), "total": 81},
                   {"timestamp": (AS_OF + timedelta(days=3)).isoformat(), "total": 10}]
        assert score_trend(history, 28, as_of=AS_OF)["latest"] == 81

    @pytest.mark.parametrize("rules", [
        {"score_not_declining_over": "a while"},
        {"score_not_declining_over": "4_weeks", "score_decline_tolerance": -1},
        {"score_not_declining_over": "4_weeks", "score_decline_tolerance": "some"},
    ])
    def test_invalid_values_fail_closed(self, rules):
        report = evaluate(rules, {"as_of": AS_OF.isoformat(), "score_history": []})
        r = _result(report, "score_not_declining_over")
        assert not r.passed and "invalid rule value" in r.message


# ---------------------------------------------------------------------------
# max_change_coupling
# ---------------------------------------------------------------------------

class TestChangeCouplingRule:
    def test_passes_under_threshold(self):
        facts = {"change_coupling": [_pair("a.py", "b.py", 0.4)]}
        r = _result(evaluate({"max_change_coupling": 0.5}, facts), "max_change_coupling")
        assert r.passed and r.actual == 0.4

    def test_fails_and_names_offenders(self):
        facts = {"change_coupling": [_pair("a.py", "b.py", 0.9), _pair("c.py", "d.py", 0.3)]}
        r = _result(evaluate({"max_change_coupling": 0.5}, facts), "max_change_coupling")
        assert not r.passed and r.actual == 0.9
        assert "a.py <-> b.py (0.90)" in r.message and "c.py" not in r.message

    def test_test_files_ignored_by_default(self):
        facts = {"change_coupling": [
            _pair("src/app.py", "tests/test_app.py", 1.0),
            _pair("src/app.py", "src/app.test.js", 1.0),
            _pair("pkg/tests/fixtures.py", "src/app.py", 1.0),
        ]}
        r = _result(evaluate({"max_change_coupling": 0.5}, facts), "max_change_coupling")
        assert r.passed and r.actual == 0.0

    def test_custom_ignore_replaces_defaults(self):
        facts = {"change_coupling": [_pair("src/app.py", "tests/test_app.py", 1.0),
                                     _pair("schema.sql", "src/model.py", 1.0)]}
        r = _result(evaluate({"max_change_coupling": 0.5, "change_coupling_ignore": ["*.sql"]},
                             facts), "max_change_coupling")
        assert not r.passed and "tests/test_app.py" in r.message
        assert "schema.sql" not in r.message

    def test_min_cochanges_filters_noise(self):
        facts = {"change_coupling": [_pair("a.py", "b.py", 1.0, cochanges=2)]}
        assert _result(evaluate({"max_change_coupling": 0.5}, facts),
                       "max_change_coupling").passed
        r = _result(evaluate({"max_change_coupling": 0.5, "change_coupling_min_cochanges": 2},
                             facts), "max_change_coupling")
        assert not r.passed

    def test_no_history_is_skipped(self):
        report = evaluate({"max_change_coupling": 0.5}, {"change_coupling": None})
        assert report.results == [] and _skipped(report, "max_change_coupling")

    def test_empty_pair_list_is_a_real_pass(self):
        r = _result(evaluate({"max_change_coupling": 0.5}, {"change_coupling": []}),
                    "max_change_coupling")
        assert r.passed and r.actual == 0.0

    @pytest.mark.parametrize("value", [1.5, -0.1, "high", True, None])
    def test_invalid_value_fails_closed(self, value):
        report = evaluate({"max_change_coupling": value},
                          {"change_coupling": [_pair("a.py", "b.py", 0.1)]})
        r = _result(report, "max_change_coupling")
        assert not r.passed and "invalid rule value" in r.message


# ---------------------------------------------------------------------------
# Gathering from a real git repository
# ---------------------------------------------------------------------------

def _git(root: Path, *args: str):
    subprocess.run(["git", *args], cwd=str(root), capture_output=True, check=False)


def _init(root: Path):
    _git(root, "init")
    _git(root, "config", "user.email", "alice@example.com")
    _git(root, "config", "user.name", "Alice")


def _commit(root: Path, message: str, files: dict[str, str], author: str = "Alice"):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", f"user.name={author}", "-c", f"user.email={author.lower()}@example.com",
         "commit", "-m", message)


class TestGatherHistoryFacts:
    def test_no_history_rules_gathers_nothing(self, tmp_path):
        assert _gather_history_facts(tmp_path, {}) == {}

    def test_non_git_directory_yields_none(self, tmp_path):
        facts = _gather_history_facts(tmp_path, {"bus_factor_min": 2, "max_change_coupling": 0.5})
        assert facts["bus_factor_by_file"] is None
        assert facts["change_coupling"] is None
        report = evaluate({"bus_factor_min": 2, "max_change_coupling": 0.5}, facts)
        assert report.results == []
        assert _skipped(report, "bus_factor_min") and _skipped(report, "max_change_coupling")

    def test_git_authorship_and_coupling(self, tmp_path):
        _init(tmp_path)
        for i in range(3):
            _commit(tmp_path, f"feat: step {i}", {"a.py": f"a = {i}\n", "b.py": f"b = {i}\n"})
        _commit(tmp_path, "feat: bob edits a", {"a.py": "a = 99\n"}, author="Bob")
        _commit(tmp_path, "chore: temp file", {"gone.py": "x = 1\n"})
        _git(tmp_path, "rm", "-q", "gone.py")
        _git(tmp_path, "commit", "-m", "chore: remove temp file")

        facts = _gather_history_facts(tmp_path, {"bus_factor_min": 2, "max_change_coupling": 0.5})
        assert facts["bus_factor_by_file"] == {"a.py": 2, "b.py": 1}
        pairs = {(p["file_a"], p["file_b"]): p for p in facts["change_coupling"]}
        assert pairs[("a.py", "b.py")]["cochanges"] == 3
        assert pairs[("a.py", "b.py")]["confidence"] == 0.75

        report = evaluate({"bus_factor_min": 2, "max_change_coupling": 0.5}, facts)
        assert not _result(report, "bus_factor_min").passed
        assert not _result(report, "max_change_coupling").passed

    def test_gathering_writes_nothing(self, tmp_path):
        _init(tmp_path)
        _commit(tmp_path, "feat: one", {"a.py": "a = 1\n"})
        before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")
                        if ".git" not in p.parts)
        _gather_history_facts(tmp_path, {"bus_factor_min": 2, "max_change_coupling": 0.5,
                                         "score_not_declining_over": "4_weeks"})
        after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")
                       if ".git" not in p.parts)
        assert before == after

    def test_score_history_file_is_read(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "score_history.jsonl").write_text(
            json.dumps({"timestamp": _ago(30), "total": 80}) + "\n"
            + json.dumps({"timestamp": _ago(1), "total": 70}) + "\n",
            encoding="utf-8")
        facts = _gather_history_facts(tmp_path, {"score_not_declining_over": "4_weeks"})
        assert [r["total"] for r in facts["score_history"]] == [80, 70]
        assert facts["as_of"]


class TestRunCheckWiring:
    def test_rules_file_history_rule_reaches_evaluation(self, tmp_path):
        _init(tmp_path)
        _commit(tmp_path, "feat: solo", {"app.py": "def main():\n    return 1\n"})
        (tmp_path / ".genesis").mkdir()
        (tmp_path / ".genesis" / "rules.json").write_text(
            json.dumps({"bus_factor_min": "2_per_module"}), encoding="utf-8")
        report = run_check(tmp_path)
        r = _result(report, "bus_factor_min")
        assert not r.passed and "app.py (1)" in r.message
        assert report.hard_failure
