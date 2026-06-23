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
        "genesis_key": bool(_load_env_key("GENESIS_WHISPER_KEY")),
        "groq_key": bool(_load_env_key("GROQ_API_KEY")),
        "openai_key": bool(_load_env_key("OPENAI_API_KEY")),
    }


def is_watch_skill_available() -> bool:
    p = check_watch_prerequisites()
    has_key = p["genesis_key"] or p["groq_key"] or p["openai_key"]
    return p["yt_dlp"] and p["ffmpeg"] and has_key


def resolve_transcription_key() -> tuple[str, str]:
    """Pick the Whisper key to use, honoring the hybrid precedence.

    Order:
      1. GENESIS_WHISPER_KEY - managed quota via Genesis (free tier, then billed).
      2. GROQ_API_KEY        - user's own Groq key (BYOK, recommended free path).
      3. OPENAI_API_KEY      - user's own OpenAI key (BYOK).

    Returns (provider, key). provider is one of: genesis | groq | openai | none.
    The caller never sees a raw managed key in logs - only the provider name
    should be surfaced to the user.
    """
    genesis = _load_env_key("GENESIS_WHISPER_KEY")
    if genesis:
        return ("genesis", genesis)
    groq = _load_env_key("GROQ_API_KEY")
    if groq:
        return ("groq", groq)
    openai = _load_env_key("OPENAI_API_KEY")
    if openai:
        return ("openai", openai)
    return ("none", "")


def ensure_watch_ready(auto_install: bool = True) -> dict:
    """Make video transcription work with zero user steps where possible.

    Tools (yt-dlp, ffmpeg) are installed automatically by delegating to the
    /watch skill's own setup.py (which knows winget/brew/pip per platform).
    The user never has to know about this.

    The transcription KEY is the one thing that cannot be auto-provisioned on
    the client: a managed key (GENESIS_WHISPER_KEY) requires a Genesis proxy,
    and a BYOK key must be created by the user. So this returns a clear status
    instead of pretending. See resolve_transcription_key().

    Returns:
      {"tools_ready": bool, "key_provider": str, "ready": bool,
       "installed": [..], "action_needed": str}
    """
    import subprocess
    import sys
    from pathlib import Path

    result = {
        "tools_ready": False,
        "key_provider": "none",
        "ready": False,
        "installed": [],
        "action_needed": "",
    }

    pre = check_watch_prerequisites()
    tools_ok = pre["yt_dlp"] and pre["ffmpeg"]

    # Auto-install missing tools via the watch skill's setup.py (silent).
    if not tools_ok and auto_install:
        setup = Path.home() / ".claude" / "skills" / "watch" / "scripts" / "setup.py"
        if setup.exists():
            try:
                proc = subprocess.run(
                    [sys.executable, str(setup)],
                    capture_output=True, text=True, timeout=300,
                    encoding="utf-8", errors="replace",
                )
                if proc.returncode == 0:
                    result["installed"] = [
                        t for t in ("yt-dlp", "ffmpeg")
                        if not pre[t.replace("-", "_")]
                    ]
                pre = check_watch_prerequisites()  # re-check after install
                tools_ok = pre["yt_dlp"] and pre["ffmpeg"]
            except (subprocess.TimeoutExpired, OSError):
                pass  # fall through to guidance below

    result["tools_ready"] = tools_ok
    provider, _ = resolve_transcription_key()
    result["key_provider"] = provider
    result["ready"] = tools_ok and provider != "none"

    if not result["ready"]:
        result["action_needed"] = watch_setup_guidance()
    return result


def watch_setup_guidance() -> str:
    """Human-readable setup steps for whatever is missing. Empty if all ready.

    Genesis calls this before deep video analysis. If a dependency is missing,
    it shows these steps instead of failing silently or pretending it ran.
    """
    import sys

    p = check_watch_prerequisites()
    if p["yt_dlp"] and p["ffmpeg"] and (p["genesis_key"] or p["groq_key"] or p["openai_key"]):
        return ""

    is_win = sys.platform.startswith("win")
    is_mac = sys.platform == "darwin"
    steps: list[str] = ["Video transcription needs a few one-time setup steps:\n"]

    if not p["yt_dlp"]:
        if is_win:
            steps.append("- yt-dlp:  winget install yt-dlp  (or: pip install -U yt-dlp)")
        elif is_mac:
            steps.append("- yt-dlp:  brew install yt-dlp")
        else:
            steps.append("- yt-dlp:  pip install -U yt-dlp")

    if not p["ffmpeg"]:
        if is_win:
            steps.append("- ffmpeg:  winget install Gyan.FFmpeg")
        elif is_mac:
            steps.append("- ffmpeg:  brew install ffmpeg")
        else:
            steps.append("- ffmpeg:  sudo apt install ffmpeg  (Debian/Ubuntu)")

    if not (p["genesis_key"] or p["groq_key"] or p["openai_key"]):
        steps.append(
            "- Transcription key (pick one):\n"
            "    Free tier (managed):  set GENESIS_WHISPER_KEY=<your-genesis-key>\n"
            "    Bring your own (free): get a key at https://console.groq.com\n"
            "                           then set GROQ_API_KEY=<key>\n"
            "    Or OpenAI:             set OPENAI_API_KEY=<key>\n"
            "  Keys can also go in ~/.config/watch/.env"
        )

    steps.append(
        "\nWithout these, Genesis will use caption-only transcription where "
        "available, and tell you when a video has no captions - it will not "
        "fabricate a transcript."
    )
    return "\n".join(steps)


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
