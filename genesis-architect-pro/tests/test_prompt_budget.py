"""
prompt_budget (G-CRIT-04): role-based packing, abbreviation, presets and
explicit overflow reporting.
"""

import json
import sys

import pytest

from genesis_architect_pro.prompt_budget import (
    ABBREVIATED,
    CONSUMER_REF,
    CORE_TARGET,
    DROPPED,
    FULL,
    IMPORTANT_CONTEXT,
    MODEL_PRESETS,
    PromptFile,
    abbreviate,
    collect_files,
    estimate_tokens,
    main,
    pack_prompt,
    resolve_budget,
)


def _py_module(n_funcs: int, body_lines: int = 6) -> str:
    """A Python module with n top-level functions, each with an indented body."""
    out = ['"""Module docstring."""', "import os", ""]
    for i in range(n_funcs):
        out.append(f"def func_{i}(x):")
        out.extend(f"    y = x + {j}" for j in range(body_lines))
        out.append("    return y")
        out.append("")
    return "\n".join(out)


class TestEstimateTokens:
    @pytest.mark.parametrize("text,expected", [("", 0), ("abcd", 1), ("abcde", 2), ("a" * 400, 100)])
    def test_ceil_chars_over_four(self, text, expected):
        assert estimate_tokens(text) == expected


class TestResolveBudget:
    def test_default_is_claude_preset(self):
        assert resolve_budget() == ("claude", MODEL_PRESETS["claude"])

    def test_presets_from_spec(self):
        assert MODEL_PRESETS["claude"] == 60_000
        assert MODEL_PRESETS["qwen-32b"] == 8_000

    def test_case_insensitive(self):
        assert resolve_budget("Qwen-32B") == ("qwen-32b", 8_000)

    def test_unknown_preset_raises_instead_of_guessing(self):
        with pytest.raises(ValueError, match="Unknown model preset"):
            resolve_budget("gpt-9")

    def test_explicit_max_tokens_wins(self):
        assert resolve_budget("claude", max_tokens=1234) == ("claude", 1234)
        assert resolve_budget(None, max_tokens=50) == (None, 50)

    @pytest.mark.parametrize("bad", [0, -5])
    def test_non_positive_max_tokens_raises(self, bad):
        with pytest.raises(ValueError):
            resolve_budget(max_tokens=bad)


class TestAbbreviate:
    def test_short_file_unchanged(self):
        text = "\n".join(f"line {i}" for i in range(25))
        assert abbreviate(text) == text

    def test_keeps_head_tail_and_exports(self):
        text = _py_module(10)
        lines = text.splitlines()
        short = abbreviate(text)
        kept = short.splitlines()
        assert kept[:20] == lines[:20]
        assert kept[-5:] == lines[-5:]
        middle = lines[20:-5]
        for ln in middle:
            if ln.startswith("def "):
                assert ln in kept
        # Indented body lines from the middle are omitted
        assert len(short) < len(text)
        omitted = len([ln for ln in middle if not ln.startswith("def ")])
        assert f"[{omitted} lines omitted" in short

    def test_js_exports_kept(self):
        body = ["// header"] * 20 + ["  const x = 1;"] * 10 + [
            "export function publicApi() {}",
            "module.exports = { publicApi };",
        ] + ["  noise();"] * 10 + ["// tail"] * 5
        short = abbreviate("\n".join(body))
        assert "export function publicApi() {}" in short
        assert "module.exports = { publicApi };" in short
        assert "  noise();" not in short

    def test_no_exports_still_marks_omission(self):
        body = ["top"] * 20 + ["    inner"] * 30 + ["end"] * 5
        short = abbreviate("\n".join(body))
        assert "[30 lines omitted, 0 export line(s) kept]" in short
        assert "    inner" not in short


class TestPackPrompt:
    def test_core_always_full_even_over_budget(self):
        big = "x" * 4000  # ~1000 tokens
        report = pack_prompt([PromptFile("src/core.py", big, CORE_TARGET)], max_tokens=100)
        assert report.files[0].status == FULL
        assert report.over_budget is True
        assert report.ok is False
        assert any("Core targets alone need" in w and "over by" in w for w in report.warnings)

    def test_core_over_budget_drops_everything_else(self):
        files = [
            PromptFile("src/core.py", "x" * 4000, CORE_TARGET),
            PromptFile("src/ctx.py", "short", IMPORTANT_CONTEXT),
            PromptFile("src/use.py", "short", CONSUMER_REF),
        ]
        report = pack_prompt(files, max_tokens=100)
        statuses = {f.path: f.status for f in report.files}
        assert statuses == {"src/core.py": FULL, "src/ctx.py": DROPPED, "src/use.py": DROPPED}
        assert any("2 file(s) dropped" in w and "src/ctx.py" in w for w in report.warnings)

    def test_important_context_full_when_it_fits(self):
        files = [
            PromptFile("a.py", "core", CORE_TARGET),
            PromptFile("b.py", _py_module(10), IMPORTANT_CONTEXT),
        ]
        report = pack_prompt(files, max_tokens=10_000)
        assert [f.status for f in report.files] == [FULL, FULL]
        assert report.ok is True
        assert report.warnings == []

    def test_important_context_abbreviated_when_full_does_not_fit(self):
        ctx = _py_module(30)
        full_cost = estimate_tokens(ctx)
        files = [PromptFile("a.py", "core", CORE_TARGET), PromptFile("b.py", ctx, IMPORTANT_CONTEXT)]
        report = pack_prompt(files, max_tokens=full_cost // 2)
        b = report.files[1]
        assert b.status == ABBREVIATED
        assert b.tokens < b.original_tokens
        assert report.ok is True

    def test_important_context_dropped_when_nothing_fits(self):
        files = [PromptFile("a.py", "core", CORE_TARGET), PromptFile("b.py", _py_module(30), IMPORTANT_CONTEXT)]
        report = pack_prompt(files, max_tokens=30)
        assert report.files[1].status == DROPPED
        assert report.files[1].tokens == 0
        assert report.over_budget is False
        assert report.ok is False

    def test_long_consumer_is_abbreviated_even_with_room(self):
        files = [PromptFile("use.py", _py_module(10), CONSUMER_REF)]
        report = pack_prompt(files, max_tokens=60_000)
        assert report.files[0].status == ABBREVIATED

    def test_short_consumer_counts_as_full(self):
        report = pack_prompt([PromptFile("use.py", "import a\n", CONSUMER_REF)], max_tokens=1000)
        assert report.files[0].status == FULL

    def test_used_tokens_within_budget_and_equal_to_sum(self):
        files = [PromptFile("a.py", "core" * 20, CORE_TARGET)] + [
            PromptFile(f"c{i}.py", _py_module(8), CONSUMER_REF) for i in range(10)
        ]
        report = pack_prompt(files, max_tokens=900)
        assert report.used_tokens <= 900
        assert report.used_tokens == sum(f.tokens for f in report.files)
        assert report.by_status(DROPPED), "budget should force some drops"

    def test_order_is_role_priority_then_input(self):
        files = [
            PromptFile("u1.py", "u", CONSUMER_REF),
            PromptFile("i1.py", "i", IMPORTANT_CONTEXT),
            PromptFile("c1.py", "c", CORE_TARGET),
            PromptFile("u2.py", "u", CONSUMER_REF),
            PromptFile("c2.py", "c", CORE_TARGET),
        ]
        report = pack_prompt(files)
        assert [f.path for f in report.files] == ["c1.py", "c2.py", "i1.py", "u1.py", "u2.py"]

    def test_duplicate_path_kept_under_highest_role(self):
        files = [
            PromptFile("src/a.py", "x", CONSUMER_REF),
            PromptFile("src\\a.py", "x", CORE_TARGET),
        ]
        report = pack_prompt(files)
        assert len(report.files) == 1
        assert report.files[0].role == CORE_TARGET

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError, match="Unknown role"):
            pack_prompt([PromptFile("a.py", "x", "vip")])

    def test_render_excludes_dropped_and_labels_sections(self):
        files = [
            PromptFile("a.py", "CORE_BODY", CORE_TARGET),
            PromptFile("b.py", "DROP_ME " * 500, IMPORTANT_CONTEXT),
        ]
        report = pack_prompt(files, max_tokens=60)
        text = report.render()
        assert "### a.py  [core-target, full]" in text
        assert "CORE_BODY" in text
        assert "DROP_ME" not in text

    def test_fence_outgrows_backticks_in_content(self):
        content = "text\n```python\ncode\n```\n"
        report = pack_prompt([PromptFile("README.md", content, CORE_TARGET)])
        assert "\n````\n" in report.files[0].content

    def test_to_dict_serializable_without_content_by_default(self):
        report = pack_prompt([PromptFile("a.py", "SECRET_BODY", CORE_TARGET)], model="qwen-32b")
        d = report.to_dict()
        text = json.dumps(d)
        assert "SECRET_BODY" not in text
        assert d["model"] == "qwen-32b" and d["budget_tokens"] == 8_000
        assert d["counts"] == {FULL: 1, ABBREVIATED: 0, DROPPED: 0}
        assert "SECRET_BODY" in json.dumps(report.to_dict(include_content=True))


class TestCollectFilesAndCli:
    def test_missing_file_becomes_warning(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        files, warnings = collect_files(tmp_path, targets=["a.py"], consumers=["missing.py"])
        assert [f.path for f in files] == ["a.py"]
        assert files[0].role == CORE_TARGET
        assert len(warnings) == 1 and "missing.py" in warnings[0]

    def test_cli_json(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "b.py").write_text(_py_module(10), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [
            "prompt_budget", "--root", str(tmp_path), "--target", "a.py",
            "--consumer", "b.py", "--consumer", "gone.py", "--model", "qwen-32b", "--json",
        ])
        main()
        data = json.loads(capsys.readouterr().out)
        assert data["model"] == "qwen-32b"
        assert [f["status"] for f in data["files"]] == [FULL, ABBREVIATED]
        assert any("gone.py" in w for w in data["warnings"])

    def test_cli_exits_1_when_core_overflows(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "big.py").write_text("x" * 4000, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [
            "prompt_budget", "--root", str(tmp_path), "--target", "big.py", "--max-tokens", "100",
        ])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        assert "WARNING: Core targets alone need" in capsys.readouterr().out

    def test_cli_unknown_model_exits_2(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prompt_budget", "--root", str(tmp_path), "--model", "nope"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
        assert "Unknown model preset" in capsys.readouterr().err
