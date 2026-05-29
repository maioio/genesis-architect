"""Tests for publish_agent: collect_release_data, generate_publish_content, format_output."""
import sys
import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from genesis_architect.core import publish_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path, notes: str = "", readme: str = "") -> Path:
    if notes:
        (tmp_path / "RELEASE_NOTES_v3.0.0.md").write_text(notes, encoding="utf-8")
    if readme:
        (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# collect_release_data
# ---------------------------------------------------------------------------

class TestCollectReleaseData:
    def test_reads_release_notes_version(self, tmp_path):
        _make_project(tmp_path, notes="# Genesis Architect v3.0.0\n\nSome content.")
        with mock.patch.object(publish_agent, "_get_recent_commits", return_value=[]):
            with mock.patch.object(publish_agent, "_detect_test_count", return_value=0):
                data = publish_agent.collect_release_data(tmp_path)
        assert data["version"] == "3.0.0"

    def test_reads_release_notes_content(self, tmp_path):
        notes = "# v2.0.0\n\nAdded vault."
        _make_project(tmp_path, notes=notes)
        with mock.patch.object(publish_agent, "_get_recent_commits", return_value=[]):
            with mock.patch.object(publish_agent, "_detect_test_count", return_value=0):
                data = publish_agent.collect_release_data(tmp_path)
        assert "Added vault." in data["release_notes_raw"]

    def test_version_defaults_to_latest_when_no_files(self, tmp_path):
        with mock.patch.object(publish_agent, "_get_recent_commits", return_value=[]):
            with mock.patch.object(publish_agent, "_detect_test_count", return_value=0):
                data = publish_agent.collect_release_data(tmp_path)
        assert data["version"] == "latest"

    def test_picks_highest_version_when_multiple_notes(self, tmp_path):
        (tmp_path / "RELEASE_NOTES_v1.0.0.md").write_text("v1", encoding="utf-8")
        (tmp_path / "RELEASE_NOTES_v3.0.0.md").write_text("v3", encoding="utf-8")
        (tmp_path / "RELEASE_NOTES_v2.0.0.md").write_text("v2", encoding="utf-8")
        with mock.patch.object(publish_agent, "_get_recent_commits", return_value=[]):
            with mock.patch.object(publish_agent, "_detect_test_count", return_value=0):
                data = publish_agent.collect_release_data(tmp_path)
        assert data["version"] == "3.0.0"

    def test_commits_included(self, tmp_path):
        commits = ["abc1234 feat: add vault", "def5678 fix: rate limit"]
        with mock.patch.object(publish_agent, "_get_recent_commits", return_value=commits):
            with mock.patch.object(publish_agent, "_detect_test_count", return_value=0):
                data = publish_agent.collect_release_data(tmp_path)
        assert data["commits"] == commits

    def test_test_count_from_readme_badge(self, tmp_path):
        readme = "[![Tests](https://img.shields.io/badge/tests-316-brightgreen)](tests/)"
        _make_project(tmp_path, readme=readme)
        count = publish_agent._detect_test_count(tmp_path)
        assert count == 316

    def test_test_count_zero_when_no_badge(self, tmp_path):
        _make_project(tmp_path, readme="# No badge here")
        with mock.patch("subprocess.run", side_effect=Exception("no pytest")):
            count = publish_agent._detect_test_count(tmp_path)
        assert count == 0


# ---------------------------------------------------------------------------
# generate_publish_content
# ---------------------------------------------------------------------------

class TestGeneratePublishContent:
    def _data(self, **kwargs):
        base = {
            "version": "3.0.0",
            "release_notes_raw": "# v3.0.0\n\nAdded fork analysis.",
            "commits": ["abc feat: fork analyzer", "def fix: rate limit"],
            "test_count": 316,
        }
        base.update(kwargs)
        return base

    def test_uses_llm_for_hn_title(self):
        response = json.dumps({"title": "Show HN: My Tool", "comment": "Built it."})
        llm_fn = mock.Mock(return_value=response)
        content = publish_agent.generate_publish_content(self._data(), llm_fn)
        assert content["hn_title"] == "Show HN: My Tool"

    def test_uses_llm_for_hn_comment(self):
        response = json.dumps({"title": "Show HN: X", "comment": "We built this."})
        llm_fn = mock.Mock(return_value=response)
        content = publish_agent.generate_publish_content(self._data(), llm_fn)
        assert content["hn_comment"] == "We built this."

    def test_falls_back_to_defaults_on_bad_json(self):
        llm_fn = mock.Mock(return_value="not json at all {broken}")
        content = publish_agent.generate_publish_content(self._data(), llm_fn)
        assert "Show HN" in content["hn_title"]
        assert len(content["hn_comment"]) > 0

    def test_strips_markdown_fences_from_llm_response(self):
        response = '```json\n{"title": "Show HN: Clean", "comment": "Nice."}\n```'
        llm_fn = mock.Mock(side_effect=[response, "release body text"])
        content = publish_agent.generate_publish_content(self._data(), llm_fn)
        assert content["hn_title"] == "Show HN: Clean"

    def test_release_body_from_llm(self):
        hn_response = json.dumps({"title": "Show HN: X", "comment": "Y"})
        release_body = "## v3.0.0\n\nAdded fork analysis."
        llm_fn = mock.Mock(side_effect=[hn_response, release_body])
        content = publish_agent.generate_publish_content(self._data(), llm_fn)
        assert content["release_body"] == release_body

    def test_release_body_falls_back_to_raw_notes_when_empty(self):
        hn_response = json.dumps({"title": "Show HN: X", "comment": "Y"})
        llm_fn = mock.Mock(side_effect=[hn_response, ""])
        data = self._data(release_notes_raw="# v3.0.0\n\nFallback content.")
        content = publish_agent.generate_publish_content(data, llm_fn)
        assert "Fallback content." in content["release_body"]

    def test_release_title_extracted_from_raw_notes(self):
        hn_response = json.dumps({"title": "Show HN: X", "comment": "Y"})
        llm_fn = mock.Mock(side_effect=[hn_response, "body"])
        data = self._data(release_notes_raw="# Genesis Architect v3.0.0 - The Big Update\n\nContent.")
        content = publish_agent.generate_publish_content(data, llm_fn)
        assert "Genesis Architect" in content["release_title"]

    def test_llm_called_twice(self):
        hn_response = json.dumps({"title": "Show HN: X", "comment": "Y"})
        llm_fn = mock.Mock(side_effect=[hn_response, "release body"])
        publish_agent.generate_publish_content(self._data(), llm_fn)
        assert llm_fn.call_count == 2

    def test_version_appears_in_hn_prompt(self):
        hn_response = json.dumps({"title": "Show HN: X", "comment": "Y"})
        llm_fn = mock.Mock(side_effect=[hn_response, "body"])
        publish_agent.generate_publish_content(self._data(version="4.1.0"), llm_fn)
        first_call_prompt = llm_fn.call_args_list[0][0][0]
        assert "4.1.0" in first_call_prompt

    def test_test_count_appears_in_hn_prompt(self):
        hn_response = json.dumps({"title": "Show HN: X", "comment": "Y"})
        llm_fn = mock.Mock(side_effect=[hn_response, "body"])
        publish_agent.generate_publish_content(self._data(test_count=999), llm_fn)
        first_call_prompt = llm_fn.call_args_list[0][0][0]
        assert "999" in first_call_prompt


# ---------------------------------------------------------------------------
# format_output
# ---------------------------------------------------------------------------

class TestFormatOutput:
    def _content(self, **kwargs):
        base = {
            "hn_title": "Show HN: Genesis Architect",
            "hn_comment": "Built this after watching teammates fail.",
            "release_title": "v3.0.0 - Big Update",
            "release_body": "## Changes\n\n- Added vault",
        }
        base.update(kwargs)
        return base

    def test_contains_option_1_label(self):
        out = publish_agent.format_output(self._content(), version="3.0.0")
        assert "OPTION 1" in out

    def test_contains_option_2_label(self):
        out = publish_agent.format_output(self._content(), version="3.0.0")
        assert "OPTION 2" in out

    def test_contains_hn_submit_url(self):
        out = publish_agent.format_output(self._content(), version="3.0.0")
        assert "https://news.ycombinator.com/submit" in out

    def test_hn_title_appears_in_output(self):
        content = self._content(hn_title="Show HN: My Custom Title")
        out = publish_agent.format_output(content, version="3.0.0")
        assert "Show HN: My Custom Title" in out

    def test_hn_comment_appears_in_output(self):
        content = self._content(hn_comment="We built this because X.")
        out = publish_agent.format_output(content, version="3.0.0")
        assert "We built this because X." in out

    def test_option_2_browser_prompt_contains_navigate(self):
        out = publish_agent.format_output(self._content(), version="3.0.0")
        assert "navigate to" in out.lower()

    def test_option_2_contains_fill_title(self):
        content = self._content(hn_title="Show HN: Exact Title")
        out = publish_agent.format_output(content, version="3.0.0")
        assert "Show HN: Exact Title" in out

    def test_option_2_contains_fill_text(self):
        content = self._content(hn_comment="Exact comment text.")
        out = publish_agent.format_output(content, version="3.0.0")
        assert "Exact comment text." in out

    def test_github_release_url_present(self):
        out = publish_agent.format_output(self._content(), version="3.0.0")
        assert "github.com/maioio/genesis-architect/releases/new" in out

    def test_version_appears_in_output(self):
        out = publish_agent.format_output(self._content(), version="3.1.0")
        assert "3.1.0" in out

    def test_release_body_appears_in_output(self):
        content = self._content(release_body="## My Release\n\nUnique content here.")
        out = publish_agent.format_output(content, version="3.0.0")
        assert "Unique content here." in out

    def test_output_is_string(self):
        out = publish_agent.format_output(self._content(), version="3.0.0")
        assert isinstance(out, str)

    def test_works_without_version(self):
        out = publish_agent.format_output(self._content())
        assert "OPTION 1" in out
        assert "OPTION 2" in out

    def test_visual_assets_section_present_when_gif_provided(self, tmp_path):
        gif = tmp_path / "action_replay.gif"
        gif.write_bytes(b"GIF")
        psr = {"replay_gif": gif, "screenshots": [], "session_name": "psr_20260519_output"}
        out = publish_agent.format_output(self._content(), version="3.0.0", psr_assets=psr)
        assert "VISUAL ASSETS" in out

    def test_visual_assets_shows_gif_filename(self, tmp_path):
        gif = tmp_path / "action_replay.gif"
        gif.write_bytes(b"GIF")
        psr = {"replay_gif": gif, "screenshots": [], "session_name": "psr_20260519_output"}
        out = publish_agent.format_output(self._content(), version="3.0.0", psr_assets=psr)
        assert "action_replay.gif" in out

    def test_visual_assets_section_absent_when_no_assets(self):
        psr = {"replay_gif": None, "screenshots": [], "session_name": ""}
        out = publish_agent.format_output(self._content(), version="3.0.0", psr_assets=psr)
        assert "VISUAL ASSETS" not in out

    def test_visual_assets_shows_screenshot_count(self, tmp_path):
        shots = []
        for i in range(3):
            p = tmp_path / f"step_{i:03d}.png"
            p.write_bytes(b"PNG")
            shots.append(p)
        psr = {"replay_gif": None, "screenshots": shots, "session_name": "psr_20260519_output"}
        out = publish_agent.format_output(self._content(), version="3.0.0", psr_assets=psr)
        assert "VISUAL ASSETS" in out
        assert "step_000.png" in out

    def test_no_absolute_paths_in_output(self, tmp_path):
        gif = tmp_path / "action_replay.gif"
        gif.write_bytes(b"GIF")
        psr = {"replay_gif": gif, "screenshots": [], "session_name": "psr_session"}
        out = publish_agent.format_output(self._content(), version="3.0.0", psr_assets=psr)
        # Must not expose Windows-style absolute user paths
        import re
        assert not re.search(r"[A-Za-z]:[/\\]Users[/\\]\w+[/\\]", out)


# ---------------------------------------------------------------------------
# sanitize_for_public
# ---------------------------------------------------------------------------

class TestSanitizeForPublic:
    def test_redacts_windows_user_path(self):
        text = r"File at C:\Users\JohnDoe\psr_output\session"
        out = publish_agent.sanitize_for_public(text)
        assert "JohnDoe" not in out
        assert "~" in out

    def test_redacts_windows_path_no_trailing_slash(self):
        text = r"Path: C:\Users\alice"
        out = publish_agent.sanitize_for_public(text)
        assert "alice" not in out

    def test_redacts_posix_home_path(self):
        text = "/home/bobsmith/psr_output/session"
        out = publish_agent.sanitize_for_public(text)
        assert "bobsmith" not in out
        assert "~" in out

    def test_redacts_api_key_sk_ant(self):
        text = "key=sk-ant-api03-abcdefghijk123456"
        out = publish_agent.sanitize_for_public(text)
        assert "abcdefghijk123456" not in out
        assert "[REDACTED]" in out

    def test_redacts_github_pat(self):
        text = "token: ghp_ABCDEFGHIJKLMNOPQRST"
        out = publish_agent.sanitize_for_public(text)
        assert "ABCDEFGHIJKLMNOPQRST" not in out

    def test_safe_text_unchanged(self):
        text = "Genesis Architect v3.0.0 - Added fork analysis."
        out = publish_agent.sanitize_for_public(text)
        assert out == text

    def test_empty_string_unchanged(self):
        assert publish_agent.sanitize_for_public("") == ""

    def test_none_like_empty_handled(self):
        assert publish_agent.sanitize_for_public("") == ""


# ---------------------------------------------------------------------------
# detect_psr_assets
# ---------------------------------------------------------------------------

class TestDetectPsrAssets:
    def _make_session(self, base: Path, name: str, has_gif: bool = True, shot_count: int = 5) -> Path:
        session_dir = base / name
        session_dir.mkdir(parents=True)
        if has_gif:
            (session_dir / "action_replay.gif").write_bytes(b"GIF")
        shots_dir = session_dir / "screenshots"
        shots_dir.mkdir()
        for i in range(shot_count):
            (shots_dir / f"step_{i:03d}.png").write_bytes(b"PNG")
        return session_dir

    def test_returns_none_when_no_psr_dir(self, tmp_path):
        result = publish_agent.detect_psr_assets(tmp_path / "nonexistent")
        assert result["replay_gif"] is None
        assert result["screenshots"] == []

    def test_detects_replay_gif(self, tmp_path):
        self._make_session(tmp_path, "psr_20260519_222400_output")
        result = publish_agent.detect_psr_assets(tmp_path)
        assert result["replay_gif"] is not None
        assert result["replay_gif"].name == "action_replay.gif"

    def test_detects_screenshots(self, tmp_path):
        self._make_session(tmp_path, "psr_20260519_222400_output", shot_count=5)
        result = publish_agent.detect_psr_assets(tmp_path)
        assert len(result["screenshots"]) == 3  # first, middle, last

    def test_picks_latest_session_when_multiple(self, tmp_path):
        self._make_session(tmp_path, "psr_20260518_output")
        import time; time.sleep(0.05)
        self._make_session(tmp_path, "psr_20260519_output")
        result = publish_agent.detect_psr_assets(tmp_path)
        assert result["session_name"] == "psr_20260519_output"

    def test_session_name_is_dirname_not_full_path(self, tmp_path):
        self._make_session(tmp_path, "psr_20260519_222400_output")
        result = publish_agent.detect_psr_assets(tmp_path)
        assert result["session_name"] == "psr_20260519_222400_output"
        assert str(tmp_path) not in result["session_name"]

    def test_no_gif_when_file_absent(self, tmp_path):
        self._make_session(tmp_path, "psr_20260519_output", has_gif=False)
        result = publish_agent.detect_psr_assets(tmp_path)
        assert result["replay_gif"] is None

    def test_screenshots_capped_at_three(self, tmp_path):
        self._make_session(tmp_path, "psr_20260519_output", shot_count=20)
        result = publish_agent.detect_psr_assets(tmp_path)
        assert len(result["screenshots"]) <= 3

    def test_single_screenshot_returned_once(self, tmp_path):
        self._make_session(tmp_path, "psr_20260519_output", shot_count=1)
        result = publish_agent.detect_psr_assets(tmp_path)
        assert len(result["screenshots"]) == 1


# ---------------------------------------------------------------------------
# collect_release_data - psr_assets integration
# ---------------------------------------------------------------------------

class TestCollectReleaseDataPsr:
    def test_psr_assets_included_in_return(self, tmp_path):
        psr_root = tmp_path / "psr_output"
        psr_root.mkdir()
        session = psr_root / "psr_20260519_output"
        session.mkdir()
        (session / "action_replay.gif").write_bytes(b"GIF")

        from unittest import mock
        with mock.patch.object(publish_agent, "_get_recent_commits", return_value=[]):
            with mock.patch.object(publish_agent, "_detect_test_count", return_value=0):
                data = publish_agent.collect_release_data(tmp_path, psr_root=psr_root)

        assert "psr_assets" in data
        assert data["psr_assets"]["replay_gif"] is not None

    def test_psr_assets_empty_when_no_psr_dir(self, tmp_path):
        from unittest import mock
        with mock.patch.object(publish_agent, "_get_recent_commits", return_value=[]):
            with mock.patch.object(publish_agent, "_detect_test_count", return_value=0):
                data = publish_agent.collect_release_data(tmp_path, psr_root=tmp_path / "nonexistent")

        assert data["psr_assets"]["replay_gif"] is None


# ---------------------------------------------------------------------------
# generate_publish_content - visual markdown in release body
# ---------------------------------------------------------------------------

class TestGeneratePublishContentVisual:
    def _data(self, psr_assets=None):
        return {
            "version": "3.0.0",
            "release_notes_raw": "# v3.0.0\n\nAdded fork analysis.",
            "commits": ["abc feat: fork analyzer"],
            "test_count": 316,
            "psr_assets": psr_assets or {"replay_gif": None, "screenshots": [], "session_name": ""},
        }

    def test_release_body_contains_gif_tag_when_gif_present(self, tmp_path):
        gif = tmp_path / "action_replay.gif"
        gif.write_bytes(b"GIF")
        psr = {"replay_gif": gif, "screenshots": [], "session_name": "psr_session"}
        import json
        hn = json.dumps({"title": "Show HN: X", "comment": "Y"})
        llm_fn = __import__("unittest.mock", fromlist=["Mock"]).Mock(side_effect=[hn, "body text"])
        content = publish_agent.generate_publish_content(self._data(psr), llm_fn)
        assert "action_replay.gif" in content["release_body"]

    def test_release_body_no_absolute_paths(self, tmp_path):
        gif = tmp_path / "action_replay.gif"
        gif.write_bytes(b"GIF")
        psr = {"replay_gif": gif, "screenshots": [], "session_name": "psr_session"}
        import json, re
        hn = json.dumps({"title": "Show HN: X", "comment": "Y"})
        llm_fn = __import__("unittest.mock", fromlist=["Mock"]).Mock(side_effect=[hn, "body"])
        content = publish_agent.generate_publish_content(self._data(psr), llm_fn)
        assert not re.search(r"[A-Za-z]:[/\\]Users[/\\]\w+", content["release_body"])

    def test_release_body_clean_when_no_psr_assets(self):
        import json
        hn = json.dumps({"title": "Show HN: X", "comment": "Y"})
        llm_fn = __import__("unittest.mock", fromlist=["Mock"]).Mock(side_effect=[hn, "body text"])
        content = publish_agent.generate_publish_content(self._data(), llm_fn)
        assert "action_replay.gif" not in content["release_body"]
