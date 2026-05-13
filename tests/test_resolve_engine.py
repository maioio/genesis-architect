"""Tests for scripts/resolve_engine.py - offline/unit tests only."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from resolve_engine import _strip_html, _truncate, Answer
from datetime import datetime, timezone


class TestStripHtml:
    def test_removes_basic_tags(self):
        assert "<p>" not in _strip_html("<p>hello</p>")

    def test_converts_code_tags(self):
        result = _strip_html("<code>os.path.join()</code>")
        assert "`os.path.join()`" in result

    def test_decodes_html_entities(self):
        result = _strip_html("&lt;div&gt; &amp; &gt;")
        assert "<div>" in result
        assert "&" in result

    def test_empty_string(self):
        assert _strip_html("") == ""


class TestTruncate:
    def test_short_text_unchanged(self):
        text = "short text"
        assert _truncate(text, max_chars=100) == text

    def test_long_text_truncated(self):
        text = "word " * 200
        result = _truncate(text, max_chars=50)
        assert len(result) <= 60
        assert result.endswith("...")

    def test_strips_html_before_truncating(self):
        text = "<p>" + "word " * 100 + "</p>"
        result = _truncate(text, max_chars=50)
        assert "<p>" not in result


class TestAnswer:
    def test_is_recent_for_new_answer(self):
        recent_ts = int(datetime.now(timezone.utc).timestamp()) - 86400
        a = Answer(1, 10, True, "body", "https://so.com/a/1", recent_ts)
        assert a.is_recent is True

    def test_is_not_recent_for_old_answer(self):
        old_ts = int(datetime.now(timezone.utc).timestamp()) - (3 * 365 * 86400)
        a = Answer(2, 10, False, "body", "https://so.com/a/2", old_ts)
        assert a.is_recent is False
