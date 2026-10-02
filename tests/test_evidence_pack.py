"""Tests for scripts/evidence_pack.py - evidence pack generation and verification."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

from genesis_architect.core.evidence_pack import (
    _parse_pitfalls,
    _parse_repos,
    _parse_exec_summary,
    _parse_roadmap_phases,
    generate,
    verify,
)


# ---------------------------------------------------------------------------
# Fixtures: minimal valid documents
# ---------------------------------------------------------------------------

MINIMAL_RESEARCH = """\
# Genesis Architect Research Report - test-project

## Executive Summary

This is a test summary for a podcast downloader CLI.

## Analyzed Repositories

| Project | Stars | Last active | Key insight |
|---|---|---|---|
| [dplocki/podcast-downloader](https://github.com/dplocki/podcast-downloader) | 143 | 2026 | Config-driven |
| [kissgyorgy/simple-podcast-dl](https://github.com/kissgyorgy/simple-podcast-dl) | 56 | 2025 | requests-first |
| [m3nu/upodder](https://github.com/m3nu/upodder) | 60 | 2024 | Cron-friendly |

## Architecture Decision Rationale

Scalable tier chosen. requests-first HTTP; file-based state; safe_filename() for paths.

## Sources

- https://github.com/kurtmckee/feedparser/issues/76
"""

MINIMAL_PITFALLS = """\
# Engineering Pitfalls Report

## Pitfall 1: feedparser hangs on slow feeds

**Seen in**: https://github.com/kurtmckee/feedparser/issues/76
**Frequency**: Found in 4 of 5 repos
**Root cause**: No timeout on feedparser HTTP.
**Our mitigation**: Use requests.get(timeout=10).
mitigation_file_path: src/podcast_dl/core/fetcher.py

## Pitfall 2: Path traversal via enclosure filename

**Seen in**: https://github.com/pypa/pip/issues/6413
**Frequency**: Found in 3 of 5 repos
**Root cause**: ../segments in URL filenames.
**Our mitigation**: safe_filename() strips path separators.
mitigation_file_path: src/podcast_dl/utils/security.py
"""

PITFALLS_MISSING_PATH = """\
# Engineering Pitfalls Report

## Pitfall 1: feedparser hangs

**Seen in**: https://github.com/kurtmckee/feedparser/issues/76
**Frequency**: 4 of 5 repos
**Root cause**: No timeout.
**Our mitigation**: Use requests with timeout.
"""

MINIMAL_ROADMAP = """\
# Roadmap

## Phase 1: Core Download Loop

Single feed, sequential download.

## Phase 2: Concurrency

Parallel downloads.
"""


# ---------------------------------------------------------------------------
# _parse_pitfalls
# ---------------------------------------------------------------------------

class TestParsePitfalls:
    def test_parses_two_pitfalls(self):
        pitfalls = _parse_pitfalls(MINIMAL_PITFALLS)
        assert len(pitfalls) == 2

    def test_extracts_id(self):
        pitfalls = _parse_pitfalls(MINIMAL_PITFALLS)
        assert pitfalls[0]["id"] == "pitfall_1"
        assert pitfalls[1]["id"] == "pitfall_2"

    def test_extracts_name(self):
        pitfalls = _parse_pitfalls(MINIMAL_PITFALLS)
        assert "feedparser" in pitfalls[0]["name"].lower()

    def test_extracts_issue_url(self):
        pitfalls = _parse_pitfalls(MINIMAL_PITFALLS)
        assert "feedparser/issues/76" in pitfalls[0]["issue_url"]

    def test_extracts_mitigation_file_path(self):
        pitfalls = _parse_pitfalls(MINIMAL_PITFALLS)
        assert pitfalls[0]["mitigation_file_path"] == "src/podcast_dl/core/fetcher.py"
        assert pitfalls[1]["mitigation_file_path"] == "src/podcast_dl/utils/security.py"

    def test_missing_mitigation_path_is_empty_string(self):
        pitfalls = _parse_pitfalls(PITFALLS_MISSING_PATH)
        assert pitfalls[0]["mitigation_file_path"] == ""


# ---------------------------------------------------------------------------
# _parse_repos
# ---------------------------------------------------------------------------

class TestParseRepos:
    def test_parses_three_repos(self):
        repos = _parse_repos(MINIMAL_RESEARCH)
        assert len(repos) == 3

    def test_extracts_name_from_link(self):
        repos = _parse_repos(MINIMAL_RESEARCH)
        assert repos[0]["name"] == "dplocki/podcast-downloader"

    def test_extracts_url(self):
        repos = _parse_repos(MINIMAL_RESEARCH)
        assert "github.com/dplocki" in repos[0]["url"]

    def test_extracts_stars(self):
        repos = _parse_repos(MINIMAL_RESEARCH)
        assert repos[0]["stars"] == "143"


# ---------------------------------------------------------------------------
# _parse_exec_summary
# ---------------------------------------------------------------------------

class TestParseExecSummary:
    def test_extracts_summary(self):
        summary = _parse_exec_summary(MINIMAL_RESEARCH)
        assert "podcast downloader" in summary.lower()

    def test_empty_when_missing(self):
        assert _parse_exec_summary("# No sections here\n") == ""


# ---------------------------------------------------------------------------
# _parse_roadmap_phases
# ---------------------------------------------------------------------------

class TestParseRoadmapPhases:
    def test_parses_two_phases(self):
        phases = _parse_roadmap_phases(MINIMAL_ROADMAP)
        assert len(phases) == 2

    def test_phase_name(self):
        phases = _parse_roadmap_phases(MINIMAL_ROADMAP)
        assert "Phase 1" in phases[0]["name"]

    def test_phase_summary(self):
        phases = _parse_roadmap_phases(MINIMAL_ROADMAP)
        assert phases[0]["summary"]  # non-empty


# ---------------------------------------------------------------------------
# generate() - integration
# ---------------------------------------------------------------------------

class TestGenerate:
    def _setup(self, tmp_path: Path, pitfalls_content: str = MINIMAL_PITFALLS) -> Path:
        (tmp_path / "RESEARCH.md").write_text(MINIMAL_RESEARCH, encoding="utf-8")
        (tmp_path / "PITFALLS.md").write_text(pitfalls_content, encoding="utf-8")
        (tmp_path / "ROADMAP.md").write_text(MINIMAL_ROADMAP, encoding="utf-8")
        return tmp_path

    def test_returns_0_on_success(self, tmp_path):
        self._setup(tmp_path)
        rc = generate(str(tmp_path))
        assert rc == 0

    def test_creates_architecture_evidence_md(self, tmp_path):
        self._setup(tmp_path)
        generate(str(tmp_path))
        assert (tmp_path / "ARCHITECTURE_EVIDENCE.md").exists()

    def test_creates_evidence_json(self, tmp_path):
        self._setup(tmp_path)
        generate(str(tmp_path))
        assert (tmp_path / ".genesis" / "evidence.json").exists()

    def test_evidence_json_has_pitfalls(self, tmp_path):
        self._setup(tmp_path)
        generate(str(tmp_path))
        data = json.loads((tmp_path / ".genesis" / "evidence.json").read_text())
        assert len(data["pitfalls"]) == 2

    def test_evidence_md_contains_risk_table(self, tmp_path):
        self._setup(tmp_path)
        generate(str(tmp_path))
        content = (tmp_path / "ARCHITECTURE_EVIDENCE.md").read_text(encoding="utf-8")
        assert "Risks Found" in content
        assert "MAPPED" in content

    def test_evidence_md_contains_validations_section(self, tmp_path):
        self._setup(tmp_path)
        generate(str(tmp_path))
        content = (tmp_path / "ARCHITECTURE_EVIDENCE.md").read_text(encoding="utf-8")
        assert "genesis_subcommands.py validate" in content

    def test_returns_1_when_pitfalls_md_missing(self, tmp_path):
        (tmp_path / "RESEARCH.md").write_text(MINIMAL_RESEARCH, encoding="utf-8")
        (tmp_path / "ROADMAP.md").write_text(MINIMAL_ROADMAP, encoding="utf-8")
        rc = generate(str(tmp_path))
        assert rc == 1


# ---------------------------------------------------------------------------
# verify() - integration
# ---------------------------------------------------------------------------

class TestVerify:
    def _full_setup(self, tmp_path: Path) -> Path:
        (tmp_path / "RESEARCH.md").write_text(MINIMAL_RESEARCH, encoding="utf-8")
        (tmp_path / "PITFALLS.md").write_text(MINIMAL_PITFALLS, encoding="utf-8")
        (tmp_path / "ROADMAP.md").write_text(MINIMAL_ROADMAP, encoding="utf-8")
        generate(str(tmp_path))
        return tmp_path

    def test_returns_0_when_all_mapped(self, tmp_path):
        self._full_setup(tmp_path)
        rc = verify(str(tmp_path))
        assert rc == 0

    def test_returns_1_when_evidence_md_missing(self, tmp_path):
        rc = verify(str(tmp_path))
        assert rc == 1

    def test_returns_1_when_unmapped_pitfall(self, tmp_path):
        (tmp_path / "RESEARCH.md").write_text(MINIMAL_RESEARCH, encoding="utf-8")
        (tmp_path / "PITFALLS.md").write_text(PITFALLS_MISSING_PATH, encoding="utf-8")
        (tmp_path / "ROADMAP.md").write_text(MINIMAL_ROADMAP, encoding="utf-8")
        generate(str(tmp_path))
        rc = verify(str(tmp_path))
        assert rc == 1

    def test_unmapped_error_message_is_clear(self, tmp_path, capsys):
        (tmp_path / "RESEARCH.md").write_text(MINIMAL_RESEARCH, encoding="utf-8")
        (tmp_path / "PITFALLS.md").write_text(PITFALLS_MISSING_PATH, encoding="utf-8")
        (tmp_path / "ROADMAP.md").write_text(MINIMAL_ROADMAP, encoding="utf-8")
        generate(str(tmp_path))
        verify(str(tmp_path))
        err = capsys.readouterr().err
        assert "mitigation_file_path" in err or "unmapped" in err.lower() or "mapped" in err.lower()
