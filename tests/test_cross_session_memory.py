"""Tests for cross_session_memory module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genesis_architect_pro.cross_session_memory import (
    restore_session,
    save_phase2,
    save_phase4,
    save_phase6,
    save_video_pitfalls,
    list_analyzed_videos,
    no_session_message,
    SessionContext,
)


# --- restore: no state ---

def test_restore_no_state_returns_not_restored(tmp_path):
    ctx = restore_session(tmp_path)
    assert not ctx.restored


def test_restore_no_state_vision_empty(tmp_path):
    ctx = restore_session(tmp_path)
    assert ctx.vision == ""


def test_no_session_message_has_init_hint():
    msg = no_session_message()
    assert "genesis init" in msg


# --- save and restore ---

def test_save_phase2_and_restore(tmp_path):
    save_phase2(tmp_path, "FastAPI REST API", repo_count=15, deep_count=6, quality="FULL")
    ctx = restore_session(tmp_path)
    assert ctx.restored
    assert ctx.vision == "FastAPI REST API"
    assert ctx.repo_count == 15
    assert ctx.deep_count == 6
    assert ctx.research_quality == "FULL"
    assert ctx.last_phase == "phase2"


def test_save_phase4_updates_phase(tmp_path):
    save_phase2(tmp_path, "CLI tool", 10, 5, "PARTIAL")
    save_phase4(tmp_path, pitfall_count=4)
    ctx = restore_session(tmp_path)
    assert ctx.last_phase == "phase4"
    assert ctx.pitfall_count == 4


def test_save_phase6_updates_phase(tmp_path):
    save_phase2(tmp_path, "CLI tool", 10, 5, "PARTIAL")
    save_phase6(tmp_path)
    ctx = restore_session(tmp_path)
    assert ctx.last_phase == "phase6"


# --- announce ---

def test_announce_contains_repos(tmp_path):
    save_phase2(tmp_path, "FastAPI", 12, 7, "FULL")
    ctx = restore_session(tmp_path)
    msg = ctx.announce()
    assert "12" in msg
    assert "7" in msg


def test_announce_mentions_phase(tmp_path):
    save_phase2(tmp_path, "FastAPI", 12, 7, "FULL")
    ctx = restore_session(tmp_path)
    msg = ctx.announce()
    assert "phase2" in msg.lower() or "Phase" in msg


def test_announce_empty_when_not_restored():
    ctx = SessionContext(
        vision="", last_phase="", last_phase_ts=0,
        repo_count=0, deep_count=0, pitfall_count=0,
        research_quality="THIN", vault_hit=False, restored=False,
    )
    assert ctx.announce() == ""


def test_announce_phase6_says_scaffold_complete(tmp_path):
    save_phase2(tmp_path, "test", 10, 5, "FULL")
    save_phase6(tmp_path)
    ctx = restore_session(tmp_path)
    msg = ctx.announce()
    assert "Scaffold" in msg or "Companion" in msg or "complete" in msg.lower()


# --- age ---

def test_age_hours_recent(tmp_path):
    save_phase2(tmp_path, "test", 5, 3, "PARTIAL")
    ctx = restore_session(tmp_path)
    assert ctx.age_hours() < 1


# --- video tracking ---

def test_save_video_pitfalls(tmp_path):
    save_phase2(tmp_path, "test", 5, 3, "PARTIAL")
    save_video_pitfalls(tmp_path, "https://youtube.com/watch?v=abc", 3)
    videos = list_analyzed_videos(tmp_path)
    assert "https://youtube.com/watch?v=abc" in videos


def test_save_video_no_duplicate(tmp_path):
    save_phase2(tmp_path, "test", 5, 3, "PARTIAL")
    save_video_pitfalls(tmp_path, "https://youtube.com/watch?v=abc", 2)
    save_video_pitfalls(tmp_path, "https://youtube.com/watch?v=abc", 1)
    videos = list_analyzed_videos(tmp_path)
    assert videos.count("https://youtube.com/watch?v=abc") == 1


def test_list_videos_empty(tmp_path):
    assert list_analyzed_videos(tmp_path) == []


def test_video_pitfalls_add_to_count(tmp_path):
    save_phase2(tmp_path, "test", 5, 3, "PARTIAL")
    save_phase4(tmp_path, pitfall_count=3)
    save_video_pitfalls(tmp_path, "https://y.com/v", 2)
    ctx = restore_session(tmp_path)
    assert ctx.pitfall_count == 5
