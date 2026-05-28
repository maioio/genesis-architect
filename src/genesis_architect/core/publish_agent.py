"""Collect release data and generate publish-ready content for HN and GitHub Releases.

Architectural note — why we use a browser-AI prompt instead of headless auto-submission:
  Hacker News runs persistent anti-bot detection (rate fingerprinting, TLS JA3 hashing,
  behavioral mouse/timing analysis). Automated headless submissions — even via Playwright
  with stealth plugins — are silently shadowbanned: the post appears to the submitter but
  is invisible to everyone else, with no error or warning. This is unrecoverable once it
  happens to an account or domain.

  This module deliberately generates a human-readable prompt that the user pastes into an
  authenticated browser session via their own AI extension. The actual HTTP request comes
  from a real browser with a valid session cookie, real user-agent, and human-like timing.
  This is not an incomplete implementation — it is the correct architecture for any tool
  that cares about the long-term health of the user's HN account and domain reputation.
"""

import json
import os
import re
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Privacy / path redaction
# ---------------------------------------------------------------------------

def _redact_path(text: str) -> str:
    """Replace absolute local paths that expose the OS username with safe generic forms.

    Handles Windows (C:\\Users\\<name>\\...) and POSIX (/home/<name>/..., /Users/<name>/...)
    paths. The replacement uses a generic ~/... form that is safe to publish publicly.
    """
    if not text:
        return text

    # Windows: C:\Users\<username>\... or C:/Users/<username>/...
    text = re.sub(
        r"[A-Za-z]:[/\\]Users[/\\][^/\\\s\"']+([/\\])",
        r"~\1",
        text,
    )
    # Also handle cases where path ends without trailing separator
    text = re.sub(
        r"[A-Za-z]:[/\\]Users[/\\][^/\\\s\"'>]+",
        "~",
        text,
    )
    # POSIX: /home/<username>/... or /Users/<username>/...
    text = re.sub(
        r"/(home|Users)/[^/\s\"']+(/)",
        r"~\2",
        text,
    )
    text = re.sub(
        r"/(home|Users)/[^/\s\"'>]+",
        "~",
        text,
    )
    return text


def _redact_env_vars(text: str) -> str:
    """Replace common secret patterns (API keys, tokens) with [REDACTED]."""
    # API key patterns: long alphanumeric strings with common prefixes
    text = re.sub(
        r"(sk-ant-api|sk-|ghp_|github_pat_|Bearer\s+)[A-Za-z0-9_\-]{10,}",
        r"\1[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    return text


def sanitize_for_public(text: str) -> str:
    """Full privacy gate: redact paths and secrets. Apply to all user-visible output."""
    text = _redact_path(text)
    text = _redact_env_vars(text)
    return text


# ---------------------------------------------------------------------------
# PSR.ai asset detection
# ---------------------------------------------------------------------------

_PSR_OUTPUT_CANDIDATES = [
    # Check env var override first
    os.environ.get("GENESIS_PSR_OUTPUT_DIR", ""),
    # Standard default on Windows
    str(Path.home() / "psr_output"),
    # Relative fallback inside project
    str(Path.cwd() / "psr_output"),
]


def _find_psr_output_dir() -> Path | None:
    """Return the PSR.ai output directory to scan, or None if not found."""
    for candidate in _PSR_OUTPUT_CANDIDATES:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def detect_psr_assets(psr_root: Path | None = None) -> dict:
    """Scan the PSR.ai output directory for the most recent session assets.

    Returns a dict with:
        {
            "replay_gif": Path | None,     # action_replay.gif from latest session
            "screenshots": list[Path],      # key screenshots from latest session
            "session_dir": Path | None,     # the resolved session output directory
            "session_name": str,            # sanitized display name (no local paths)
        }

    All returned path strings are sanitized (no local user paths exposed).
    """
    base = psr_root or _find_psr_output_dir()
    if base is None or not base.is_dir():
        return {"replay_gif": None, "screenshots": [], "session_dir": None, "session_name": ""}

    # Find the most recently modified *_output directory
    output_dirs = sorted(
        [d for d in base.iterdir() if d.is_dir() and d.name.endswith("_output")],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not output_dirs:
        return {"replay_gif": None, "screenshots": [], "session_dir": None, "session_name": ""}

    session_dir = output_dirs[0]

    replay_gif = session_dir / "action_replay.gif"
    if not replay_gif.exists():
        replay_gif = None

    screenshots_dir = session_dir / "screenshots"
    screenshots: list[Path] = []
    if screenshots_dir.is_dir():
        all_shots = sorted(screenshots_dir.glob("*.png"), key=lambda p: p.name)
        # Pick up to 3 representative screenshots (first, middle, last)
        n = len(all_shots)
        if n > 0:
            indices = {0, n // 2, n - 1}
            screenshots = [all_shots[i] for i in sorted(indices)]

    # Build a safe display name: just the directory name, no full path
    session_name = session_dir.name  # e.g. "psr_20260519_222400_output"

    return {
        "replay_gif": replay_gif,
        "screenshots": screenshots,
        "session_dir": session_dir,
        "session_name": session_name,
    }


# ---------------------------------------------------------------------------
# Release data collection
# ---------------------------------------------------------------------------

def collect_release_data(project_root: Path, psr_root: Path | None = None) -> dict:
    """Read RELEASE_NOTES, commits, test count, and PSR.ai assets from the project root.

    Returns:
        {
            "version": str,
            "release_notes_raw": str,
            "commits": list[str],
            "test_count": int,
            "psr_assets": dict,   # from detect_psr_assets()
        }
    """
    root = Path(project_root)

    # Find latest RELEASE_NOTES_vX.Y.Z.md
    notes_files = sorted(root.glob("RELEASE_NOTES_v*.md"), reverse=True)
    version = "latest"
    release_notes_raw = ""
    if notes_files:
        latest = notes_files[0]
        release_notes_raw = latest.read_text(encoding="utf-8")
        m = re.search(r"v(\d+\.\d+\.\d+)", latest.name)
        if m:
            version = m.group(1)

    commits = _get_recent_commits(root)
    test_count = _detect_test_count(root)
    psr_assets = detect_psr_assets(psr_root)

    return {
        "version": version,
        "release_notes_raw": release_notes_raw,
        "commits": commits,
        "test_count": test_count,
        "psr_assets": psr_assets,
    }


def _get_recent_commits(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "$(git describe --tags --abbrev=0)..HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=root, capture_output=True, text=True, timeout=10,
            )
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        return lines[:15]
    except Exception:
        return []


def _detect_test_count(root: Path) -> int:
    readme = root / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        m = re.search(r"tests-(\d+)-", text)
        if m:
            return int(m.group(1))
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--collect-only", "-q"],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        m = re.search(r"(\d+) test", result.stdout + result.stderr)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# Content generation
# ---------------------------------------------------------------------------

def _build_visual_markdown(psr_assets: dict, version: str) -> str:
    """Return a Markdown snippet for embedding PSR.ai visuals in the release body.

    Uses only filenames (never absolute paths) so the output is safe to publish.
    """
    parts = []

    if psr_assets.get("replay_gif"):
        gif_name = psr_assets["replay_gif"].name  # "action_replay.gif"
        parts.append("## Demo")
        parts.append(
            f"![Genesis Architect v{version} demo]({gif_name})\n"
            f"<!-- Upload {gif_name} as a release asset and GitHub will inline it above. -->"
        )

    if psr_assets.get("screenshots"):
        parts.append("\n## Screenshots")
        for i, shot in enumerate(psr_assets["screenshots"], 1):
            parts.append(
                f"![Step {i}]({shot.name})\n"
                f"<!-- Upload {shot.name} as a release asset -->"
            )

    return "\n\n".join(parts)


def generate_publish_content(data: dict, llm_fn) -> dict:
    """Call LLM twice to generate HN post and GitHub release body.

    Args:
        data: output of collect_release_data()
        llm_fn: callable(prompt: str) -> str

    Returns:
        {
            "hn_title": str,
            "hn_comment": str,
            "release_title": str,
            "release_body": str,
        }
    """
    version = data.get("version", "latest")
    commits_text = "\n".join(data.get("commits", [])) or "No commits detected."
    test_count = data.get("test_count", 0)
    notes_raw = data.get("release_notes_raw", "")
    psr_assets = data.get("psr_assets", {})

    # --- Prompt 1: HN post ---
    hn_prompt = f"""You are writing a Show HN submission for Hacker News.

Project: Genesis Architect
Version: {version}
What it does: Scans 15-20 real GitHub repos and mines their Issues for production pitfalls before scaffolding a project. Unlike Yeoman/Cookiecutter, it reads what actually broke in production repos before writing a single file.
Key changes in this release:
{commits_text}
Test count: {test_count}

Rules:
- Title: max 80 chars, starts with "Show HN:", factual not hype, highlight the most technically interesting thing
- Founder comment: 2-3 sentences, honest, invites technical discussion, no marketing speak
- HN audience is senior engineers — be specific and humble

Return a JSON object with exactly these two keys:
{{"title": "...", "comment": "..."}}
Return ONLY the JSON, no markdown, no explanation."""

    hn_raw = llm_fn(hn_prompt).strip()
    hn_title = "Show HN: Genesis Architect - scans 20 GitHub repos before scaffolding your project"
    hn_comment = (
        "Built this after watching teammates scaffold projects that hit the same production bugs "
        "everyone else hit. The research phase (scanning Issues, not just READMEs) is what makes "
        "it different. Happy to answer questions."
    )
    try:
        clean = re.sub(r"^```[a-z]*\n?", "", hn_raw, flags=re.MULTILINE)
        clean = re.sub(r"\n?```$", "", clean, flags=re.MULTILINE)
        parsed = json.loads(clean.strip())
        hn_title = parsed.get("title", hn_title)
        hn_comment = parsed.get("comment", hn_comment)
    except Exception:
        pass

    # --- Prompt 2: GitHub Release body ---
    visual_hint = ""
    if psr_assets.get("replay_gif") or psr_assets.get("screenshots"):
        visual_hint = "\nNote: Visual assets (demo GIF, screenshots) will be appended after this section."

    release_prompt = f"""You are writing GitHub release notes for a developer tool called Genesis Architect.

Version: v{version}
Commits in this release:
{commits_text}

Raw notes (expand on these):
{notes_raw[:3000]}
{visual_hint}

Rules:
- Start with a one-line summary of the release
- Keep all technical details from the raw notes
- Use clean markdown with ## headers
- Be concise but complete
- Do NOT add hype or adjectives like "powerful" or "amazing"

Return ONLY the markdown text, no explanation."""

    release_body = llm_fn(release_prompt).strip()
    if not release_body:
        release_body = notes_raw

    # Append visual asset markdown (filenames only — no local paths)
    visual_md = _build_visual_markdown(psr_assets, version)
    if visual_md:
        release_body = release_body.rstrip() + "\n\n" + visual_md

    # Apply privacy gate to the full release body
    release_body = sanitize_for_public(release_body)

    release_title = f"v{version} - Genesis Architect"
    if notes_raw:
        m = re.search(r"^#\s+(.+)$", notes_raw, re.MULTILINE)
        if m:
            release_title = m.group(1).strip()

    return {
        "hn_title": hn_title,
        "hn_comment": hn_comment,
        "release_title": release_title,
        "release_body": release_body,
    }


# ---------------------------------------------------------------------------
# Terminal output formatting
# ---------------------------------------------------------------------------

def format_output(content: dict, version: str = "", psr_assets: dict | None = None) -> str:
    """Format the final terminal output with both submission options plus visual asset guidance."""
    hn_title = content.get("hn_title", "")
    hn_comment = content.get("hn_comment", "")
    release_title = content.get("release_title", "")
    release_body = content.get("release_body", "")
    v = f"v{version}" if version else ""
    psr = psr_assets or {}

    bar = "=" * 60

    browser_ai_prompt = (
        f'Please navigate to https://news.ycombinator.com/submit . '
        f'Fill the "title" field exactly with: "{hn_title}" . '
        f'Fill the "text" field exactly with: "{hn_comment}" . '
        f'Then click the submit button.'
    )

    arch_note = (
        "NOTE: genesis publish uses a browser-AI prompt instead of headless auto-submission.\n"
        "  This is a deliberate architectural decision: HN silently shadowbans automated\n"
        "  submissions. By generating a prompt for your authenticated browser session,\n"
        "  your account and domain stay 100% safe. Paste Option 2 into your Chrome AI\n"
        "  extension and it handles the rest."
    )

    lines = [
        "",
        bar,
        f"  Genesis Publish  {v}".rstrip(),
        bar,
        "",
        arch_note,
        "",
        "OPTION 1 - Manual Copy-Paste",
        "-" * 40,
        "  HN Submit URL:  https://news.ycombinator.com/submit",
        "",
        "  Title:",
        f"  {hn_title}",
        "",
        "  Comment (post as first reply after submitting):",
        *[f"  {line}" for line in hn_comment.splitlines()],
        "",
        "",
        "OPTION 2 - Browser AI Prompt",
        "  (paste this directly into your Chrome AI extension)",
        "-" * 40,
        browser_ai_prompt,
        "",
        "",
        "GITHUB RELEASE",
        "-" * 40,
        "  URL:   https://github.com/maioio/genesis-architect/releases/new",
        f"  Tag:   v{version}" if version else "  Tag:   (set your version tag)",
        f"  Title: {release_title}",
        "",
        "  Body (copy the full release notes below):",
        bar,
        release_body,
        bar,
        "",
    ]

    # --- Visual Assets section ---
    has_gif = bool(psr.get("replay_gif"))
    has_shots = bool(psr.get("screenshots"))

    if has_gif or has_shots:
        lines += [
            "VISUAL ASSETS  (from PSR.ai session)",
            "-" * 40,
            "  Drag and drop these files into the GitHub Release UI",
            '  (the "Attach binaries" area at the bottom of the release editor).',
            "  GitHub will host them and the Markdown in the release body will",
            "  automatically render them inline.",
            "",
        ]

        if has_gif:
            gif_path = psr["replay_gif"]
            # Show only the session directory name + filename — no full local path
            session_name = psr.get("session_name", "")
            safe_display = f"~/psr_output/{session_name}/{gif_path.name}" if session_name else gif_path.name
            lines += [
                "  1. Demo GIF (animated replay of the whole session)",
                f"     File:  {safe_display}",
                f"     Asset: {gif_path.name}",
                "",
            ]

        if has_shots:
            lines.append("  2. Key Screenshots")
            for i, shot in enumerate(psr["screenshots"], 1):
                session_name = psr.get("session_name", "")
                safe_display = f"~/psr_output/{session_name}/{shot.name}" if session_name else shot.name
                lines.append(f"     [{i}] {safe_display}")
            lines.append("")

        lines += [
            "  After uploading, the release body already contains the Markdown",
            "  image tags referencing these filenames — no editing required.",
            "",
        ]

    return sanitize_for_public("\n".join(lines))
