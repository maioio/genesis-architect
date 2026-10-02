"""
prompt_export (G-MED-04, partial G-MED-05): offline, budget-packed refactoring
prompts for plan steps that were selected explicitly.
"""

import io
import json
import os
import re
import sys
from pathlib import Path

import pytest

from genesis_architect_pro import prompt_export
from genesis_architect_pro.prompt_budget import (
    ABBREVIATED,
    CONSUMER_REF,
    CORE_TARGET,
    DROPPED,
    FULL,
    IMPORTANT_CONTEXT,
    estimate_tokens,
)
from genesis_architect_pro.prompt_export import (
    CONSTRAINTS,
    EXISTS,
    MAX_CONSUMERS,
    WOULD_WRITE,
    WRITTEN,
    _NO_FILES,
    _safe_rel,
    _step_files,
    export_prompts,
    format_step_list,
    main,
    plan_from_dict,
    prompt_filename,
    select_steps,
    step_fingerprint,
    write_prompts,
)
from genesis_architect_pro.refactoring_planner import (
    RefactoringPlan,
    RefactorOperation,
    RefactorStep,
)


GENERATED_AT = "2026-09-28T00:00:00+00:00"
MODULES = {"src/a.py": {"imported_by": ["src/c0.py", "src/c1.py", "src/c2.py"]}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _touch(root: Path, rel: str, content: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _lines(n: int, prefix: str) -> str:
    """n assignment lines; none of them is an export line."""
    return "".join(f"{prefix}{i} = {i}\n" for i in range(n))


def _op(type_: str, path: str, description: str = "do it") -> RefactorOperation:
    return RefactorOperation(type=type_, path=path, description=description)


def _step(id_: int, ops, rule: str = "hub-splitter", title: str | None = None,
          **kw) -> RefactorStep:
    return RefactorStep(id=id_, tier=kw.pop("tier", 1), rule=rule,
                        priority=kw.pop("priority", "HIGH"),
                        title=title if title is not None else f"Step {id_}",
                        why=kw.pop("why", "because"), operations=list(ops), **kw)


def _plan(*steps: RefactorStep, generated_at: str = GENERATED_AT) -> RefactoringPlan:
    # Built directly, not through plan_from_dict, so duplicate ids are allowed.
    return RefactoringPlan(
        steps=list(steps),
        tier1_count=sum(1 for s in steps if s.tier == 1),
        tier2_count=sum(1 for s in steps if s.tier == 2),
        total_score_impact=sum(s.score_impact for s in steps),
        generated_at=generated_at,
    )


def _full_plan() -> RefactoringPlan:
    return _plan(_step(1, [_op("MODIFY", "src/a.py"), _op("DELETE", "src/old.py"),
                           _op("CREATE", "src/new.py")]))


def _one(plan: RefactoringPlan, root: Path, **kw):
    return export_prompts(plan, root, "all", **kw).prompts[0]


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "proj"
    _touch(root, "src/a.py", "def a():\n    return 1\n")
    _touch(root, "src/old.py", _lines(40, "old_"))
    for i in range(3):
        _touch(root, f"src/c{i}.py", _lines(60, f"c{i}_"))
    return root


# ---------------------------------------------------------------------------
# Fingerprints and the approval gate
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_stable_when_the_id_changes(self):
        ops = [_op("MODIFY", "src/a.py")]
        assert step_fingerprint(_step(1, ops, title="T")) == step_fingerprint(_step(7, ops, title="T"))

    def test_changes_when_an_operation_changes(self):
        a = _step(1, [_op("MODIFY", "src/a.py")], title="T")
        b = _step(1, [_op("MODIFY", "src/b.py")], title="T")
        assert step_fingerprint(a) != step_fingerprint(b)

    def test_is_eight_hex_characters(self):
        assert re.fullmatch(r"[0-9a-f]{8}", step_fingerprint(_step(1, [])))


class TestSelectSteps:
    @pytest.fixture
    def plan(self):
        return _plan(*(_step(i, [_op("MODIFY", f"src/m{i}.py")]) for i in (1, 2, 3)))

    @pytest.mark.parametrize("selection", ["all", "ALL", " all "])
    def test_all_selects_every_step(self, plan, selection):
        assert [s.id for s in select_steps(plan, selection)] == [1, 2, 3]

    @pytest.mark.parametrize("selection", ["3,1", [3, 1], ("3", " 1 ")])
    def test_steps_come_back_in_plan_order(self, plan, selection):
        assert [s.id for s in select_steps(plan, selection)] == [1, 3]

    def test_fingerprint_is_case_insensitive(self, plan):
        fp = step_fingerprint(plan.steps[1])
        assert [s.id for s in select_steps(plan, fp.upper())] == [2]

    def test_unknown_token_names_the_available_ids(self, plan):
        with pytest.raises(ValueError, match=re.escape("No step matches 99 (step ids: 1, 2, 3).")):
            select_steps(plan, "99")

    def test_unknown_token_on_an_empty_plan(self):
        with pytest.raises(ValueError, match="none: the plan has no steps"):
            select_steps(_plan(), "1")

    @pytest.mark.parametrize("selection", ["", None, " , ", []])
    def test_empty_selection_is_refused(self, plan, selection):
        with pytest.raises(ValueError, match="No steps selected"):
            select_steps(plan, selection)

    def test_all_cannot_be_combined(self, plan):
        with pytest.raises(ValueError, match="'all' selects every step"):
            select_steps(plan, "all,99")

    def test_shared_id_is_ambiguous_but_fingerprint_works(self):
        first = _step(1, [_op("MODIFY", "src/a.py")], title="A")
        second = _step(1, [_op("MODIFY", "src/b.py")], title="B")
        plan = _plan(first, second)
        with pytest.raises(ValueError, match="matches more than one step"):
            select_steps(plan, "1")
        assert select_steps(plan, step_fingerprint(second)) == [second]

    def test_shared_fingerprint_is_ambiguous_but_id_works(self):
        ops = [_op("MODIFY", "src/a.py")]
        plan = _plan(_step(1, ops, title="T"), _step(2, ops, title="T"))
        with pytest.raises(ValueError, match="matches more than one step"):
            select_steps(plan, step_fingerprint(plan.steps[0]))
        assert [s.id for s in select_steps(plan, "2")] == [2]

    def test_non_ascii_digit_is_not_an_id(self, plan):
        # "\u00b2".isdigit() is True; int() would accept it too.
        with pytest.raises(ValueError, match="No step matches"):
            select_steps(plan, "\u00b2")


# ---------------------------------------------------------------------------
# Plan files
# ---------------------------------------------------------------------------

MINIMAL_STEP = {"id": 1, "tier": 1, "rule": "r", "priority": "HIGH", "title": "t"}


def _with(**changes) -> dict:
    step = dict(MINIMAL_STEP)
    step.update(changes)
    return {"steps": [step]}


class TestPlanFromDict:
    def test_json_round_trip(self):
        plan = _plan(_step(1, [_op("MODIFY", "src/a.py")], score_impact=4, confidence=0.6,
                           confidence_basis="b"),
                     _step(2, [_op("DELETE", "src/old.py")], tier=2))
        back = plan_from_dict(json.loads(json.dumps(plan.to_dict())))
        assert back.steps == plan.steps
        assert back.generated_at == GENERATED_AT

    def test_counts_are_recomputed_not_trusted(self):
        plan = _plan(_step(1, [], score_impact=3), _step(2, [], tier=2, score_impact=2))
        data = plan.to_dict()
        data.update(tier1_count=99, tier2_count=99, total_score_impact=99)
        back = plan_from_dict(data)
        assert (back.tier1_count, back.tier2_count, back.total_score_impact) == (1, 1, 5)

    def test_int_confidence_becomes_float(self):
        step = plan_from_dict(_with(confidence=1)).steps[0]
        assert step.confidence == 1.0 and isinstance(step.confidence, float)

    def test_non_string_generated_at_is_dropped(self):
        data = _with()
        data["generated_at"] = 12
        assert plan_from_dict(data).generated_at == ""

    def test_minimal_step_takes_the_defaults(self):
        step = plan_from_dict(_with()).steps[0]
        assert step == RefactorStep(id=1, tier=1, rule="r", priority="HIGH", title="t", why="")

    @pytest.mark.parametrize("data, message", [
        ([], "Not a refactoring plan"),
        ({"steps": {}}, "Not a refactoring plan"),
        (_with(id=True), "Step 1 of the plan is malformed: 'id' must be int, got bool"),
        (_with(operations=[{"type": "MODIFY", "path": 3}]), "'path' must be str, got int"),
        ({"steps": [{k: v for k, v in MINIMAL_STEP.items() if k != "title"}]},
         "missing 'title'"),
        ({"steps": [5]}, "a step must be an object"),
        (_with(operations=[5]), "an operation must be an object"),
        (_with(why=None), "'why' must be str, got NoneType"),
        (_with(confidence="x"), "'confidence' must be int or float, got str"),
        ({"steps": [MINIMAL_STEP, MINIMAL_STEP]}, "Step ids must be unique; repeated: 1"),
    ])
    def test_malformed_plans_are_refused(self, data, message):
        with pytest.raises(ValueError, match=re.escape(message)):
            plan_from_dict(data)


class TestFormatStepList:
    def test_empty_plan(self):
        assert format_step_list(_plan()) == "The plan has no steps; nothing to export."

    def test_lists_every_step_and_exports_nothing(self):
        plan = _plan(_step(1, [], score_impact=3, title="Split hub"),
                     _step(2, [], score_impact=2, title="Drop dead code"))
        text = format_step_list(plan)
        assert "Refactoring plan: 2 step(s), +5 pts estimated" in text
        for step in plan.steps:
            assert step_fingerprint(step) in text
            assert step.title in text
        assert "Nothing exported." in text


# ---------------------------------------------------------------------------
# Choosing the files
# ---------------------------------------------------------------------------

class TestSafeRel:
    @pytest.mark.parametrize("rel", ["src/./a.py", "src/x/../a.py", "src\\a.py"])
    def test_normalises_inside_paths(self, proj, rel):
        assert _safe_rel(proj, rel) == "src/a.py"

    @pytest.mark.parametrize("rel", [
        "", ".", "..", "src/..", "../outside.py", "/etc/passwd", "\\etc\\passwd",
        "C:foo", "C:\\x", "\\\\server\\share\\x", "//server/share/x", "a\x00b",
    ])
    def test_refuses_paths_outside_the_root(self, proj, rel):
        assert _safe_rel(proj, rel) is None

    def test_refuses_a_symlink_that_escapes(self, proj, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        try:
            os.symlink(outside, proj / "link", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks are not available here")
        assert _safe_rel(proj, "link/x.py") is None


class TestStepFiles:
    def test_delete_is_context(self, proj):
        step = _step(1, [_op("DELETE", "src/old.py")])
        assert _step_files(step, proj, None) == ([], ["src/old.py"], [], [])

    def test_new_file_is_described_not_loaded(self, proj):
        step = _step(1, [_op("CREATE", "src/new.py")])
        assert _step_files(step, proj, None) == ([], [], [], [])
        assert "1. CREATE `src/new.py`: do it" in _one(_plan(step), proj).prompt

    def test_placeholder_is_skipped_quietly(self, proj):
        step = _step(1, [_op("CREATE", "[composition root]")])
        assert _step_files(step, proj, None) == ([], [], [], [])

    def test_path_outside_the_root_is_refused(self, proj):
        step = _step(1, [_op("MODIFY", "../outside.py")])
        targets, _, _, warnings = _step_files(step, proj, None)
        assert targets == []
        assert warnings == ["Refused '../outside.py': not a path inside the project root."]

    def test_existing_create_becomes_a_target(self, proj):
        step = _step(1, [_op("CREATE", "src/a.py")])
        targets, _, _, warnings = _step_files(step, proj, None)
        assert targets == ["src/a.py"]
        assert warnings == ["src/a.py is marked CREATE but already exists; "
                            "it is included so it is not overwritten blind."]

    def test_missing_target_is_a_warning(self, proj):
        sp = _one(_plan(_step(1, [_op("MODIFY", "src/missing.py")])), proj)
        assert any(w.startswith("Could not read src/missing.py (core-target)") for w in sp.warnings)

    def test_duplicates_collapse_and_target_wins(self, proj):
        step = _step(1, [_op("MODIFY", "src/a.py"), _op("MODIFY", "src/a.py"),
                         _op("DELETE", "src/a.py")])
        targets, context, _, _ = _step_files(step, proj, None)
        assert (targets, context) == (["src/a.py"], [])


class TestConsumers:
    STEP = _step(1, [_op("MODIFY", "src/a.py"), _op("DELETE", "src/old.py")])

    def _consumers(self, proj, modules):
        return _step_files(self.STEP, proj, modules)[2:]

    def test_backslashes_are_normalised_and_sorted(self, proj):
        modules = {"src\\a.py": {"imported_by": ["src\\c1.py", "src/c0.py"]}}
        assert self._consumers(proj, modules) == (["src/c0.py", "src/c1.py"], [])

    def test_targets_and_context_are_not_consumers(self, proj):
        modules = {"src/a.py": {"imported_by": ["src/a.py", "src/old.py", "src/c0.py"]}}
        assert self._consumers(proj, modules)[0] == ["src/c0.py"]

    def test_bad_importers_are_dropped(self, proj):
        modules = {"src/a.py": {"imported_by": ["../evil.py", 3, None, "src/c0.py"]}}
        assert self._consumers(proj, modules)[0] == ["src/c0.py"]

    def test_consumers_are_capped(self, proj):
        importers = [f"src/i{n:02d}.py" for n in reversed(range(10))]
        consumers, warnings = self._consumers(proj, {"src/a.py": {"imported_by": importers}})
        assert consumers == [f"src/i{n:02d}.py" for n in range(MAX_CONSUMERS)]
        assert warnings == ["10 modules import the targets; the first 8 by path "
                            "are included as references."]

    @pytest.mark.parametrize("modules", [
        None, {}, {"src/a.py": ["src/c0.py"]}, {"src/a.py": {"imported_by": "src/c0.py"}},
    ])
    def test_no_usable_graph_means_no_consumers(self, proj, modules):
        assert self._consumers(proj, modules) == ([], [])


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

SWEEP_PLANS = {
    "modify-delete-create": (_full_plan, MODULES),
    "delete-only": (lambda: _plan(_step(1, [_op("DELETE", "src/old.py")])), None),
}


class TestBudget:
    def test_used_tokens_measure_the_prompt(self, proj):
        sp = _one(_full_plan(), proj, modules=MODULES)
        assert sp.used_tokens == estimate_tokens(sp.prompt)

    def test_default_budget_is_the_claude_preset(self, proj):
        export = export_prompts(_full_plan(), proj, "all")
        assert (export.model, export.budget_tokens) == ("claude", 60_000)

    def test_at_the_floor_only_core_targets_remain(self, proj):
        plan = _full_plan()
        p0 = _one(plan, proj, max_tokens=1, modules=MODULES).used_tokens
        sp = _one(plan, proj, max_tokens=p0, modules=MODULES)
        assert not sp.over_budget
        assert {f.path for f in sp.budget.files if f.status != DROPPED} == {"src/a.py"}
        assert "- src/c0.py (consumer-ref, dropped)" in sp.prompt
        assert "- src/old.py (important-context, dropped)" in sp.prompt
        assert any("file(s) dropped to fit the budget:" in w for w in sp.warnings)

        below = _one(plan, proj, max_tokens=p0 - 1, modules=MODULES)
        assert below.over_budget
        assert any(w.startswith("The prompt needs ~") for w in below.warnings)

    def test_oversized_core_target_is_reported(self, proj):
        _touch(proj, "src/big.py", _lines(2000, "x"))
        export = export_prompts(_plan(_step(1, [_op("MODIFY", "src/big.py")])), proj, "all",
                                max_tokens=1000)
        assert export.over_budget
        assert any("over by ~" in w for w in export.prompts[0].warnings)

    @pytest.mark.parametrize("name", sorted(SWEEP_PLANS))
    def test_over_budget_exactly_below_the_floor(self, proj, name):
        make_plan, modules = SWEEP_PLANS[name]
        plan = make_plan()
        p0 = _one(plan, proj, max_tokens=1, modules=modules).used_tokens
        full = _one(plan, proj, max_tokens=10**6, modules=modules).used_tokens
        seen_abbreviated = False
        for budget in range(max(1, p0 - 25), full + 25):
            sp = _one(plan, proj, max_tokens=budget, modules=modules)
            assert sp.over_budget == (budget < p0), budget
            for f in sp.budget.files:
                if f.status != FULL:
                    assert f"- {f.path} ({f.role}, {f.status})" in sp.prompt, budget
                seen_abbreviated |= f.status == ABBREVIATED
        assert seen_abbreviated

    def test_large_budget_keeps_everything(self, proj):
        sp = _one(_full_plan(), proj, max_tokens=10**6, modules=MODULES)
        status = {f.path: (f.role, f.status) for f in sp.budget.files}
        assert status["src/a.py"] == (CORE_TARGET, FULL)
        assert status["src/old.py"] == (IMPORTANT_CONTEXT, FULL)
        for i in range(3):
            assert status[f"src/c{i}.py"] == (CONSUMER_REF, ABBREVIATED)
            assert f"- src/c{i}.py (consumer-ref, abbreviated)" in sp.prompt
        assert not sp.over_budget and not sp.budget.over_budget

        bare = _one(_full_plan(), proj, max_tokens=10**6)
        assert all(f.status == FULL for f in bare.budget.files)
        assert prompt_export._TRIM_NOTE not in bare.prompt

    def test_create_only_step_has_no_files(self, proj):
        sp = _one(_plan(_step(1, [_op("CREATE", "src/new.py")])), proj)
        assert _NO_FILES in sp.prompt
        assert not sp.over_budget


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

class TestContent:
    def test_header(self, proj):
        step = _step(1, [_op("MODIFY", "src/a.py")], score_impact=5, confidence_basis="basis")
        sp = _one(_plan(step), proj)
        assert "# Refactoring step 1: Step 1" in sp.prompt
        assert (f"<!-- Genesis Architect PRO prompt_export | fingerprint {sp.fingerprint} "
                f"| plan {GENERATED_AT} -->") in sp.prompt
        assert "Rule: hub-splitter | Priority: HIGH | Tier: 1 | Complexity: MEDIUM" in sp.prompt
        assert "Planner estimate: +5 pts, confidence 0.80 (basis)" in sp.prompt
        for constraint in CONSTRAINTS:
            assert f"- {constraint}" in sp.prompt
        assert "### src/a.py  [core-target, full]" in sp.prompt

    def test_no_plan_timestamp(self, proj):
        sp = _one(_plan(_step(1, []), generated_at=""), proj)
        assert " | plan" not in sp.prompt

    def test_json_is_environment_neutral(self, proj):
        export = export_prompts(_full_plan(), proj, "all", modules=MODULES)
        text = json.dumps(export.to_dict())
        for needle in (str(proj), json.dumps(str(proj))[1:-1], proj.as_posix()):
            assert needle not in text

    def test_json_without_prompts(self, proj):
        data = export_prompts(_full_plan(), proj, "all").to_dict(include_prompts=False)
        assert all("prompt" not in p for p in data["prompts"])

    def test_bad_root_and_selection(self, proj, tmp_path):
        with pytest.raises(NotADirectoryError):
            export_prompts(_full_plan(), tmp_path / "nope", "all")
        with pytest.raises(ValueError, match="No steps selected"):
            export_prompts(_full_plan(), proj, "")


# ---------------------------------------------------------------------------
# Writing files
# ---------------------------------------------------------------------------

class TestWritePrompts:
    @pytest.fixture
    def export(self, proj):
        return export_prompts(_full_plan(), proj, "all")

    def test_dry_run_writes_nothing(self, export, tmp_path):
        out = tmp_path / "out"
        name = prompt_filename(export.prompts[0])
        assert [(a.path, a.status) for a in write_prompts(export, out)] == [(name, WOULD_WRITE)]
        assert not out.exists()

    def test_apply_writes_utf8_with_lf(self, export, tmp_path):
        out = tmp_path / "out"
        sp = export.prompts[0]
        actions = write_prompts(export, out, apply=True)
        assert actions[0].status == WRITTEN
        assert actions[0].path == f"step-01-hub-splitter-{sp.fingerprint}.md"
        assert (out / actions[0].path).read_bytes() == sp.prompt.encode("utf-8")

    def test_existing_file_is_never_overwritten(self, export, tmp_path):
        out = tmp_path / "out"
        target = _touch(out, prompt_filename(export.prompts[0]), "keep")
        assert write_prompts(export, out, apply=True)[0].status == EXISTS
        assert target.read_text(encoding="utf-8") == "keep"

    def test_file_appearing_mid_write_is_not_overwritten(self, export, tmp_path, monkeypatch):
        def raiser(*args, **kwargs):
            raise FileExistsError(args[0])
        monkeypatch.setattr(prompt_export, "open", raiser, raising=False)
        assert write_prompts(export, tmp_path / "out", apply=True)[0].status == EXISTS

    def test_out_dir_that_is_a_file(self, export, tmp_path):
        with pytest.raises(NotADirectoryError):
            write_prompts(export, _touch(tmp_path, "file.txt"))

    @pytest.mark.parametrize("rule, slug", [
        ("../../etc", "etc"),
        ("!!!", "step"),
        ("a" * 300, "a" * 40),
        ("a" * 39 + "-b", "a" * 39),
    ])
    def test_filename_slug_is_safe(self, proj, rule, slug):
        sp = _one(_plan(_step(1, [], rule=rule)), proj)
        assert prompt_filename(sp) == f"step-01-{slug}-{sp.fingerprint}.md"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    @pytest.fixture
    def plan_file(self, tmp_path):
        path = tmp_path / "plan.json"
        path.write_text(json.dumps(_full_plan().to_dict()), encoding="utf-8")
        return path

    def _run(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["prompt_export", *map(str, args)])
        main()

    def _exit(self, monkeypatch, *args):
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, *args)
        return exc.value.code

    def test_without_steps_only_lists(self, proj, plan_file, monkeypatch, capsys):
        self._run(monkeypatch, proj, "--plan", plan_file, "--no-graph")
        assert "Nothing exported." in capsys.readouterr().out
        assert not (proj / ".genesis").exists()

    def test_json_export(self, proj, plan_file, monkeypatch, capsys):
        self._run(monkeypatch, proj, "--plan", plan_file, "--no-graph", "--steps", "1", "--json")
        data = json.loads(capsys.readouterr().out)
        assert [p["step_id"] for p in data["prompts"]] == [1]
        assert not data["over_budget"]
        assert not (proj / ".genesis").exists()

    @pytest.mark.parametrize("extra, message", [
        (["--steps", "99"], "No step matches"),
        (["--apply"], "--apply only takes effect with --out-dir."),
        (["--steps", "1", "--model", "bogus"], "Unknown model preset"),
        (["--steps", "1", "--max-tokens", "0"], "max_tokens must be positive"),
    ])
    def test_usage_errors_exit_2(self, proj, plan_file, monkeypatch, capsys, extra, message):
        assert self._exit(monkeypatch, proj, "--plan", plan_file, "--no-graph", *extra) == 2
        assert message in capsys.readouterr().err

    def test_not_a_directory(self, tmp_path, plan_file, monkeypatch, capsys):
        assert self._exit(monkeypatch, tmp_path / "nope", "--plan", plan_file) == 2
        assert "Not a directory" in capsys.readouterr().err

    @pytest.mark.parametrize("content", [None, "{not json", json.dumps({"steps": [5]})])
    def test_unloadable_plan(self, proj, tmp_path, monkeypatch, capsys, content):
        path = tmp_path / "bad.json"
        if content is not None:
            path.write_text(content, encoding="utf-8")
        assert self._exit(monkeypatch, proj, "--plan", path) == 2
        assert "Could not load the plan" in capsys.readouterr().err

    def test_over_budget_exits_1_with_a_warning(self, proj, plan_file, monkeypatch, capsys):
        code = self._exit(monkeypatch, proj, "--plan", plan_file, "--no-graph",
                          "--steps", "1", "--max-tokens", "50")
        assert code == 1
        assert "WARNING: step 1: The prompt needs ~" in capsys.readouterr().err

    def test_out_dir_dry_run(self, proj, plan_file, tmp_path, monkeypatch, capsys):
        out = tmp_path / "out"
        self._run(monkeypatch, proj, "--plan", plan_file, "--no-graph", "--steps", "1",
                  "--out-dir", out)
        text = capsys.readouterr().out
        assert WOULD_WRITE in text
        assert "Dry run: nothing written. Re-run with --apply to write." in text
        assert not out.exists()

    def test_out_dir_apply(self, proj, plan_file, tmp_path, monkeypatch, capsys):
        out = tmp_path / "out"
        self._run(monkeypatch, proj, "--plan", plan_file, "--no-graph", "--steps", "1",
                  "--out-dir", out, "--apply")
        assert WRITTEN in capsys.readouterr().out
        assert len(list(out.glob("step-01-*.md"))) == 1

    def test_out_dir_that_is_a_file(self, proj, plan_file, tmp_path, monkeypatch, capsys):
        blocker = _touch(tmp_path, "blocker")
        code = self._exit(monkeypatch, proj, "--plan", plan_file, "--no-graph", "--steps", "1",
                          "--out-dir", blocker)
        assert code == 2
        assert "Could not write to" in capsys.readouterr().err

    def test_graph_supplies_consumers(self, proj, plan_file, monkeypatch, capsys):
        monkeypatch.setattr(prompt_export, "_graph_modules", lambda root, language: MODULES)
        self._run(monkeypatch, proj, "--plan", plan_file, "--steps", "1")
        assert "### src/c0.py  [consumer-ref, abbreviated]" in capsys.readouterr().out

    def test_plan_is_generated_without_plan_file(self, proj, monkeypatch, capsys):
        monkeypatch.setattr(prompt_export, "generate_plan", lambda root, language=None: _full_plan())
        self._run(monkeypatch, proj, "--no-graph")
        assert "Step 1" in capsys.readouterr().out

    @pytest.mark.parametrize("extra", [[], ["--steps", "1"]])
    def test_unencodable_console_exits_2(self, proj, tmp_path, monkeypatch, capsys, extra):
        path = tmp_path / "plan.json"
        plan = _plan(_step(1, [_op("MODIFY", "src/a.py")], title="Split \u05d0"))
        path.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
        assert self._exit(monkeypatch, proj, "--plan", path, "--no-graph", *extra) == 2
        err = capsys.readouterr().err
        assert "cp1252" in err and "--out-dir" in err
