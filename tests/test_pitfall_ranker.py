"""Tests for pitfall_ranker module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genesis_architect.pro.pitfall_ranker import (
    RankedPitfall,
    deduplicate,
    score,
    rank,
    from_github_issue,
    from_exa_result,
    from_web_result,
    days_old_from,
    why_ranked,
    format_ranked,
    _title_tokens,
    _similar,
)


def _make(title="Memory leak in worker", url="https://github.com/a/b/issues/1",
          source="github_issues", confidence="high", signal_type="pitfall",
          engagement=10, days_old=90) -> RankedPitfall:
    return RankedPitfall(
        title=title, url=url, source=source, confidence=confidence,
        signal_type=signal_type, raw_text=title[:100],
        engagement=engagement, days_old=days_old,
    )


# --- scoring ---

def test_high_confidence_scores_more_than_low():
    high = _make(confidence="high")
    low = _make(confidence="low")
    assert score(high) > score(low)


def test_recent_issue_scores_more():
    recent = _make(days_old=100)
    old = _make(days_old=800)
    assert score(recent) > score(old)


def test_corroboration_adds_points():
    p = _make()
    p.corroborated_by = ["https://reddit.com/r/x/comments/abc"]
    assert score(p) > score(_make())


def test_high_engagement_adds_bonus():
    engaged = _make(engagement=15)
    low_eng = _make(engagement=2)
    assert score(engaged) > score(low_eng)


def test_unknown_days_no_recency_bonus():
    p = _make(days_old=-1)
    p2 = _make(days_old=100)
    assert score(p) < score(p2)


# --- deduplication ---

def test_similar_titles_merged():
    a = _make("Memory leak in connection pool", "https://github.com/a/b/issues/1")
    b = _make("Memory leak in connection pool causes OOM", "https://github.com/a/b/issues/2")
    result = deduplicate([a, b])
    assert len(result) == 1


def test_dissimilar_titles_not_merged():
    a = _make("Memory leak in worker", "https://github.com/a/b/issues/1")
    b = _make("Slow startup time on Windows", "https://github.com/a/b/issues/2")
    result = deduplicate([a, b])
    assert len(result) == 2


def test_corroboration_upgrades_confidence():
    a = _make("Memory leak", "https://github.com/a/b/issues/1", confidence="medium")
    b = _make("Memory leak in pool", "https://reddit.com/r/x", source="reddit", confidence="low")
    result = deduplicate([a, b])
    assert result[0].confidence == "high"


def test_engagement_summed_after_merge():
    a = _make("Memory leak in pool", "https://github.com/a/b/issues/1", engagement=5)
    b = _make("Memory leak pool crash", "https://github.com/a/b/issues/2", engagement=8)
    result = deduplicate([a, b])
    assert result[0].engagement == 13


# --- ranking ---

def test_rank_returns_at_most_top_n():
    pitfalls = [_make(title=f"Issue {i}", url=f"https://github.com/a/b/issues/{i}") for i in range(20)]
    result = rank(pitfalls, top_n=5)
    assert len(result) <= 5


def test_rank_sorted_descending():
    pitfalls = [
        _make("Old issue", days_old=800, confidence="low"),
        _make("New critical", "https://github.com/a/b/issues/99", days_old=10, confidence="high", engagement=20),
    ]
    result = rank(pitfalls)
    assert result[0].title == "New critical"


def test_rank_sets_score_field():
    p = _make()
    result = rank([p])
    assert result[0].score > 0


# --- converters ---

def test_from_github_issue_dict():
    issue = {
        "title": "Connection pool exhausted",
        "url": "https://github.com/a/b/issues/42",
        "comments": 8, "reactions": 3,
        "category": "performance", "labels": ["bug"], "body": "",
    }
    p = from_github_issue(issue)
    assert p.source == "github_issues"
    assert p.engagement == 11
    assert p.confidence == "high"


def test_from_github_issue_low_engagement():
    issue = {"title": "Minor bug", "url": "https://github.com/a/b/issues/1",
             "comments": 1, "reactions": 0, "category": "bug", "labels": [], "body": ""}
    p = from_github_issue(issue)
    assert p.confidence == "medium"


def test_from_exa_result_reddit():
    r = {"url": "https://reddit.com/r/python/comments/abc", "title": "Pitfalls using asyncio",
         "text": "Avoid mixing sync and async", "comments": 60, "provider": "tavily"}
    p = from_exa_result(r)
    assert p.source == "reddit"
    assert p.engagement == 60
    assert p.confidence == "high"
    assert p.provider == "tavily"


def test_provider_relevance_is_not_engagement():
    """A search provider's `score` is query relevance, not human attention.

    Feeding it into engagement is what made every web result rank identically:
    the value is a 0.0-1.0 float, so the engagement bonus could never fire and
    the confidence upgrade fired on nothing.
    """
    r = {"url": "https://reddit.com/r/python/comments/abc", "title": "Pitfalls",
         "text": "Avoid mixing sync and async", "score": 0.93}
    p = from_exa_result(r)
    assert p.relevance == 0.93
    assert p.engagement == 0
    assert p.confidence == "medium"   # not upgraded by a relevance float


def test_from_exa_result_blog():
    r = {"url": "https://some-blog.com/post", "title": "My experience",
         "text": "Lessons learned", "score": 0.5}
    p = from_exa_result(r)
    assert p.source == "web"
    assert p.confidence == "low"


# --- engagement-free ranking signals ---

def test_official_host_outranks_marketing_page_without_engagement():
    """The tie the ranker used to produce: neither result carries engagement."""
    forum = from_exa_result({
        "url": "https://community.adobe.com/t5/photoshop/scripting-crash/td-p/1",
        "title": "Script crashes on batch export",
        "text": "app.activeDocument.exportDocument(file, ExportType.SAVEFORWEB);\n"
                "Fails after 250 files, takes 1200ms per doc on v24.1.",
    })
    agency = from_exa_result({
        "url": "https://some-agency.com/services/photoshop-automation",
        "title": "Photoshop automation done right",
        "text": "We help brands scale their creative production with automation.",
    })
    ranked = rank([agency, forum])
    assert ranked[0].url.startswith("https://community.adobe.com")
    assert ranked[0].score > ranked[1].score


def test_days_old_parsed_from_source_dates():
    """Recency was dead code: every converter hard-coded days_old=-1."""
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    p = from_exa_result({"url": "https://x.com/a", "title": "t", "text": "b",
                         "published_date": recent})
    assert 25 <= p.days_old <= 35
    assert score(p) > score(from_exa_result(
        {"url": "https://x.com/a", "title": "t", "text": "b"}))


def test_missing_date_stays_unknown():
    p = from_exa_result({"url": "https://x.com/a", "title": "t", "text": "b"})
    assert p.days_old == -1


def test_score_breakdown_explains_the_rank():
    p = from_exa_result({
        "url": "https://forums.example.org/thread/1",
        "title": "Export pipeline breaks",
        "text": "```python\nexport(doc)\n```",
    })
    score(p)
    assert p.score_breakdown["authority"] == 2.0
    assert p.score_breakdown["substance"] >= 1.0
    assert "authoritative host" in why_ranked(p)


# --- formatting ---

def test_format_ranked_empty():
    assert "No pitfall" in format_ranked([])


def test_format_ranked_includes_title():
    p = _make("Connection pool exhausted")
    p.score = 7.0
    output = format_ranked([p])
    assert "Connection pool exhausted" in output


def test_format_ranked_shows_score():
    p = _make()
    result = rank([p])
    output = format_ranked(result)
    assert "score:" in output


# --- title tokens ---

def test_title_tokens_removes_stop_words():
    tokens = _title_tokens("the memory leak in pool")
    assert "the" not in tokens
    assert "memory" in tokens
    assert "pool" in tokens


def test_similar_identical_titles():
    a = _make("Memory leak in connection pool")
    b = _make("Memory leak in connection pool")
    assert _similar(a, b)


def test_not_similar_different_topics():
    a = _make("Memory leak in pool")
    b = _make("Authentication bypass vulnerability")
    assert not _similar(a, b)


def test_authority_cannot_be_borrowed_by_substring():
    """A lookalike host must not inherit an official host's authority bonus."""
    real = from_exa_result({"url": "https://github.com/a/b/issues/1", "title": "t", "text": ""})
    fake = from_exa_result({"url": "https://github.com.attacker.test/a", "title": "t", "text": ""})
    assert score(real) > score(fake)
    assert fake.score_breakdown["authority"] == 0.0


def test_subdomain_of_official_domain_still_counts():
    p = from_exa_result({"url": "https://old.reddit.com/r/x/comments/1",
                         "title": "t", "text": ""})
    assert p.source == "reddit"
    score(p)
    assert p.score_breakdown["authority"] == 1.0
