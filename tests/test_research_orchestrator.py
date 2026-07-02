"""Tests for research_orchestrator module - no network, no disk I/O."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


@pytest.fixture(autouse=True)
def _licensed(monkeypatch):
    """Orchestrator is a licensed Pro feature. These tests assert behavior, not
    the gate (the gate itself is covered by test_license.py), so grant a license
    for their duration."""
    monkeypatch.setattr("genesis_architect_pro.license.is_licensed", lambda: True)


from genesis_architect_pro.research_orchestrator import (
    ResearchSummary,
    RepoResult,
    build_summary_from_raw,
    check_floor,
    compute_quality,
    merge_streams,
    format_summary,
    FLOOR_MIN_REPOS,
    FLOOR_MIN_DEEP,
)


# --- helpers ---

def _repos(n: int, deep: int = 0) -> list[dict]:
    return [
        {"name": f"owner/repo{i}", "stars": 100 + i, "url": f"https://github.com/owner/repo{i}",
         "description": f"Repo {i}", "deep_analyzed": i < deep}
        for i in range(n)
    ]


def _issues(n: int) -> list[dict]:
    return [
        {"title": f"Issue {i}", "url": f"https://github.com/owner/repo/issues/{i}",
         "comments": 6, "reactions": 4, "category": "bug", "labels": ["bug"], "body": ""}
        for i in range(n)
    ]


# --- floor gate ---

def test_floor_passes_with_enough_repos():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, f"https://github.com/o/r{i}", "", i < 6)
                     for i in range(13)]
    ok, _ = check_floor(summary)
    assert ok


def test_floor_fails_too_few_repos():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, "", "", True) for i in range(5)]
    ok, msg = check_floor(summary)
    assert not ok
    assert "Floor not met" in msg


def test_floor_fails_too_few_deep():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, "", "", i < 2) for i in range(13)]
    ok, _ = check_floor(summary)
    assert not ok


def test_floor_message_includes_options():
    summary = ResearchSummary(vision="test")
    summary.repos = []
    _, msg = check_floor(summary)
    assert "Broaden" in msg or "override" in msg or "Architect" in msg


# --- quality signal ---

def test_quality_full():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, "", "", True) for i in range(9)]
    from genesis_architect_pro.pitfall_ranker import RankedPitfall
    summary.pitfall_candidates = [
        RankedPitfall(f"Issue {i}", f"https://x/{i}", "github_issues", "high", "pitfall", "x")
        for i in range(6)
    ]
    assert compute_quality(summary) == "FULL"


def test_quality_thin():
    summary = ResearchSummary(vision="test")
    summary.repos = []
    summary.pitfall_candidates = []
    assert compute_quality(summary) == "THIN"


def test_quality_partial():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, "", "", True) for i in range(6)]
    summary.pitfall_candidates = []
    assert compute_quality(summary) == "PARTIAL"


# --- merge_streams ---

def test_merge_streams_github_issues():
    issues = _issues(3)
    ranked, _ = merge_streams(issues, [], [], "FastAPI")
    assert len(ranked) > 0
    assert all(p.source == "github_issues" for p in ranked)


def test_merge_streams_exa_results():
    exa = [{"url": "https://reddit.com/r/python/comments/abc",
             "title": "FastAPI lessons learned", "text": "avoid sync in async", "score": 60}]
    ranked, _ = merge_streams([], exa, [], "FastAPI")
    assert any(p.source == "reddit" for p in ranked)


def test_merge_streams_video_signals():
    video_exa = [{"url": "https://youtube.com/watch?v=abc",
                  "title": "FastAPI mistakes postmortem", "text": "we learned the hard way",
                  "author": "DevChannel"}]
    ranked, video_signals = merge_streams([], [], video_exa, "FastAPI")
    assert len(video_signals) > 0


def test_merge_streams_ranked_descending():
    issues = _issues(5)
    ranked, _ = merge_streams(issues, [], [], "test")
    scores = [p.score for p in ranked]
    assert scores == sorted(scores, reverse=True)


def test_merge_streams_caps_at_10():
    issues = _issues(20)
    ranked, _ = merge_streams(issues, [], [], "test")
    assert len(ranked) <= 10


# --- build_summary_from_raw ---

def test_build_summary_sets_vision():
    s = build_summary_from_raw("My FastAPI App", _repos(5), [], [], [])
    assert s.vision == "My FastAPI App"


def test_build_summary_computes_quality():
    s = build_summary_from_raw("test", _repos(2), [], [], [])
    assert s.research_quality in ("FULL", "PARTIAL", "THIN")


def test_build_summary_vault_save(tmp_path):
    s = build_summary_from_raw("test vision", _repos(3), _issues(2), [], [],
                                project_root=tmp_path)
    assert s.vision == "test vision"
    vault_file = tmp_path / ".genesis" / "vault" / "index.json"
    assert vault_file.exists()


def test_build_summary_floor_flag():
    s = build_summary_from_raw("test", _repos(FLOOR_MIN_REPOS + 1, deep=FLOOR_MIN_DEEP + 1),
                                _issues(6), [], [])
    assert s.floor_met is True


# --- format_summary ---

def test_format_summary_includes_quality():
    s = build_summary_from_raw("test", [], [], [], [])
    output = format_summary(s)
    assert "Research quality" in output or "THIN" in output


def test_format_summary_shows_repos():
    s = build_summary_from_raw("test", _repos(3), [], [], [])
    output = format_summary(s)
    assert "repo" in output.lower() or "owner" in output.lower()


def test_format_summary_floor_warning_when_not_met():
    s = build_summary_from_raw("test", _repos(2), [], [], [])
    output = format_summary(s)
    assert "Floor not met" in output or "Options" in output or "Broaden" in output


# --- SKILL.md integration ---


