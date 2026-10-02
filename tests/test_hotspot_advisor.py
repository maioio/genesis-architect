"""
hotspot_advisor (G-HIGH-02): one prescribed refactoring action per
churn + coupling hotspot, with a score delta whose source is named.
"""

import json
import shutil
import subprocess
import sys

import pytest

from genesis_architect_pro import hotspot_advisor
from genesis_architect_pro.git_analyzer import CoupledPair
from genesis_architect_pro.hotspot_advisor import (
    COUPLED,
    GOD,
    HUB,
    MIN_COMMITS,
    VOCABULARY,
    Candidate,
    FileStats,
    HotspotAdvice,
    HotspotReport,
    _rebase_commits,
    _rebase_pairs,
    _repo_prefix,
    _window,
    advise,
    extraction_candidate,
    file_stats,
    find_hotspots,
    format_report,
    main,
)
from genesis_architect_pro.refactoring_planner import (
    RefactoringPlan,
    RefactorOperation,
    RefactorStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mod(imported_by=(), imports=(), fan_out=None):
    return {
        "imports": list(imports),
        "imported_by": list(imported_by),
        "fan_in": len(imported_by),
        "fan_out": len(imports) if fan_out is None else fan_out,
        "lines": 100,
    }


def _importers(n, tests=0):
    return [f"src/user_{i}.py" for i in range(n)] + [f"tests/test_{i}.py" for i in range(tests)]


def _hub_graph(path="src/hub.py", fan_in=11, tests=0, imports=("src/base.py",)):
    return {path: _mod(_importers(fan_in, tests), imports)}


def _god_graph(path="src/god.py", fan_out=16):
    return {path: _mod((), [f"src/dep_{i}.py" for i in range(fan_out)])}


def _pair(a, b, cochanges=5, confidence=0.8):
    return CoupledPair(file_a=a, file_b=b, cochanges=cochanges,
                       commits_a=cochanges, commits_b=cochanges, confidence=confidence)


def _stats(path, commits=MIN_COMMITS, authors=2, **more):
    out = {path: FileStats(commits=commits, authors=authors)}
    out.update(more)
    return out


def _step(id, rule, paths, score, tier=1):
    return RefactorStep(
        id=id, tier=tier, rule=rule, priority="HIGH", title=f"step {id}", why="w",
        operations=[RefactorOperation("MODIFY", p, "d") for p in paths],
        score_impact=score,
    )


def _only(advice):
    assert len(advice) == 1, advice
    return advice[0]


# ---------------------------------------------------------------------------
# Window phrase and message format
# ---------------------------------------------------------------------------

class TestWindow:
    @pytest.mark.parametrize("days, text", [
        (1, "1 day"), (6, "6 days"), (7, "1 week"), (56, "8 weeks"), (90, "90 days"),
    ])
    def test_weeks_only_when_whole(self, days, text):
        assert _window(days) == text


class TestMessage:
    def test_spec_example_shape(self):
        graph = {"src/billing.py": _mod(_importers(12), ["src/db.py"])}
        advice = _only(find_hotspots(
            _stats("src/billing.py", commits=47, authors=3), graph, [], days=56,
            candidate_for=lambda rel: Candidate("PaymentService", 10, 120, 400),
        ))
        assert advice.message() == (
            "This file changed 47 times in 8 weeks, has 3 authors, and a fan-in of 12. "
            "Extract `PaymentService` (120 of 400 lines) into its own module behind a "
            "stable interface (`src/billing_interface.py`), then point the 12 importers "
            "at the interface. "
            "Estimated score delta: +6 pts (planner rule hub-splitter for fan-in 12)."
        )

    def test_singular_nouns(self):
        advice = HotspotAdvice(path="a.py", days=7, commits=1, authors=1, fan_in=3,
                               fan_out=1, action=COUPLED, recommendation="R.",
                               score_delta=None, delta_basis="not derivable: x")
        assert advice.evidence() == ("This file changed 1 time in 1 week, has 1 author, "
                                     "and a fan-in of 3.")
        assert advice.delta_text() == "Estimated score delta: not derivable: x."

    def test_no_graph_says_fan_in_not_measured(self):
        advice = _only(find_hotspots(
            _stats("src/a.py", **{"src/b.py": FileStats(3, 2)}), {},
            [_pair("src/a.py", "src/b.py")], days=90,
        ))
        assert advice.fan_in is None and advice.fan_out is None
        assert "its fan-in was not measured (no import graph)" in advice.evidence()

    def test_to_dict_carries_the_message(self):
        advice = _only(find_hotspots(_stats("src/hub.py"), _hub_graph(), [], days=90))
        data = advice.to_dict()
        assert data["message"] == advice.message()
        assert data["action"] == HUB
        json.dumps(data)


# ---------------------------------------------------------------------------
# Thresholds and action rules
# ---------------------------------------------------------------------------

class TestThresholds:
    def test_min_commits_is_the_medium_churn_threshold(self):
        assert MIN_COMMITS == 8

    @pytest.mark.parametrize("commits, found", [(7, False), (8, True)])
    def test_commit_boundary(self, commits, found):
        advice = find_hotspots(_stats("src/hub.py", commits=commits), _hub_graph(), [],
                               days=90)
        assert bool(advice) is found

    @pytest.mark.parametrize("fan_in, found", [(10, False), (11, True)])
    def test_fan_in_boundary(self, fan_in, found):
        advice = find_hotspots(_stats("src/hub.py"), _hub_graph(fan_in=fan_in), [], days=90)
        assert bool(advice) is found

    def test_fan_in_counts_production_importers_only(self):
        graph = _hub_graph(fan_in=9, tests=5)
        assert find_hotspots(_stats("src/hub.py"), graph, [], days=90) == []

    def test_fan_in_falls_back_to_the_count_without_importer_list(self):
        graph = {"src/hub.py": {"imports": ["src/x.py"], "imported_by": [],
                                "fan_in": 12, "fan_out": 1}}
        assert _only(find_hotspots(_stats("src/hub.py"), graph, [], days=90)).fan_in == 12

    @pytest.mark.parametrize("fan_out, found", [(15, False), (16, True)])
    def test_fan_out_boundary(self, fan_out, found):
        advice = find_hotspots(_stats("src/god.py"), _god_graph(fan_out=fan_out), [],
                               days=90)
        assert bool(advice) is found

    @pytest.mark.parametrize("confidence, found", [(0.49, False), (0.5, True)])
    def test_coupling_confidence_boundary(self, confidence, found):
        advice = find_hotspots(_stats("src/a.py"), {},
                               [_pair("src/a.py", "src/b.py", confidence=confidence)],
                               days=90)
        assert bool(advice) is found

    def test_churn_without_coupling_is_not_a_hotspot(self):
        graph = {"src/a.py": _mod(_importers(3), ["src/b.py"])}
        assert find_hotspots(_stats("src/a.py", commits=60), graph, [], days=90) == []

    def test_file_missing_from_an_existing_graph_counts_as_uncoupled(self):
        advice = _only(find_hotspots(_stats("src/new.py"), _hub_graph(),
                                     [_pair("src/new.py", "src/other.py")], days=90))
        assert (advice.fan_in, advice.fan_out, advice.action) == (0, 0, COUPLED)

    @pytest.mark.parametrize("kwargs", [
        {"days": 0}, {"min_commits": 0}, {"min_confidence": 0}, {"min_confidence": 1.5},
        {"top_n": 0},
    ])
    def test_invalid_arguments_raise(self, kwargs):
        args = {"days": 90, **kwargs}
        with pytest.raises(ValueError):
            find_hotspots({}, {}, [], **args)


class TestActions:
    def test_hub_without_candidate(self):
        advice = _only(find_hotspots(_stats("src/hub.py"), _hub_graph(), [], days=90))
        assert advice.action == HUB
        assert advice.recommendation == (
            "Extract a stable interface from hub.py into `src/hub_interface.py` and "
            "point its 11 importers at it."
        )

    def test_top_level_file_has_no_dot_slash(self):
        advice = _only(find_hotspots(_stats("app.py"), _hub_graph("app.py"), [], days=90))
        assert "`app_interface.py`" in advice.recommendation
        assert "./" not in advice.recommendation

    def test_vocabulary_is_not_split_and_not_scored(self):
        graph = _hub_graph(imports=())
        advice = _only(find_hotspots(_stats("src/hub.py"), graph, [], days=90))
        assert advice.action == VOCABULARY
        assert "shared vocabulary, not a hub" in advice.recommendation
        assert advice.score_delta is None
        assert advice.delta_basis.startswith("not derivable: the planner does not score")

    def test_hub_wins_over_god(self):
        graph = {"src/x.py": _mod(_importers(11), [f"src/d{i}.py" for i in range(20)])}
        assert _only(find_hotspots(_stats("src/x.py"), graph, [], days=90)).action == HUB

    def test_god_without_candidate(self):
        advice = _only(find_hotspots(_stats("src/god.py"), _god_graph(), [], days=90))
        assert advice.action == GOD
        assert advice.recommendation == (
            "It imports 16 modules (the god-class threshold is 15). Split it by "
            "responsibility into `src/god_core.py` and `src/god_utils.py`, and reduce "
            "god.py to a thin coordinator."
        )

    def test_god_with_candidate(self):
        advice = _only(find_hotspots(
            _stats("src/god.py"), _god_graph(), [], days=90,
            candidate_for=lambda rel: Candidate("Engine", 5, 300, 900),
        ))
        assert "start by moving `Engine` (300 of 900 lines)" in advice.recommendation

    def test_candidate_lookup_only_for_hub_and_god(self):
        seen = []
        find_hotspots(_stats("src/a.py"), {}, [_pair("src/a.py", "src/b.py")], days=90,
                      candidate_for=lambda rel: seen.append(rel))
        assert seen == []

    @pytest.mark.parametrize("graph, phrase", [
        ({"src/a.py": _mod(), "src/b.py": _mod()}, "with no import between them"),
        ({"src/a.py": _mod((), ["src/b.py"]), "src/b.py": _mod(["src/a.py"])},
         "and one imports the other"),
        ({"src/b.py": _mod((), ["src/a.py"]), "src/a.py": _mod(["src/b.py"])},
         "and one imports the other"),
        ({}, "Check whether they share a hidden contract"),
    ])
    def test_coupled_depends_on_the_import_between(self, graph, phrase):
        advice = _only(find_hotspots(_stats("src/a.py"), graph,
                                     [_pair("src/a.py", "src/b.py", cochanges=6,
                                            confidence=0.75)], days=90))
        assert advice.action == COUPLED
        assert "changed together with `src/b.py` in 6 commits (confidence 0.75)" \
            in advice.recommendation
        assert phrase in advice.recommendation

    def test_coupled_counts_further_partners(self):
        pairs = [_pair("src/a.py", "src/b.py", confidence=0.9),
                 _pair("src/c.py", "src/a.py", confidence=0.6),
                 _pair("src/a.py", "src/d.py", confidence=0.7)]
        advice = _only(find_hotspots(_stats("src/a.py"), {}, pairs, days=90))
        assert [p.path for p in advice.partners] == ["src/b.py", "src/d.py", "src/c.py"]
        assert "(and 2 other files)" in advice.recommendation

    def test_partner_note_on_a_hub(self):
        advice = _only(find_hotspots(_stats("src/hub.py"), _hub_graph(),
                                     [_pair("src/hub.py", "src/q.py", confidence=0.66)],
                                     days=90))
        assert advice.action == HUB
        assert "It also changes together with `src/q.py` (confidence 0.66)." in advice.notes

    def test_single_author_note(self):
        advice = _only(find_hotspots(_stats("src/hub.py", authors=1), _hub_graph(), [],
                                     days=90))
        assert any("one author" in n for n in advice.notes)
        many = _only(find_hotspots(_stats("src/hub.py", authors=2), _hub_graph(), [],
                                   days=90))
        assert many.notes == []


class TestExclusions:
    def test_tests_are_never_hotspots(self):
        graph = _hub_graph("tests/test_hub.py")
        assert find_hotspots(_stats("tests/test_hub.py"), graph, [], days=90) == []

    @pytest.mark.parametrize("test_path", [
        "tests/test_a.py", "pkg/tests/helpers.py", "src/a_test.py", "test/x.py",
    ])
    def test_tests_are_never_partners(self, test_path):
        assert find_hotspots(_stats("src/a.py"), {}, [_pair("src/a.py", test_path)],
                             days=90) == []

    def test_absent_files_are_neither_hotspots_nor_partners(self):
        stats = _stats("src/a.py", **{"src/gone.py": FileStats(9, 2)})
        pairs = [_pair("src/a.py", "src/gone.py")]
        assert find_hotspots(stats, {}, pairs, days=90, present={"src/a.py"}) == []


# ---------------------------------------------------------------------------
# Score delta
# ---------------------------------------------------------------------------

class TestScoreDelta:
    @pytest.mark.parametrize("fan_in, delta", [(11, 5), (12, 6), (30, 12)])
    def test_hub_planner_rule(self, fan_in, delta):
        advice = _only(find_hotspots(_stats("src/hub.py"), _hub_graph(fan_in=fan_in), [],
                                     days=90))
        assert advice.score_delta == delta
        assert advice.delta_basis == f"planner rule hub-splitter for fan-in {fan_in}"

    @pytest.mark.parametrize("fan_out, delta", [(16, 8), (40, 15)])
    def test_god_planner_rule(self, fan_out, delta):
        advice = _only(find_hotspots(_stats("src/god.py"), _god_graph(fan_out=fan_out), [],
                                     days=90))
        assert advice.score_delta == delta
        assert advice.delta_basis == f"planner rule god-class-splitter for fan-out {fan_out}"

    def test_plan_step_with_the_matching_rule_wins(self):
        plan = RefactoringPlan(steps=[
            _step(1, "cycle-breaker", ["src/hub.py"], 8),
            _step(2, "hub-splitter", ["src/hub_interface.py", "src/hub.py",
                                      "[all importers]"], 3),
        ])
        advice = _only(find_hotspots(_stats("src/hub.py"), _hub_graph(), [], days=90,
                                     plan=plan))
        assert (advice.score_delta, advice.delta_basis) == (3, "plan step 2, hub-splitter")

    def test_highest_matching_step_then_lowest_id(self):
        plan = RefactoringPlan(steps=[
            _step(5, "hub-splitter", ["src/hub.py"], 4),
            _step(3, "hub-splitter", ["src/hub.py"], 4),
            _step(1, "hub-splitter", ["src/hub.py"], 2),
        ])
        advice = _only(find_hotspots(_stats("src/hub.py"), _hub_graph(), [], days=90,
                                     plan=plan))
        assert advice.delta_basis == "plan step 3, hub-splitter"

    def test_step_for_another_rule_is_not_used_for_a_hub(self):
        plan = RefactoringPlan(steps=[_step(1, "cycle-breaker", ["src/hub.py"], 8)])
        advice = _only(find_hotspots(_stats("src/hub.py"), _hub_graph(), [], days=90,
                                     plan=plan))
        assert advice.score_delta == 5
        assert advice.delta_basis.startswith("planner rule hub-splitter")

    def test_placeholder_paths_do_not_match(self):
        plan = RefactoringPlan(steps=[_step(1, "hub-splitter", ["[all importers]"], 9)])
        advice = _only(find_hotspots(_stats("[all importers]"),
                                     _hub_graph("[all importers]"), [], days=90, plan=plan))
        assert advice.delta_basis.startswith("planner rule")

    def test_coupled_is_not_derivable_and_mentions_other_steps(self):
        plan = RefactoringPlan(steps=[_step(2, "cycle-breaker", ["src/a.py"], 8)])
        advice = _only(find_hotspots(_stats("src/a.py"), {},
                                     [_pair("src/a.py", "src/b.py")], days=90, plan=plan))
        assert advice.score_delta is None
        assert advice.delta_basis == (
            "not derivable: no planner rule scores this action; plan step 2 "
            "(cycle-breaker, +8 pts) also changes this file"
        )

    def test_coupled_without_plan(self):
        advice = _only(find_hotspots(_stats("src/a.py"), {},
                                     [_pair("src/a.py", "src/b.py")], days=90))
        assert advice.delta_basis == "not derivable: no planner rule scores this action"


# ---------------------------------------------------------------------------
# Ordering and limits
# ---------------------------------------------------------------------------

class TestOrdering:
    def test_most_changed_first_then_fan_in_then_path(self):
        graph = {**_hub_graph("src/b.py", fan_in=11), **_hub_graph("src/a.py", fan_in=11),
                 **_hub_graph("src/c.py", fan_in=20), **_hub_graph("src/d.py", fan_in=11)}
        stats = {"src/a.py": FileStats(9, 2), "src/b.py": FileStats(9, 2),
                 "src/c.py": FileStats(9, 2), "src/d.py": FileStats(30, 2)}
        advice = find_hotspots(stats, graph, [], days=90)
        assert [a.path for a in advice] == ["src/d.py", "src/c.py", "src/a.py", "src/b.py"]

    def test_top_n(self):
        graph = {**_hub_graph("src/a.py"), **_hub_graph("src/b.py")}
        stats = {"src/a.py": FileStats(9, 2), "src/b.py": FileStats(10, 2)}
        assert [a.path for a in find_hotspots(stats, graph, [], days=90, top_n=1)] \
            == ["src/b.py"]


# ---------------------------------------------------------------------------
# Git inputs
# ---------------------------------------------------------------------------

class TestFileStats:
    def test_counts_commits_and_distinct_authors(self):
        commits = [
            {"author": "ann", "files": ["a.py", "b.py"]},
            {"author": "bob", "files": ["a.py"]},
            {"author": "ann", "files": ["a.py", "a.py"]},
            {"author": "", "files": ["b.py"]},
        ]
        stats = file_stats(commits)
        assert stats["a.py"] == FileStats(commits=3, authors=2)
        assert stats["b.py"] == FileStats(commits=2, authors=1)

    def test_normalizes_backslashes(self):
        assert set(file_stats([{"author": "a", "files": ["src\\x.py"]}])) == {"src/x.py"}


class TestRebase:
    def test_strips_the_prefix_and_drops_outside_files(self):
        commits = [{"author": "a", "files": ["proj/a.py", "other/z.py"]},
                   {"author": "a", "files": ["other/only.py"]}]
        assert _rebase_commits(commits, "proj/") == [{"author": "a", "files": ["a.py"]}]

    def test_empty_prefix_keeps_everything(self):
        commits = [{"author": "a", "files": ["a.py", "b/c.py"]}]
        assert _rebase_commits(commits, "") == commits

    def test_prefix_is_not_a_bare_string_prefix(self):
        commits = [{"author": "a", "files": ["project/a.py"]}]
        assert _rebase_commits(commits, "proj/") == []

    def test_pairs(self):
        pairs = [_pair("proj/a.py", "proj/b.py"), _pair("proj/a.py", "other/z.py")]
        out = _rebase_pairs(pairs, "proj/")
        assert [(p.file_a, p.file_b) for p in out] == [("a.py", "b.py")]
        assert out[0].confidence == pairs[0].confidence


# ---------------------------------------------------------------------------
# Extraction candidate
# ---------------------------------------------------------------------------

class TestExtractionCandidate:
    def _write(self, tmp_path, name, text):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return name

    def test_largest_class(self, tmp_path):
        rel = self._write(tmp_path, "m.py", (
            "class Small:\n    a = 1\n\n"
            "class Big:\n    a = 1\n    b = 2\n    c = 3\n\n"
            "def helper():\n    return 1\n"
        ))
        assert extraction_candidate(tmp_path, rel) == Candidate("Big", 4, 4, 10)

    def test_tie_goes_to_the_first(self, tmp_path):
        rel = self._write(tmp_path, "m.py",
                          "class A:\n    x = 1\n\nclass B:\n    y = 1\n")
        assert extraction_candidate(tmp_path, rel).name == "A"

    def test_a_lone_class_is_not_a_candidate(self, tmp_path):
        rel = self._write(tmp_path, "m.py", "import os\n\nclass Only:\n    x = 1\n")
        assert extraction_candidate(tmp_path, rel) is None

    def test_no_class(self, tmp_path):
        rel = self._write(tmp_path, "m.py", "def a():\n    pass\n\ndef b():\n    pass\n")
        assert extraction_candidate(tmp_path, rel) is None

    @pytest.mark.parametrize("name, text", [
        ("m.js", "class A {}\nclass B {}\n"),
        ("broken.py", "class A:\n  def (\n"),
    ])
    def test_unparseable_or_not_python(self, tmp_path, name, text):
        assert extraction_candidate(tmp_path, self._write(tmp_path, name, text)) is None

    def test_missing_file(self, tmp_path):
        assert extraction_candidate(tmp_path, "nope.py") is None

    def test_outside_root(self, tmp_path):
        self._write(tmp_path, "outside.py", "class A:\n    x = 1\n\nclass B:\n    y = 1\n")
        root = tmp_path / "root"
        root.mkdir()
        assert extraction_candidate(root, "../outside.py") is None


# ---------------------------------------------------------------------------
# advise() with git mocked
# ---------------------------------------------------------------------------

class TestAdvise:
    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        (tmp_path / "src").mkdir()
        for name in ("hub.py", "b.py"):
            (tmp_path / "src" / name).write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(hotspot_advisor, "_is_git_repo", lambda p: True)
        monkeypatch.setattr(hotspot_advisor, "_repo_prefix", lambda p: "")
        return tmp_path

    def _log(self, monkeypatch, commits):
        monkeypatch.setattr(hotspot_advisor, "_git_log",
                            lambda root, days, cache_dir=None: commits)

    def test_not_a_directory(self, tmp_path):
        with pytest.raises(ValueError, match="not a directory"):
            advise(tmp_path / "missing")

    def test_not_a_git_repo_is_an_error_not_a_clean_result(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hotspot_advisor, "_is_git_repo", lambda p: False)
        with pytest.raises(ValueError, match="not a git repository"):
            advise(tmp_path)

    def test_invalid_days_before_touching_the_disk(self, tmp_path):
        with pytest.raises(ValueError, match="days"):
            advise(tmp_path / "missing", days=0)

    def test_no_commits_warns(self, repo, monkeypatch):
        self._log(monkeypatch, [])
        report = advise(repo, modules={})
        assert report.hotspots == []
        assert "No commits touched this project" in report.warnings[0]

    def test_hub_found_and_deleted_files_ignored(self, repo, monkeypatch):
        commits = [{"author": f"a{i % 3}", "files": ["src/hub.py", "src/gone.py"]}
                   for i in range(9)]
        self._log(monkeypatch, commits)
        graph = {**_hub_graph("src/hub.py"), **_hub_graph("src/gone.py")}
        report = advise(repo, modules=graph)
        assert [h.path for h in report.hotspots] == ["src/hub.py"]
        hub = report.hotspots[0]
        assert (hub.commits, hub.authors, hub.action) == (9, 3, HUB)
        assert hub.partners == []          # src/gone.py is not on disk
        assert report.files_examined == 2

    def test_no_graph_warns_and_finds_coupling(self, repo, monkeypatch):
        commits = [{"author": "a", "files": ["src/hub.py", "src/b.py"]} for _ in range(8)]
        self._log(monkeypatch, commits)
        report = advise(repo, modules={})
        assert any("No import graph" in w for w in report.warnings)
        assert {h.path for h in report.hotspots} == {"src/hub.py", "src/b.py"}
        assert all(h.action == COUPLED for h in report.hotspots)

    def test_graph_is_read_when_not_injected(self, repo, monkeypatch):
        self._log(monkeypatch, [{"author": "a", "files": ["src/hub.py"]}] * 8)
        calls = []
        monkeypatch.setattr(hotspot_advisor, "_graph_modules",
                            lambda root, language: calls.append(language) or _hub_graph())
        report = advise(repo, language="python")
        assert calls == ["python"]
        assert report.hotspots[0].action == HUB

    def test_bulk_commits_do_not_create_coupling(self, repo, monkeypatch):
        bulk = ["src/hub.py", "src/b.py"] + [f"other/f{i}.py" for i in range(40)]
        self._log(monkeypatch, [{"author": "a", "files": bulk} for _ in range(8)])
        monkeypatch.setattr(hotspot_advisor, "_repo_prefix", lambda p: "")
        assert advise(repo, modules={}).hotspots == []


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
class TestRealRepository:
    def _git(self, cwd, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=cwd, check=True, capture_output=True)

    def test_prefix_and_rebasing_in_a_subdirectory(self, tmp_path):
        self._git(tmp_path, "init", "-q")
        proj = tmp_path / "proj"
        proj.mkdir()
        (tmp_path / "outside.py").write_text("0\n", encoding="utf-8")
        for i in range(8):
            for name in ("a.py", "b.py"):
                (proj / name).write_text(f"v = {i}\n", encoding="utf-8")
            (tmp_path / "outside.py").write_text(f"{i}\n", encoding="utf-8")
            self._git(tmp_path, "add", "-A")
            self._git(tmp_path, "commit", "-q", "-m", f"c{i}")

        assert _repo_prefix(proj) == "proj/"
        assert _repo_prefix(tmp_path) == ""

        report = advise(proj, modules={})
        assert {h.path for h in report.hotspots} == {"a.py", "b.py"}
        assert report.files_examined == 2
        assert report.hotspots[0].partners[0].path in {"a.py", "b.py"}
        assert not (proj / ".genesis").exists()


# ---------------------------------------------------------------------------
# Output and CLI
# ---------------------------------------------------------------------------

class TestFormat:
    def test_empty_report(self):
        text = format_report(HotspotReport(days=56, files_examined=4))
        assert "last 8 weeks, 4 changed file(s) examined" in text
        assert "No hotspots" in text

    def test_report_is_ascii(self):
        advice = find_hotspots(_stats("src/hub.py", authors=1), _hub_graph(),
                               [_pair("src/hub.py", "src/q.py")], days=90)
        text = format_report(HotspotReport(days=90, hotspots=advice, warnings=["w"]))
        assert text.isascii()
        assert "1. src/hub.py  [hub]" in text
        assert "Note: Every change came from one author" in text
        assert "WARNING: w" in text


class TestCli:
    def _run(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["hotspot_advisor", *map(str, args)])
        main()

    def _exit(self, monkeypatch, *args):
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, *args)
        return exc.value.code

    def _fake_advise(self, monkeypatch, report=None):
        seen = {}

        def fake(path, **kwargs):
            seen.update(kwargs, path=path)
            return report or HotspotReport(days=kwargs["days"])
        monkeypatch.setattr(hotspot_advisor, "advise", fake)
        return seen

    def test_not_a_directory_exits_2(self, tmp_path, monkeypatch, capsys):
        assert self._exit(monkeypatch, tmp_path / "missing") == 2
        assert "not a directory" in capsys.readouterr().err

    def test_not_a_git_repo_exits_2(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(hotspot_advisor, "_is_git_repo", lambda p: False)
        assert self._exit(monkeypatch, tmp_path) == 2
        assert "not a git repository" in capsys.readouterr().err

    def test_invalid_days_exits_2(self, tmp_path, monkeypatch, capsys):
        assert self._exit(monkeypatch, tmp_path, "--days", "0") == 2
        assert "days must be at least 1" in capsys.readouterr().err

    @pytest.mark.parametrize("content", ["not json", '{"steps": "x"}'])
    def test_bad_plan_exits_2(self, tmp_path, monkeypatch, capsys, content):
        plan = tmp_path / "plan.json"
        plan.write_text(content, encoding="utf-8")
        self._fake_advise(monkeypatch)
        assert self._exit(monkeypatch, tmp_path, "--plan", plan) == 2
        assert "could not load the plan plan.json" in capsys.readouterr().err

    def test_missing_plan_exits_2(self, tmp_path, monkeypatch, capsys):
        self._fake_advise(monkeypatch)
        assert self._exit(monkeypatch, tmp_path, "--plan", tmp_path / "nope.json") == 2

    def test_plan_is_loaded_and_passed(self, tmp_path, monkeypatch):
        plan = RefactoringPlan(steps=[_step(1, "hub-splitter", ["src/hub.py"], 9)],
                               tier1_count=1, total_score_impact=9)
        path = tmp_path / "plan.json"
        path.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
        seen = self._fake_advise(monkeypatch)
        self._run(monkeypatch, tmp_path, "--plan", path, "--days", "56", "--top", "3")
        assert seen["plan"].steps[0].score_impact == 9
        assert (seen["days"], seen["top_n"]) == (56, 3)

    def test_json_output(self, tmp_path, monkeypatch, capsys):
        advice = find_hotspots(_stats("src/hub.py"), _hub_graph(), [], days=90)
        self._fake_advise(monkeypatch, HotspotReport(days=90, hotspots=advice))
        self._run(monkeypatch, tmp_path, "--json")
        data = json.loads(capsys.readouterr().out)
        assert data["hotspots"][0]["path"] == "src/hub.py"
        assert data["hotspots"][0]["message"].startswith("This file changed 8 times")
        assert "authors" in data["hotspots"][0]
        assert isinstance(data["hotspots"][0]["authors"], int)

    def test_text_output(self, tmp_path, monkeypatch, capsys):
        self._fake_advise(monkeypatch)
        self._run(monkeypatch, tmp_path)
        assert "No hotspots" in capsys.readouterr().out

    def test_unencodable_console_exits_2(self, tmp_path, monkeypatch, capsys):
        self._fake_advise(monkeypatch)
        real_print = print

        def raiser(*args, **kwargs):
            if kwargs.get("file") is None:
                raise UnicodeEncodeError("cp1252", "x", 0, 1, "boom")
            real_print(*args, **kwargs)
        monkeypatch.setattr(hotspot_advisor, "print", raiser, raising=False)
        assert self._exit(monkeypatch, tmp_path) == 2
        assert "use --json" in capsys.readouterr().err
