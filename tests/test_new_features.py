"""Tests for fork_analyzer, nlu_gate, audit_inference, companion."""
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from genesis_architect.core import nlu_gate, audit_inference, companion


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
