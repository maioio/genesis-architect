"""Collect release data and generate publish-ready content for HN and GitHub Releases."""

import json
import re
import subprocess
from pathlib import Path


def collect_release_data(project_root: Path) -> dict:
    """Read RELEASE_NOTES, commits, and test count from the project root.

    Returns:
        {
            "version": str,
            "release_notes_raw": str,
            "commits": list[str],
            "test_count": int,
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

    # Commits since last tag (or last 10 if no tags)
    commits = _get_recent_commits(root)

    # Test count from README badge or pytest
    test_count = _detect_test_count(root)

    return {
        "version": version,
        "release_notes_raw": release_notes_raw,
        "commits": commits,
        "test_count": test_count,
    }


def _get_recent_commits(root: Path) -> list[str]:
    try:
        # Commits since last tag
        result = subprocess.run(
            ["git", "log", "--oneline", "$(git describe --tags --abbrev=0)..HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            # Fallback: last 10 commits
            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=root, capture_output=True, text=True, timeout=10,
            )
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        return lines[:15]
    except Exception:
        return []


def _detect_test_count(root: Path) -> int:
    # Try README badge pattern: tests-316-brightgreen
    readme = root / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        m = re.search(r"tests-(\d+)-", text)
        if m:
            return int(m.group(1))
    # Try running pytest --collect-only
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
    # Parse JSON — fall back to defaults if LLM returns malformed output
    try:
        # Strip markdown code fences if present
        clean = re.sub(r"^```[a-z]*\n?", "", hn_raw, flags=re.MULTILINE)
        clean = re.sub(r"\n?```$", "", clean, flags=re.MULTILINE)
        parsed = json.loads(clean.strip())
        hn_title = parsed.get("title", hn_title)
        hn_comment = parsed.get("comment", hn_comment)
    except Exception:
        pass

    # --- Prompt 2: GitHub Release body ---
    release_prompt = f"""You are writing GitHub release notes for a developer tool called Genesis Architect.

Version: v{version}
Commits in this release:
{commits_text}

Raw notes (expand on these):
{notes_raw[:3000]}

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

    release_title = f"v{version} - Genesis Architect"
    if notes_raw:
        # Try to extract title from first heading in raw notes
        m = re.search(r"^#\s+(.+)$", notes_raw, re.MULTILINE)
        if m:
            release_title = m.group(1).strip()

    return {
        "hn_title": hn_title,
        "hn_comment": hn_comment,
        "release_title": release_title,
        "release_body": release_body,
    }


def format_output(content: dict, version: str = "") -> str:
    """Format the final terminal output with both submission options."""
    hn_title = content.get("hn_title", "")
    hn_comment = content.get("hn_comment", "")
    release_title = content.get("release_title", "")
    release_body = content.get("release_body", "")
    v = f"v{version}" if version else ""

    bar = "=" * 60

    browser_ai_prompt = (
        f'Please navigate to https://news.ycombinator.com/submit . '
        f'Fill the "title" field exactly with: "{hn_title}" . '
        f'Fill the "text" field exactly with: "{hn_comment}" . '
        f'Then click the submit button.'
    )

    lines = [
        "",
        bar,
        f"  Genesis Publish  {v}".rstrip(),
        bar,
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

    return "\n".join(lines)
