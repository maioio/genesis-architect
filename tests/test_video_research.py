"""Tests for video_research module - no network calls, no external dependencies."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genesis_architect_pro.video_research import (
    build_youtube_queries,
    parse_exa_video_results,
    format_video_signals,
    build_deep_research_command,
    _classify,
    _relevance,
)

build_video_queries = build_youtube_queries
_classify_video = _classify


# --- Query builder ---

def test_build_video_queries_returns_three():
    queries = build_video_queries("FastAPI REST API")
    assert len(queries) == 3


def test_build_video_queries_contain_vision():
    queries = build_video_queries("async task queue")
    assert all("async task queue" in q for q in queries)


def test_build_video_queries_target_youtube():
    queries = build_video_queries("CLI tool")
    assert all("youtube.com" in q for q in queries)


def test_build_video_queries_cover_lessons_arch_failure():
    queries = build_video_queries("test")
    combined = " ".join(queries)
    assert "lessons learned" in combined or "mistakes" in combined
    assert "architecture" in combined
    assert "failure" in combined or "postmortem" in combined


# --- Signal classification ---

def test_classify_lessons_learned():
    assert _classify_video("Mistakes I made building microservices", "") == "lessons_learned"


def test_classify_architecture_talk():
    assert _classify_video("System Design: Event-driven architecture patterns", "") == "architecture_talk"


def test_classify_tutorial():
    assert _classify_video("Getting Started with FastAPI - Step by Step Tutorial", "") == "tutorial"


def test_classify_unknown():
    assert _classify_video("Weekly newsletter roundup", "") == "unknown"


def test_relevance_lessons_learned_is_high():
    assert _relevance("lessons_learned") == "high"


def test_relevance_architecture_talk_is_high():
    assert _relevance("architecture_talk") == "high"


def test_relevance_tutorial_is_medium():
    assert _relevance("tutorial") == "medium"


def test_relevance_unknown_is_low():
    assert _relevance("unknown") == "low"


# --- Exa result parsing ---

def _make_exa_results():
    return [
        {
            "url": "https://www.youtube.com/watch?v=abc123",
            "title": "Lessons learned building a task queue at scale",
            "text": "We spent two years building this system and made every mistake possible.",
            "author": "EngineeringChannel",
        },
        {
            "url": "https://www.youtube.com/watch?v=def456",
            "title": "Clean Architecture talk - PyCon 2024",
            "text": "Architecture patterns for maintainable Python services.",
            "author": "PyCon",
        },
        {
            "url": "https://news.ycombinator.com/item?id=999",  # not youtube
            "title": "HN: Ask HN about task queues",
            "text": "Discussion",
            "author": "HN",
        },
        {
            "url": "https://youtu.be/xyz789",
            "title": "Getting started with Celery tutorial",
            "text": "Step by step guide.",
            "author": "TutorialChannel",
        },
    ]


def test_parse_filters_non_youtube():
    results = parse_exa_video_results(_make_exa_results(), "task queue")
    urls = [s.url for s in results]
    assert "https://news.ycombinator.com/item?id=999" not in urls


def test_parse_returns_youtube_only():
    results = parse_exa_video_results(_make_exa_results(), "task queue")
    for s in results:
        assert "youtube.com" in s.url or "youtu.be" in s.url


def test_parse_sorted_high_first():
    results = parse_exa_video_results(_make_exa_results(), "task queue")
    relevances = [s.relevance for s in results]
    order = {"high": 0, "medium": 1, "low": 2}
    assert all(
        order[relevances[i]] <= order[relevances[i + 1]]
        for i in range(len(relevances) - 1)
    )


def test_parse_caps_at_eight():
    many = _make_exa_results() * 5  # 20 items
    results = parse_exa_video_results(many, "task queue")
    assert len(results) <= 8


def test_parse_includes_watch_command():
    results = parse_exa_video_results(_make_exa_results(), "task queue")
    for s in results:
        assert "/watch" in s.watch_command
        assert s.url in s.watch_command


def test_parse_watch_command_has_question():
    results = parse_exa_video_results(_make_exa_results(), "task queue")
    for s in results:
        assert "task queue" in s.watch_command


# --- Format output ---

def test_format_empty_returns_empty_string():
    assert format_video_signals([]) == ""


def test_format_includes_titles():
    results = parse_exa_video_results(_make_exa_results(), "task queue")
    output = format_video_signals(results)
    assert "Lessons learned" in output or "Clean Architecture" in output


def test_format_includes_watch_commands():
    results = parse_exa_video_results(_make_exa_results(), "task queue")
    output = format_video_signals(results)
    assert "/watch" in output


def test_format_includes_stream_d_header():
    results = parse_exa_video_results(_make_exa_results(), "task queue")
    output = format_video_signals(results)
    assert "Stream D" in output


# --- Deep research command ---

def test_deep_research_command_includes_url():
    cmd = build_deep_research_command("https://youtube.com/watch?v=abc", "FastAPI")
    assert "https://youtube.com/watch?v=abc" in cmd


def test_deep_research_command_includes_topic():
    cmd = build_deep_research_command("https://youtube.com/watch?v=abc", "FastAPI")
    assert "FastAPI" in cmd


def test_deep_research_command_starts_with_watch():
    cmd = build_deep_research_command("https://youtube.com/watch?v=abc", "FastAPI")
    assert cmd.startswith("/watch")


def test_deep_research_command_asks_for_pitfalls():
    cmd = build_deep_research_command("https://youtube.com/watch?v=abc", "task queue")
    assert "pitfall" in cmd.lower() or "lessons" in cmd.lower()

