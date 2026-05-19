"""Tests for scripts/mitigation_enforcer.py - hard mitigation file enforcement."""
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mitigation_enforcer import (
    _parse_pitfalls_from_md,
    _resolve_mitigation_path,
    enforce,
    EnforcementResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PITFALLS_TWO_MAPPED = """\
## Pitfall 1: feedparser hangs
**Seen in**: https://github.com/kurtmckee/feedparser/issues/76
**Our mitigation**: Use requests with timeout.
mitigation_file_path: src/podcast_dl/core/fetcher.py

## Pitfall 2: Path traversal
**Seen in**: https://github.com/pypa/pip/issues/6413
**Our mitigation**: safe_filename() strips separators.
mitigation_file_path: src/podcast_dl/utils/security.py
"""

PITFALLS_ONE_UNMAPPED = """\
## Pitfall 1: feedparser hangs
**Seen in**: https://github.com/kurtmckee/feedparser/issues/76
**Our mitigation**: Use requests with timeout.
"""

PITFALLS_MIXED = """\
## Pitfall 1: feedparser hangs
**Seen in**: https://github.com/kurtmckee/feedparser/issues/76
**Our mitigation**: Use requests.
mitigation_file_path: src/myapp/core/fetcher.py

## Pitfall 2: No mitigation path
**Seen in**: https://github.com/example/repo/issues/1
**Our mitigation**: Fix it somehow.
"""


# ---------------------------------------------------------------------------
# _parse_pitfalls_from_md
# ---------------------------------------------------------------------------

class TestParsePitfallsFromMd:
    def test_parses_two_pitfalls(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_TWO_MAPPED, encoding="utf-8")
        result = _parse_pitfalls_from_md(f)
        assert len(result) == 2

    def test_extracts_mitigation_file_path(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_TWO_MAPPED, encoding="utf-8")
        result = _parse_pitfalls_from_md(f)
        assert result[0]["mitigation_file_path"] == "src/podcast_dl/core/fetcher.py"

    def test_empty_path_when_absent(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_ONE_UNMAPPED, encoding="utf-8")
        result = _parse_pitfalls_from_md(f)
        assert result[0]["mitigation_file_path"] == ""

    def test_extracts_issue_url(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_TWO_MAPPED, encoding="utf-8")
        result = _parse_pitfalls_from_md(f)
        assert "feedparser" in result[0]["issue_url"]


# ---------------------------------------------------------------------------
# _resolve_mitigation_path
# ---------------------------------------------------------------------------

class TestResolveMitigationPath:
    def test_returns_path_when_file_exists(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "security.py").write_text("# ok")
        result = _resolve_mitigation_path("src/security.py", tmp_path)
        assert result is not None
        assert result.exists()

    def test_returns_none_when_file_missing(self, tmp_path):
        result = _resolve_mitigation_path("src/nonexistent.py", tmp_path)
        assert result is None

    def test_blocks_traversal(self, tmp_path):
        result = _resolve_mitigation_path("../../../etc/passwd", tmp_path)
        assert result is None

    def test_empty_path_returns_none(self, tmp_path):
        result = _resolve_mitigation_path("", tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# enforce() - core enforcement logic
# ---------------------------------------------------------------------------

class TestEnforce:
    def test_all_present_returns_ok(self, tmp_path):
        # Create the mitigation files with substantive code (comment-only files fail the stub check)
        (tmp_path / "src" / "podcast_dl" / "core").mkdir(parents=True)
        (tmp_path / "src" / "podcast_dl" / "utils").mkdir(parents=True)
        (tmp_path / "src" / "podcast_dl" / "core" / "fetcher.py").write_text(
            "import requests\ndef fetch(url): return requests.get(url, timeout=10)\n"
        )
        (tmp_path / "src" / "podcast_dl" / "utils" / "security.py").write_text(
            "from pathlib import Path\ndef safe_path(base, p): return Path(base) / Path(p).name\n"
        )

        pitfalls = [
            {"id": "pitfall_1", "name": "feedparser hangs",
             "mitigation_file_path": "src/podcast_dl/core/fetcher.py"},
            {"id": "pitfall_2", "name": "path traversal",
             "mitigation_file_path": "src/podcast_dl/utils/security.py"},
        ]
        result = enforce(pitfalls, tmp_path)
        assert result.ok
        assert len(result.passed) == 2
        assert len(result.failed) == 0
        assert len(result.unmapped) == 0

    def test_missing_file_goes_to_failed(self, tmp_path):
        pitfalls = [
            {"id": "pitfall_1", "name": "feedparser hangs",
             "mitigation_file_path": "src/nonexistent/fetcher.py"},
        ]
        result = enforce(pitfalls, tmp_path)
        assert not result.ok
        assert len(result.failed) == 1
        assert result.failed[0]["id"] == "pitfall_1"

    def test_empty_mitigation_path_goes_to_unmapped(self, tmp_path):
        pitfalls = [
            {"id": "pitfall_1", "name": "some pitfall", "mitigation_file_path": ""},
        ]
        result = enforce(pitfalls, tmp_path)
        assert not result.ok
        assert len(result.unmapped) == 1

    def test_mixed_passed_failed_unmapped(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "exists.py").write_text("def check(): return True\n")

        pitfalls = [
            {"id": "pitfall_1", "name": "ok pitfall",
             "mitigation_file_path": "src/exists.py"},
            {"id": "pitfall_2", "name": "missing pitfall",
             "mitigation_file_path": "src/missing.py"},
            {"id": "pitfall_3", "name": "unmapped pitfall",
             "mitigation_file_path": ""},
        ]
        result = enforce(pitfalls, tmp_path)
        assert not result.ok
        assert len(result.passed) == 1
        assert len(result.failed) == 1
        assert len(result.unmapped) == 1

    def test_empty_pitfall_list_is_ok(self, tmp_path):
        result = enforce([], tmp_path)
        assert result.ok


# ---------------------------------------------------------------------------
# EnforcementResult.summary
# ---------------------------------------------------------------------------

class TestEnforcementResultSummary:
    def test_summary_contains_counts(self, tmp_path):
        pitfalls = [
            {"id": "p1", "name": "ok", "mitigation_file_path": "src/missing.py"},
        ]
        result = enforce(pitfalls, tmp_path)
        summary = result.summary()
        assert "0/1" in summary or "missing" in summary.lower()


# ---------------------------------------------------------------------------
# CLI integration: main() via subprocess (proves exit code)
# ---------------------------------------------------------------------------

class TestMainExitCodes:
    def test_exits_0_when_all_files_present(self, tmp_path):
        import subprocess
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "fetcher.py").write_text("def fetch(url): return url\n")
        pitfalls_md = tmp_path / "PITFALLS.md"
        pitfalls_md.write_text(
            "## Pitfall 1: Test\n"
            "**Seen in**: https://github.com/example/repo/issues/1\n"
            "**Our mitigation**: Use fetcher.\n"
            "mitigation_file_path: src/fetcher.py\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable,
             str(ROOT / "scripts" / "mitigation_enforcer.py"),
             str(pitfalls_md),
             "--src-root", str(tmp_path)],
            capture_output=True,
        )
        assert result.returncode == 0

    def test_exits_1_when_file_missing(self, tmp_path):
        import subprocess
        pitfalls_md = tmp_path / "PITFALLS.md"
        pitfalls_md.write_text(
            "## Pitfall 1: Test\n"
            "**Seen in**: https://github.com/example/repo/issues/1\n"
            "**Our mitigation**: Use fetcher.\n"
            "mitigation_file_path: src/does_not_exist.py\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable,
             str(ROOT / "scripts" / "mitigation_enforcer.py"),
             str(pitfalls_md),
             "--src-root", str(tmp_path)],
            capture_output=True,
        )
        # This is the key DoD test: missing mitigation file -> exit 1
        assert result.returncode == 1

    def test_exits_1_when_pitfall_unmapped(self, tmp_path):
        import subprocess
        pitfalls_md = tmp_path / "PITFALLS.md"
        pitfalls_md.write_text(
            "## Pitfall 1: No path\n"
            "**Seen in**: https://github.com/example/repo/issues/1\n"
            "**Our mitigation**: Not mapped yet.\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable,
             str(ROOT / "scripts" / "mitigation_enforcer.py"),
             str(pitfalls_md),
             "--src-root", str(tmp_path)],
            capture_output=True,
        )
        assert result.returncode == 1
