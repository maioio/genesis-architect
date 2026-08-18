"""Tests for research_orchestrator module - no network, no disk I/O."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genesis_architect.pro.research_orchestrator import (
    ResearchSummary,
    RepoResult,
    build_summary_from_raw,
    check_floor,
    compute_quality,
    merge_streams,
    format_summary,
    FLOOR_MIN_REPOS,
    FLOOR_MIN_DEEP,
    classify_domain,
    normalize_streams,
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
    from genesis_architect.pro.pitfall_ranker import RankedPitfall
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




# --- domain-aware floor (a non-code vision has no repo corpus) ---

def test_classify_domain_code_vision():
    assert classify_domain("build a FastAPI service with a Postgres backend") == "code"
    assert classify_domain("a CLI tool for log parsing") == "code"


def test_classify_domain_non_code_vision():
    assert classify_domain(
        "extract a house standard from a design studio archive"
    ) == "non_code"
    assert classify_domain("write onboarding guidelines for new editorial hires") == "non_code"


def test_classify_domain_ties_resolve_to_code():
    """Biased toward code: weakening the repo floor is the costlier mistake."""
    assert classify_domain("something entirely ambiguous") == "code"


def test_non_code_floor_counts_sources_not_repos():
    """A non-repo-shaped problem must not fail on a repo count it can never meet."""
    topics = ["tracking metrics", "baseline grid", "colour proofing", "kerning pairs",
              "paper stock", "logo clearspace", "export presets", "archive naming",
              "print bleed"]
    web = [
        {"url": f"https://community.example{i}.com/thread/{i}",
         "title": f"House rule for {topic}",
         "text": "```css\n.tracking { letter-spacing: 0.02em; }\n```"}
        for i, topic in enumerate(topics)
    ]
    s = build_summary_from_raw(
        "extract a house standard from a studio archive",
        repos=[], github_issues=[], web_results=web, media_results=[],
    )
    assert s.domain == "non_code"
    passed, message = check_floor(s)
    assert passed, message
    assert "repos are not the unit" in message


def test_non_code_floor_still_blocks_thin_research():
    """The gate must survive the domain switch - only its unit changes."""
    s = build_summary_from_raw(
        "extract a house standard from a studio archive",
        repos=[], github_issues=[],
        web_results=[{"url": "https://a-blog.com/p", "title": "One post", "text": "prose"}],
        media_results=[],
    )
    assert check_floor(s)[0] is False
    assert "Floor not met" in check_floor(s)[1]


def test_code_floor_message_offers_the_domain_escape():
    s = build_summary_from_raw("build a CLI tool", _repos(2), [], [], [])
    assert "--domain non-code" in check_floor(s)[1]


# --- stream naming (provider-neutral, back-compatible) ---

def test_legacy_stream_keys_still_load():
    raw = {"exa_results": [{"url": "https://a.com", "title": "t", "text": "x"}],
           "video_exa_results": [{"url": "https://youtube.com/watch?v=1", "title": "talk"}]}
    normalized = normalize_streams(raw)
    assert "exa_results" not in normalized
    assert len(normalized["web_results"]) == 1
    assert len(normalized["media_results"]) == 1


def test_legacy_and_canonical_keys_merge_rather_than_overwrite():
    raw = {"web_results": [{"url": "https://a.com", "title": "a"}],
           "exa_results": [{"url": "https://b.com", "title": "b"}]}
    assert len(normalize_streams(raw)["web_results"]) == 2


def test_build_summary_accepts_legacy_kwargs():
    s = build_summary_from_raw(
        "test", _repos(1), [],
        exa_results=[{"url": "https://a.com", "title": "t", "text": "x"}],
    )
    assert len(s.pitfall_candidates) == 1


def test_provider_recorded_per_item_not_in_the_field_name():
    s = build_summary_from_raw(
        "test", [], [],
        web_results=[{"url": "https://a.com", "title": "t", "text": "x",
                      "provider": "tavily"}],
    )
    assert s.pitfall_candidates[0].provider == "tavily"


# --- machine-readable output ---

def test_to_dict_is_json_serializable_and_carries_the_verdict():
    import json
    s = build_summary_from_raw("build a CLI tool", _repos(3), [], [], [])
    payload = s.to_dict()
    assert json.loads(json.dumps(payload))["domain"] == "code"
    assert payload["floor_met"] is False
    assert "floor_message" in payload
    assert payload["repos"][0]["slug"] == "owner/repo0"


def test_summary_names_the_command_that_closes_the_video_loop():
    """Stream D hands out /watch commands; the return leg must be named too."""
    s = build_summary_from_raw(
        "a task queue service", repos=[], github_issues=[], web_results=[],
        media_results=[{"url": "https://www.youtube.com/watch?v=1",
                        "title": "Lessons learned running queues",
                        "text": "what we wish we knew"}],
    )
    output = format_summary(s)
    assert "--absorb" in output
    assert "a task queue service" in output
