"""Tests for fork_analyzer, nlu_gate, audit_inference, companion."""
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from genesis_architect.core import nlu_gate, audit_inference, companion
from genesis_architect.core.nlu_gate import Intent, Confidence, detect_intent, announce_routing


# ---------------------------------------------------------------------------
# NLU Gate
# ---------------------------------------------------------------------------

class TestNluGate:
    def _make_ask(self, inputs):
        it = iter(inputs)
        return lambda: next(it)

    def _yes(self): return True
    def _no(self): return False

    def test_exact_letter_a(self):
        result = nlu_gate.prompt_choice(self._make_ask(["A"]), self._yes)
        assert result == "A"

    def test_exact_letter_b(self):
        result = nlu_gate.prompt_choice(self._make_ask(["B"]), self._yes)
        assert result == "B"

    def test_natural_minimalist(self):
        result = nlu_gate.prompt_choice(self._make_ask(["I want the minimalist approach"]), self._yes)
        assert result == "A"

    def test_natural_scalable(self):
        result = nlu_gate.prompt_choice(self._make_ask(["let's go scalable"]), self._yes)
        assert result == "B"

    def test_confirm_no_retries(self):
        inputs = ["A", "A", "A"]
        it = iter(inputs)
        confirms = iter([False, False, True])
        result = nlu_gate.prompt_choice(lambda: next(it), lambda: next(confirms))
        assert result == "A"

    def test_three_failures_returns_restart(self):
        result = nlu_gate.prompt_choice(self._make_ask(["???", "???", "???"]), self._yes)
        assert result == "__restart__"

    def test_case_insensitive(self):
        result = nlu_gate.prompt_choice(self._make_ask(["a"]), self._yes)
        assert result == "A"

    def test_quick_option(self):
        result = nlu_gate.prompt_choice(self._make_ask(["quick"]), self._yes)
        assert result == "C"


# ---------------------------------------------------------------------------
# Audit Inference
# ---------------------------------------------------------------------------

class TestAuditInference:
    def test_reads_pyproject_name_and_description(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndescription = "A great tool"\n'
        )
        ctx = audit_inference.infer_project_context(tmp_path)
        assert ctx["name"] == "myapp"
        assert ctx["description"] == "A great tool"

    def test_reads_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "mytool", "description": "A JS tool"}'
        )
        ctx = audit_inference.infer_project_context(tmp_path)
        assert ctx["name"] == "mytool"
        assert "JS tool" in ctx["description"]

    def test_reads_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module github.com/user/mygoapp\n\ngo 1.21\n")
        ctx = audit_inference.infer_project_context(tmp_path)
        assert ctx["name"] == "mygoapp"

    def test_readme_fallback_description(self, tmp_path):
        (tmp_path / "README.md").write_text("# MyProject\nA tool that does things.\n")
        ctx = audit_inference.infer_project_context(tmp_path)
        assert "tool that does things" in ctx["description"]

    def test_empty_project_returns_empty(self, tmp_path):
        ctx = audit_inference.infer_project_context(tmp_path)
        assert ctx["name"] == ""
        assert ctx["description"] == ""

    def test_get_vision_uses_inference(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndescription = "inferred vision"\n'
        )
        vision = audit_inference.get_vision(tmp_path, ask_fn=lambda _: "manual")
        assert vision == "inferred vision"

    def test_get_vision_prompts_when_empty(self, tmp_path):
        vision = audit_inference.get_vision(tmp_path, ask_fn=lambda _: "manual vision")
        assert vision == "manual vision"


# ---------------------------------------------------------------------------
# Companion Exit
# ---------------------------------------------------------------------------

class TestCompanionExit:
    def test_done_exits(self):
        exits, reason = companion.should_exit("done")
        assert exits
        assert reason == "explicit"

    def test_exit_companion_mode(self):
        exits, reason = companion.should_exit("exit companion mode")
        assert exits

    def test_genesis_init_exits(self):
        exits, reason = companion.should_exit("genesis init my new project")
        assert exits
        assert reason == "new_project"

    def test_new_project_exits(self):
        exits, reason = companion.should_exit("let's work on a new project")
        assert exits
        assert reason == "unrelated"

    def test_normal_question_stays(self):
        exits, _ = companion.should_exit("how do I handle errors in Python?")
        assert not exits

    def test_empty_input_stays(self):
        exits, _ = companion.should_exit("")
        assert not exits

    def test_exit_message_explicit(self):
        msg = companion.exit_message("explicit")
        assert "genesis init" in msg

    def test_exit_message_new_project(self):
        msg = companion.exit_message("new_project")
        assert "new project" in msg.lower()


# ---------------------------------------------------------------------------
# Intent Detection (Natural Language Routing)
# ---------------------------------------------------------------------------

class TestIntentDetection:
    # --- Fast Build ---
    def test_just_build(self):
        r = detect_intent("just build it")
        assert r.intent == Intent.FAST_BUILD
        assert r.confidence == Confidence.HIGH

    def test_build_me_quick(self):
        r = detect_intent("build me a quick working version")
        assert r.intent == Intent.FAST_BUILD

    def test_hackathon(self):
        r = detect_intent("I need this for a hackathon tonight")
        assert r.intent == Intent.FAST_BUILD

    def test_get_it_running(self):
        r = detect_intent("just get it running")
        assert r.intent == Intent.FAST_BUILD

    def test_skip_research(self):
        r = detect_intent("skip the research and build")
        assert r.intent == Intent.FAST_BUILD

    # --- Founder / Product Strategy ---
    def test_worth_building(self):
        r = detect_intent("I have an idea for a project. Check if it is worth building.")
        assert r.intent == Intent.FOUNDER
        assert r.confidence == Confidence.HIGH

    def test_should_i_build(self):
        r = detect_intent("should I build this or is there already something like it?")
        assert r.intent == Intent.FOUNDER

    def test_competitors(self):
        r = detect_intent("who are the competitors in this space?")
        assert r.intent == Intent.FOUNDER

    def test_idea_validation(self):
        r = detect_intent("help me with idea validation before I start")
        assert r.intent == Intent.FOUNDER

    # --- Audit ---
    def test_review_this(self):
        r = detect_intent("review this project before I continue")
        assert r.intent == Intent.AUDIT
        assert r.confidence == Confidence.HIGH

    def test_audit_keyword(self):
        r = detect_intent("audit my codebase")
        assert r.intent == Intent.AUDIT

    def test_before_release(self):
        r = detect_intent("check this before I release")
        assert r.intent == Intent.AUDIT

    def test_code_review(self):
        r = detect_intent("do a code review of this")
        assert r.intent == Intent.AUDIT

    # --- Recovery ---
    def test_broken_project(self):
        r = detect_intent("This existing project is broken. Figure out what is wrong.")
        assert r.intent == Intent.RECOVERY
        assert r.confidence == Confidence.HIGH

    def test_debug_this(self):
        r = detect_intent("debug this - it stopped working after the last commit")
        assert r.intent == Intent.RECOVERY

    def test_something_wrong(self):
        r = detect_intent("something is wrong with the project")
        assert r.intent == Intent.RECOVERY

    def test_crashed(self):
        r = detect_intent("the app crashed and I don't know why")
        assert r.intent == Intent.RECOVERY

    # --- Resume ---
    def test_continue_from_where_stopped(self):
        r = detect_intent("Continue from where we stopped.")
        assert r.intent == Intent.RESUME
        assert r.confidence == Confidence.HIGH

    def test_pick_up(self):
        r = detect_intent("pick up where we left off")
        assert r.intent == Intent.RESUME

    def test_resume_keyword(self):
        r = detect_intent("resume the project")
        assert r.intent == Intent.RESUME

    def test_carry_on(self):
        r = detect_intent("carry on with the project")
        assert r.intent == Intent.RESUME

    # --- Validation ---
    def test_does_this_work(self):
        r = detect_intent("does this work?")
        assert r.intent == Intent.VALIDATION

    def test_smoke_test(self):
        r = detect_intent("run a smoke test on this")
        assert r.intent == Intent.VALIDATION

    def test_is_it_working(self):
        r = detect_intent("is it working now?")
        assert r.intent == Intent.VALIDATION

    # --- Research Only ---
    def test_just_research(self):
        r = detect_intent("just do research, don't build anything yet")
        assert r.intent == Intent.RESEARCH_ONLY
        assert r.confidence == Confidence.HIGH

    def test_no_code(self):
        r = detect_intent("only research, no code")
        assert r.intent == Intent.RESEARCH_ONLY

    def test_investigate(self):
        r = detect_intent("investigate what projects like this do")
        assert r.intent == Intent.RESEARCH_ONLY

    # --- Unknown / low confidence ---
    def test_vague_input_unknown(self):
        r = detect_intent("I want to build something")
        assert r.intent == Intent.UNKNOWN

    def test_empty_input_unknown(self):
        r = detect_intent("")
        assert r.intent == Intent.UNKNOWN

    def test_unrelated_text_unknown(self):
        r = detect_intent("the weather is nice today")
        assert r.intent == Intent.UNKNOWN

    # --- Confidence levels ---
    def test_high_confidence_strong_signal(self):
        r = detect_intent("figure out what is wrong with this broken project")
        assert r.confidence == Confidence.HIGH

    def test_medium_confidence_weak_signal(self):
        r = detect_intent("validate the code")
        assert r.confidence in (Confidence.MEDIUM, Confidence.HIGH)

    # --- Announcement format ---
    def test_announce_high_confidence_contains_intent(self):
        r = detect_intent("just build it")
        msg = announce_routing(r, "just build it")
        assert "fast-build" in msg
        assert "just build" in msg

    def test_announce_unknown_asks_question(self):
        r = detect_intent("")
        msg = announce_routing(r, "")
        assert "?" in msg

    def test_announce_medium_offers_correction(self):
        r = detect_intent("validate the code")
        r.confidence = Confidence.MEDIUM  # force medium for test
        msg = announce_routing(r, "validate the code")
        assert "change course" in msg or "no" in msg.lower()

    # --- Case insensitivity ---
    def test_uppercase_input(self):
        r = detect_intent("JUST BUILD IT NOW")
        assert r.intent == Intent.FAST_BUILD

    def test_mixed_case(self):
        r = detect_intent("Worth Building? Check please.")
        assert r.intent == Intent.FOUNDER
