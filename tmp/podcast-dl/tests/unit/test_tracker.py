"""Tests for core/tracker.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from podcast_dl.core.tracker import load_state, save_state, is_downloaded, mark_downloaded


class TestStateRoundtrip:
    def test_empty_when_no_file(self, tmp_path):
        assert load_state(tmp_path / "s.json") == set()

    def test_save_and_reload(self, tmp_path):
        p = tmp_path / "s.json"
        urls = {"https://example.com/ep1.mp3", "https://example.com/ep2.mp3"}
        save_state(p, urls)
        assert load_state(p) == urls

    def test_is_downloaded_true(self):
        state = {"https://example.com/ep1.mp3"}
        assert is_downloaded("https://example.com/ep1.mp3", state) is True

    def test_is_downloaded_false(self):
        assert is_downloaded("https://example.com/other.mp3", {"https://x.com/a.mp3"}) is False

    def test_mark_downloaded_adds(self):
        state: set[str] = set()
        mark_downloaded("https://example.com/ep.mp3", state)
        assert "https://example.com/ep.mp3" in state

    def test_corrupted_file_returns_empty(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text("not json", encoding="utf-8")
        assert load_state(p) == set()

    def test_atomic_write_no_tmp_leftover(self, tmp_path):
        p = tmp_path / "s.json"
        save_state(p, {"https://x.com/ep.mp3"})
        assert p.exists()
        assert not (tmp_path / "s.tmp").exists()
