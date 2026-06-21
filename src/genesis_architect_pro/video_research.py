"""
Multi-platform media research for Genesis Architect.

Phase 2 Stream D: finds video and social content via Exa (metadata only).
Companion Mode: deep video analysis via /watch skill.

Platforms covered:
  YouTube   - architecture talks, lessons learned, postmortems
  Reddit    - community experience, war stories (via Apify or Exa)
  Instagram - dev community demos, short-form architecture breakdowns

Design principles:
- Phase 2 baseline: metadata only - zero transcription cost
- Deep analysis: opt-in via `genesis research --video <url>`
- Ask clarifying questions before deep-diving any specific source
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MediaSignal:
    title: str
    url: str
    platform: str        # youtube | reddit | instagram | unknown
    channel: str
    description: str
    signal_type: str     # lessons_learned | architecture_talk | tutorial | community | unknown
    relevance: str       # high | medium | low
    watch_command: str   # /watch command (YouTube only; empty for others)
    extra: dict = field(default_factory=dict)

    # backward compat alias used by pitfall_ranker
    @property
    def signal_type_compat(self) -> str:
        return self.signal_type


# keep old name as alias so existing code doesn't break
VideoSignal = MediaSignal


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _detect_platform(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "reddit.com" in url or "redd.it" in url:
        return "reddit"
    if "instagram.com" in url:
        return "instagram"
    return "unknown"


# ---------------------------------------------------------------------------
# Signal classification
# ---------------------------------------------------------------------------

_LESSON_KEYWORDS = {
    "lessons learned", "mistakes", "pitfall", "regret", "what i wish",
    "don't do", "avoid", "failure", "postmortem", "we broke", "went wrong",
    "should have", "warning", "gotcha",
}
_ARCH_KEYWORDS = {
    "architecture", "system design", "microservice", "monolith", "event-driven",
    "cqrs", "hexagonal", "clean arch", "domain driven", "ddd", "solid",
    "design pattern", "refactor",
}
_TUTORIAL_KEYWORDS = {
    "tutorial", "how to", "getting started", "build with", "step by step",
    "guide", "walkthrough", "crash course",
}
_COMMUNITY_KEYWORDS = {
    "discussion", "thread", "ask", "advice", "experience", "ama",
    "what do you use", "best library", "recommend",
}


def _classify(title: str, description: str) -> str:
    t = (title + " " + description).lower()
    if any(k in t for k in _LESSON_KEYWORDS):
        return "lessons_learned"
    if any(k in t for k in _ARCH_KEYWORDS):
        return "architecture_talk"
    if any(k in t for k in _COMMUNITY_KEYWORDS):
        return "community"
    if any(k in t for k in _TUTORIAL_KEYWORDS):
        return "tutorial"
    return "unknown"


def _relevance(signal_type: str) -> str:
    return {
        "lessons_learned": "high",
        "architecture_talk": "high",
        "community": "medium",
        "tutorial": "medium",
        "unknown": "low",
    }.get(signal_type, "low")


# ---------------------------------------------------------------------------
# Query builders - one per platform
# ---------------------------------------------------------------------------

def build_youtube_queries(vision: str) -> list[str]:
    """Exa queries targeting YouTube. Run in parallel during Phase 2 Stream D."""
    return [
        f'"{vision}" lessons learned mistakes site:youtube.com',
        f'"{vision}" architecture talk conference site:youtube.com',
        f'"{vision}" production failure postmortem site:youtube.com',
    ]


def build_reddit_queries(vision: str) -> list[str]:
    """Exa queries targeting Reddit dev communities."""
    return [
        f'"{vision}" pitfalls lessons learned site:reddit.com',
        f'"{vision}" architecture advice site:reddit.com/r/programming OR site:reddit.com/r/devops OR site:reddit.com/r/softwarearchitecture',
        f'"{vision}" what I wish I knew site:reddit.com',
    ]


def build_instagram_queries(vision: str) -> list[str]:
    """Exa queries targeting Instagram dev content (limited, use sparingly)."""
    return [
        f'"{vision}" developer tip architecture site:instagram.com',
    ]


def build_all_media_queries(vision: str) -> dict[str, list[str]]:
    """
    Return all queries grouped by platform.
    Stream D runs these in parallel with GitHub/Exa streams.
    """
    return {
        "youtube": build_youtube_queries(vision),
        "reddit": build_reddit_queries(vision),
        "instagram": build_instagram_queries(vision),
    }


# ---------------------------------------------------------------------------
# Result parsers
# ---------------------------------------------------------------------------

def _make_watch_command(url: str, question: str) -> str:
    safe_q = question.replace('"', "'")
    return f'/watch {url} "{safe_q}"'


def _make_question(vision: str) -> str:
    return (
        f"What are the main pitfalls, architecture decisions, and lessons "
        f"learned about building {vision}?"
    )


def parse_exa_results(exa_results: list[dict], vision: str,
                      platforms: tuple[str, ...] = ("youtube", "reddit", "instagram")
                      ) -> list[MediaSignal]:
    """
    Convert raw Exa results from any platform into MediaSignal objects.
    Filters to requested platforms only.
    """
    signals = []
    for r in exa_results:
        url = r.get("url", "")
        platform = _detect_platform(url)
        if platform not in platforms:
            continue

        title = r.get("title", "")
        description = r.get("text", r.get("snippet", ""))[:300]
        channel = r.get("author", r.get("domain", "unknown"))
        signal_type = _classify(title, description)
        relevance = _relevance(signal_type)

        watch_cmd = ""
        if platform == "youtube":
            watch_cmd = _make_watch_command(url, _make_question(vision))

        signals.append(MediaSignal(
            title=title,
            url=url,
            platform=platform,
            channel=channel,
            description=description,
            signal_type=signal_type,
            relevance=relevance,
            watch_command=watch_cmd,
        ))

    signals.sort(key=lambda s: ({"high": 0, "medium": 1, "low": 2}[s.relevance], s.platform))
    return signals[:8]   # cap: 5 video + 3 social max


# backward compat
def parse_exa_video_results(exa_results: list[dict], vision: str) -> list[MediaSignal]:
    return parse_exa_results(exa_results, vision, platforms=("youtube",))


# ---------------------------------------------------------------------------
# Clarifying questions (asked before deep-diving a specific source)
# ---------------------------------------------------------------------------

def clarifying_questions_for_deep_research(signal: MediaSignal, vision: str) -> list[str]:
    """
    Return questions Genesis should ask before running /watch or deep-scraping
    a specific media result. Implements the 'ask questions along the way' rule.
    """
    base = [
        f"This {signal.platform} content seems relevant to {vision}. Should I analyze it in depth?",
    ]
    if signal.platform == "youtube":
        base += [
            "A: Yes - run /watch and extract pitfalls + architecture decisions",
            "B: Add to research list only (show the /watch command, don't run yet)",
            "C: Skip this video",
        ]
    elif signal.platform == "reddit":
        base += [
            "A: Yes - read the thread and extract community insights",
            "B: Note the URL for later",
            "C: Skip",
        ]
    else:
        base += ["A: Include in research  B: Skip"]
    return base


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_PLATFORM_ICONS = {
    "youtube": "🎬",
    "reddit": "📋",
    "instagram": "📸",
    "unknown": "🔗",
}

_TYPE_ICONS = {
    "lessons_learned": "🎯",
    "architecture_talk": "🏗",
    "community": "💬",
    "tutorial": "📺",
    "unknown": "📎",
}


def format_media_signals(signals: list[MediaSignal], group_by_platform: bool = True) -> str:
    """Format all media signals for Phase 5 research summary."""
    if not signals:
        return ""

    lines = ["### Media Research (Stream D)\n"]

    if group_by_platform:
        by_platform: dict[str, list[MediaSignal]] = {}
        for s in signals:
            by_platform.setdefault(s.platform, []).append(s)

        for platform, items in by_platform.items():
            p_icon = _PLATFORM_ICONS.get(platform, "🔗")
            lines.append(f"**{p_icon} {platform.capitalize()}**")
            for s in items:
                t_icon = _TYPE_ICONS.get(s.signal_type, "📎")
                lines.append(f"  {t_icon} **{s.title}**")
                lines.append(f"     Channel/Author: {s.channel} | Type: {s.signal_type.replace('_', ' ')}")
                if s.description:
                    lines.append(f"     _{s.description[:100]}..._")
                if s.watch_command:
                    lines.append(f"     Deep analysis: `{s.watch_command}`")
                else:
                    lines.append(f"     URL: {s.url}")
                lines.append("")
    else:
        for s in signals:
            icon = _TYPE_ICONS.get(s.signal_type, "📎")
            lines.append(f"{icon} **{s.title}** ({s.platform})")
            if s.watch_command:
                lines.append(f"   `{s.watch_command}`")
            lines.append("")

    return "\n".join(lines)


# alias for backward compat
def format_video_signals(signals: list[MediaSignal]) -> str:
    return format_media_signals(signals)


# ---------------------------------------------------------------------------
# Companion Mode: deep analysis
# ---------------------------------------------------------------------------

def build_deep_research_command(url: str, topic: str) -> str:
    """
    Build the /watch command for `genesis research --video <url>`.
    Only YouTube URLs supported for full transcription.
    """
    question = (
        f"Analyze this video for: (1) architecture decisions and their rationale, "
        f"(2) pitfalls and mistakes mentioned, (3) lessons learned about {topic}. "
        f"Extract specific, actionable insights relevant to building {topic}."
    )
    return _make_watch_command(url, question)


def check_watch_prerequisites() -> dict:
    """Return status of /watch skill dependencies."""
    return {
        "yt_dlp": shutil.which("yt-dlp") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "groq_key": bool(_load_env_key("GROQ_API_KEY")),
        "openai_key": bool(_load_env_key("OPENAI_API_KEY")),
    }


def is_watch_skill_available() -> bool:
    p = check_watch_prerequisites()
    return p["yt_dlp"] and p["ffmpeg"] and (p["groq_key"] or p["openai_key"])


def _load_env_key(key: str) -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    env_path = os.path.expanduser("~/.config/watch/.env")
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return ""
