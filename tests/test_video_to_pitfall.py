"""Tests for video_to_pitfall module - no network, no disk I/O (except tmp_path)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genesis_architect.pro.video_to_pitfall import (
    extract_from_watch_output,
    append_to_pitfalls_md,
    summarize_extraction,
    PitfallEntry,
    _slug,
    _classify_category,
    _extract_timestamp,
)


# --- sample watch output ---

WATCH_OUTPUT_GOOD = """
[00:03] In this talk I'll share the mistakes we made building our task queue system.

[02:15] The biggest pitfall was not using connection pooling from the start.
We learned the hard way that opening a new database connection per task caused
severe memory exhaustion under load. We regret not catching this earlier.

[05:30] Another gotcha: never use synchronous calls inside async workers.
This caused timeouts across the board and we had to refactor the entire pipeline.

[08:00] Security warning: we found that raw task payloads were logged, exposing
user tokens and API secrets. Always sanitize before logging.

[11:20] Lessons learned: start with proper monitoring from day one.
We broke production twice before adding proper health checks.
"""

WATCH_OUTPUT_TUTORIAL = """
In this tutorial I'll show you how to build a task queue with Celery.
Step 1: install redis. Step 2: configure your broker URL.
Let's get started building this amazing system together.
"""


# --- extraction ---

def test_extract_finds_pitfalls():
    entries = extract_from_watch_output(WATCH_OUTPUT_GOOD, "https://youtube.com/watch?v=abc", "task queue")
    assert len(entries) > 0


def test_extract_tutorial_may_yield_less():
    entries = extract_from_watch_output(WATCH_OUTPUT_TUTORIAL, "https://youtube.com/watch?v=xyz", "celery")
    # tutorials have fewer pitfall signals - could be 0
    assert isinstance(entries, list)


def test_extract_caps_at_seven():
    long_text = (WATCH_OUTPUT_GOOD + "\n") * 10
    entries = extract_from_watch_output(long_text, "https://youtube.com/watch?v=abc", "test")
    assert len(entries) <= 7


def test_extract_entries_have_required_fields():
    entries = extract_from_watch_output(WATCH_OUTPUT_GOOD, "https://youtube.com/watch?v=abc", "task queue")
    for e in entries:
        assert e.title
        assert e.source_url
        assert e.source_type == "video"
        assert e.category in ("pitfall", "architecture_regret", "security", "performance")
        assert e.confidence in ("high", "medium", "low")
        assert e.mitigation_file_path


def test_extract_deduplicates():
    duped = WATCH_OUTPUT_GOOD + "\n" + WATCH_OUTPUT_GOOD
    entries = extract_from_watch_output(duped, "https://youtube.com/watch?v=abc", "test")
    titles = [e.title for e in entries]
    assert len(titles) == len(set(t[:20] for t in titles))


def test_extract_security_category():
    text = "[03:00] Security warning: we found raw API tokens being logged. Always sanitize before logging."
    entries = extract_from_watch_output(text, "https://youtube.com/watch?v=sec", "api")
    security = [e for e in entries if e.category == "security"]
    assert len(security) > 0


def test_extract_timestamp_captured():
    text = "[05:30] We learned the hard way that this was a big mistake we regret."
    entries = extract_from_watch_output(text, "https://youtube.com/watch?v=ts", "test")
    if entries:
        assert "05:30" in entries[0].timestamp_cited or entries[0].timestamp_cited == ""


def test_extract_min_confidence_filter():
    entries_all = extract_from_watch_output(WATCH_OUTPUT_GOOD, "https://y.com/v", "test", min_confidence="low")
    entries_high = extract_from_watch_output(WATCH_OUTPUT_GOOD, "https://y.com/v", "test", min_confidence="high")
    assert len(entries_all) >= len(entries_high)


# --- PitfallEntry.to_markdown ---

def test_to_markdown_contains_title():
    e = PitfallEntry(
        title="Connection pool exhausted", source_url="https://y.com/v", source_type="video",
        category="performance", what="DB connections explode", why="no pooling",
        mitigation="Use pool_pre_ping=True", mitigation_file_path="src/db/pool.py",
        timestamp_cited="02:15", confidence="high", raw_excerpt="memory exhaustion under load",
    )
    md = e.to_markdown(3)
    assert "## Pitfall 3" in md
    assert "Connection pool exhausted" in md
    assert "02:15" in md
    assert "src/db/pool.py" in md


def test_to_markdown_has_implementation_block():
    e = PitfallEntry(
        title="Token leak", source_url="https://y.com/v", source_type="video",
        category="security", what="tokens logged", why="no sanitization",
        mitigation="Sanitize logs", mitigation_file_path="src/utils/security.py",
        timestamp_cited="", confidence="high", raw_excerpt="tokens in logs",
    )
    md = e.to_markdown(1)
    assert "Create:" in md
    assert "Test:" in md
    assert "Validate:" in md


# --- append_to_pitfalls_md ---

def test_append_creates_file_if_missing(tmp_path):
    entries = extract_from_watch_output(WATCH_OUTPUT_GOOD, "https://y.com/v", "test")
    path = tmp_path / "PITFALLS.md"
    count = append_to_pitfalls_md(entries, path)
    assert path.exists()
    assert count == len(entries)


def test_append_adds_to_existing(tmp_path):
    path = tmp_path / "PITFALLS.md"
    path.write_text("# PITFALLS.md\n\n## Pitfall 1: Existing issue\n\n", encoding="utf-8")
    entries = extract_from_watch_output(WATCH_OUTPUT_GOOD, "https://y.com/v", "test")
    append_to_pitfalls_md(entries, path)
    content = path.read_text(encoding="utf-8")
    assert "Existing issue" in content
    assert "Video Research Pitfalls" in content


def test_append_continues_numbering(tmp_path):
    path = tmp_path / "PITFALLS.md"
    path.write_text("# Pitfalls\n\n## Pitfall 5: Old issue\n\n", encoding="utf-8")
    entries = extract_from_watch_output(WATCH_OUTPUT_GOOD, "https://y.com/v", "test")[:1]
    append_to_pitfalls_md(entries, path)
    content = path.read_text(encoding="utf-8")
    assert "## Pitfall 6:" in content


def test_append_empty_entries_returns_zero(tmp_path):
    path = tmp_path / "PITFALLS.md"
    count = append_to_pitfalls_md([], path)
    assert count == 0
    assert not path.exists()


# --- summarize_extraction ---

def test_summarize_empty():
    msg = summarize_extraction([], "https://y.com/v")
    assert "No clear pitfalls" in msg


def test_summarize_with_entries():
    entries = extract_from_watch_output(WATCH_OUTPUT_GOOD, "https://y.com/v", "test")
    msg = summarize_extraction(entries, "https://y.com/v")
    assert str(len(entries)) in msg or "pitfall" in msg.lower()


# --- helpers ---

def test_slug_basic():
    assert _slug("Memory leak in pool") == "memory_leak_in_pool"


def test_slug_special_chars():
    s = _slug("don't use sync/async!")
    assert " " not in s
    assert "/" not in s


def test_classify_security():
    assert _classify_category("CVE injection bypass found in auth") == "security"


def test_classify_performance():
    assert _classify_category("memory leak causing OOM crash") == "performance"


def test_classify_arch_regret():
    assert _classify_category("we migrated from monolith to microservices") == "architecture_regret"


def test_classify_default_pitfall():
    assert _classify_category("something went wrong last week") == "pitfall"


# --- timestamp citation across the formats /watch really emits ---

def test_timestamp_from_bracketed_transcript_line():
    assert _extract_timestamp("[04:12] the mistake we made was caching too early") == "04:12"


def test_timestamp_from_frame_label():
    """watch.py labels frames `t=MM:SS` on the absolute timeline."""
    assert _extract_timestamp("frame_007.jpg t=11:40 shows the broken dashboard") == "11:40"


def test_timestamp_from_prose_citation():
    assert _extract_timestamp("At 00:19:02 the speaker warns about tenant leakage") == "00:19:02"


def test_aspect_ratio_is_not_mistaken_for_a_timestamp():
    """A bare colon-separated pair must not be read as a citation."""
    assert _extract_timestamp("we exported everything at 16:9 which was a mistake") == ""


def test_absorbed_entry_cites_its_timestamp():
    watch_text = (
        "[04:12] The biggest mistake we made was storing session tokens in "
        "localStorage, because any XSS immediately becomes full account takeover "
        "and we learned this the hard way in production."
    )
    entries = extract_from_watch_output(watch_text, "https://youtu.be/DEMO", "a SaaS backend")
    assert entries
    assert entries[0].timestamp_cited == "04:12"
    assert "unknown timestamp" not in entries[0].why


def test_title_drops_the_leading_timestamp():
    """The timestamp lives in `timestamp_cited`; leaving it in the title also
    defeated the sentence-start anchor and produced a raw 60-char slice."""
    watch_text = (
        "[04:12] Storing session tokens in localStorage was our biggest mistake, "
        "because any XSS immediately becomes full account takeover."
    )
    entries = extract_from_watch_output(watch_text, "https://youtu.be/DEMO", "a SaaS backend")
    assert entries
    assert not entries[0].title.startswith("[")
    assert entries[0].timestamp_cited == "04:12"
    assert entries[0].title.startswith("Storing session tokens")
