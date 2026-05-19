"""Tests for utils/security.py."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from podcast_dl.utils.security import safe_filename, safe_output_path, PathTraversalError


class TestSafeFilename:
    def test_strips_path_separators(self):
        result = safe_filename("../../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result

    def test_strips_null_bytes(self):
        assert "\x00" not in safe_filename("episode\x00evil")

    def test_strips_windows_illegal_chars(self):
        result = safe_filename('ep: "title" <best> *ever*')
        for ch in ':"<>*?|':
            assert ch not in result

    def test_non_ascii_to_ascii(self):
        assert safe_filename("Podcast mit Umlauten").isascii()

    def test_empty_returns_fallback(self):
        assert safe_filename("") == "episode"

    def test_truncates_to_max_length(self):
        assert len(safe_filename("a" * 300)) <= 200

    def test_only_illegal_chars_returns_fallback(self):
        assert safe_filename("???***///")  # non-empty


class TestSafeOutputPath:
    def test_valid_path_resolves(self, tmp_path):
        result = safe_output_path(tmp_path, "episode.mp3")
        assert result == (tmp_path / "episode.mp3").resolve()

    def test_traversal_raises(self, tmp_path):
        with pytest.raises(PathTraversalError):
            safe_output_path(tmp_path, "../outside.mp3")
