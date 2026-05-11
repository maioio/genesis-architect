#!/usr/bin/env python3
"""
research_validator.py - Genesis Architect
Validates that a generated RESEARCH.md is complete and well-formed.
Exits with code 0 if valid, code 1 if issues found.
Requires: Python 3.9+ (uses list[str] type hints)

Usage:
  python scripts/research_validator.py RESEARCH.md
  python scripts/research_validator.py path/to/project/RESEARCH.md
  python scripts/research_validator.py RESEARCH.md --verify-issues   # HTTP-check GitHub issue URLs
  python scripts/research_validator.py RESEARCH.md --verify-repos    # HTTP-check repos + star counts
  python scripts/research_validator.py RESEARCH.md --verify-issues --verify-repos

Environment:
  GITHUB_TOKEN  Optional. If set, used as Bearer token to avoid rate limits (60 req/hr unauthenticated).
"""

import sys
import re
import os
import json
import urllib.request
import urllib.error
from pathlib import Path


def _safe_path(requested: str) -> Path:
    """
    Resolve `requested` and ensure it stays under either the current working
    directory or this script's repo root. Either is fine - this validator is
    designed to be invoked against a user's project (cwd) or against the
    bundled examples/templates (repo root). Anything else is rejected to
    block traversal tricks like passing '/etc/passwd'.
    """
    cwd = Path.cwd().resolve()
    repo_root = Path(__file__).parent.parent.resolve()
    target = Path(requested).resolve()
    if target.is_relative_to(cwd) or target.is_relative_to(repo_root):
        return target
    raise PermissionError(
        f"Security: path '{target}' is outside cwd ('{cwd}') and repo root ('{repo_root}')"
    )

REQUIRED_SECTIONS = [
    "Executive Summary",
    "Search Scope",
    "Analyzed Repositories",
    "Market Landscape",
    "Architecture Decision Rationale",
    "Sources",
]

MIN_REPOS = 5
MIN_SOURCES = 3

GITHUB_ISSUE_RE = re.compile(
    r"https://github\.com/[^/]+/[^/]+/issues/(\d+)"
)

# Matches https://github.com/{owner}/{repo} - stops before any trailing slash+path
GITHUB_REPO_RE = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:/[^\s,)\]>\"']*)?"
)

# Table row format: | [repo-name](url) | 3.4k | ...
# Captures the URL and the stars cell (second column after the repo link column)
TABLE_ROW_RE = re.compile(
    r"\|\s*\[.*?\]\((https://github\.com/[^)]+)\)\s*\|([^|]*)\|"
)


def _parse_star_count(raw: str) -> int | None:
    """
    Parse a star count string like '3.4k', '12k', '3400', '1.2m' into an int.
    Returns None if the string cannot be parsed.
    """
    raw = raw.strip().lower().replace(",", "")
    if not raw:
        return None
    try:
        if raw.endswith("k"):
            return int(float(raw[:-1]) * 1_000)
        if raw.endswith("m"):
            return int(float(raw[:-1]) * 1_000_000)
        return int(float(raw))
    except ValueError:
        return None


def _github_api_request(url: str) -> dict | None:
    """
    Make a GET request to the GitHub API. Returns parsed JSON dict or None on error.
    Uses GITHUB_TOKEN env var if available.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "genesis-architect-validator/1.0")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # Caller checks for None = repo missing
        # Other HTTP errors (403 rate limit, etc.) - treat as non-fatal
        return {}
    except Exception:
        # Network errors are non-fatal
        return {}


def verify_github_issues(urls: list[str]) -> list[str]:
    """HEAD-check each GitHub issue URL. Returns list of dead URLs."""
    dead = []
    for url in urls:
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "genesis-architect-validator/1.0")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 404:
                    dead.append(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                dead.append(url)
        except Exception:
            # Network errors are non-fatal - skip rather than false-positive
            pass
    return dead


def verify_github_repos(content: str) -> list[str]:
    """
    For each GitHub repo URL found in a RESEARCH.md table row, call the GitHub API
    and verify:
      1. The repo exists (not 404).
      2. The star count reported in the table is within +-50% of actual.

    Returns a list of issue strings. Empty = all good.
    """
    issues = []

    # Extract (url, raw_stars) from table rows
    table_entries: list[tuple[str, str]] = TABLE_ROW_RE.findall(content)

    if not table_entries:
        # No table entries found - nothing to verify
        return issues

    checked: set[str] = set()

    for raw_url, raw_stars in table_entries:
        # Normalise URL: strip trailing slashes and sub-paths to get owner/repo
        match = re.match(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", raw_url)
        if not match:
            continue
        owner, repo = match.group(1), match.group(2)
        canonical = f"https://github.com/{owner}/{repo}"

        if canonical in checked:
            continue
        checked.add(canonical)

        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        print(f"  Checking repo: {canonical} ...", flush=True)
        data = _github_api_request(api_url)

        if data is None:
            issues.append(f"Repo not found (404): {canonical}")
            continue

        # data == {} means a non-404 network/API error - skip checks
        if not data:
            continue

        if data.get("archived"):
            issues.append(f"Repo is archived (cited as active): {canonical}")

        actual_stars: int = data.get("stargazers_count", 0)
        reported_stars = _parse_star_count(raw_stars)

        if reported_stars is None:
            # Cannot parse the reported count - skip comparison
            continue

        # Allow +-50% tolerance (stars change over time, k-rounding adds noise)
        if actual_stars == 0 and reported_stars == 0:
            continue

        # Avoid division by zero when actual is 0 but reported is not
        if actual_stars == 0:
            ratio = float("inf")
        else:
            ratio = reported_stars / actual_stars

        if ratio < 0.5 or ratio > 1.5:
            issues.append(
                f"Star count mismatch for {canonical}: "
                f"RESEARCH.md says ~{reported_stars:,}, actual is {actual_stars:,} "
                f"(ratio {ratio:.2f}, tolerance +-50%)"
            )

    return issues


def validate(
    path: str,
    verify_issues: bool = False,
    verify_repos: bool = False,
    issues_only: bool = False,
) -> list[str]:
    """
    Returns a list of issues. Empty list = valid.

    `issues_only=True` skips the RESEARCH.md-shaped checks (required sections,
    repo table size, source-link minimum, header signature) so the same script
    can verify GitHub issue URL liveness in non-RESEARCH files like PITFALLS.md.
    """
    issues = []

    try:
        with open(_safe_path(path), "r", encoding="utf-8") as f:
            content = f.read()
    except PermissionError as e:
        return [str(e)]
    except FileNotFoundError:
        return [f"File not found: {path}"]

    if not issues_only:
        # Check required sections
        for section in REQUIRED_SECTIONS:
            if section not in content:
                issues.append(f"Missing section: '{section}'")

        # Check repo count in table
        table_rows = re.findall(r"^\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|", content, re.MULTILINE)
        # Subtract header and separator rows
        data_rows = [r for r in table_rows if not re.match(r"^\|\s*[-:]+\s*\|", r)]
        if len(data_rows) < MIN_REPOS:
            issues.append(
                f"Too few repos in table: found {len(data_rows)}, minimum is {MIN_REPOS}"
            )

        # Check for at least MIN_SOURCES links
        links = re.findall(r"""https?://[^\s,)\]>"']+""", content)
        if len(links) < MIN_SOURCES:
            issues.append(f"Too few source links: found {len(links)}, minimum is {MIN_SOURCES}")

    # Check GitHub issue URLs have valid format (owner/repo/issues/number)
    all_issue_urls = [m for m in re.findall(r"https://github\.com/[^\s,)\]>\"']+", content)
                     if "/issues/" in m]
    malformed = [u for u in all_issue_urls if not GITHUB_ISSUE_RE.match(u)]
    if malformed:
        issues.append(f"Malformed GitHub issue URLs: {malformed}")

    # Optional: HTTP-verify each issue URL exists (not 404)
    if verify_issues and all_issue_urls:
        valid_urls = [u for u in all_issue_urls if GITHUB_ISSUE_RE.match(u)]
        print(f"  Verifying {len(valid_urls)} GitHub issue URL(s)...", flush=True)
        dead = verify_github_issues(valid_urls)
        for url in dead:
            issues.append(f"GitHub issue URL returns 404 (fabricated?): {url}")

    # Optional: API-verify each repo exists and star count is plausible
    if verify_repos:
        token_status = "authenticated" if os.environ.get("GITHUB_TOKEN") else "unauthenticated (60 req/hr limit)"
        print(f"  Verifying GitHub repos via API ({token_status})...", flush=True)
        repo_issues = verify_github_repos(content)
        issues.extend(repo_issues)

    if not issues_only:
        # Check it was generated by Genesis Architect
        if "Genesis Architect" not in content:
            issues.append("Missing 'Genesis Architect' header - was this generated by the skill?")

    return issues


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(
            "Usage: python research_validator.py <path-to-md> [--verify-issues] [--verify-repos] [--issues-only]\n"
            "\n"
            "Flags:\n"
            "  --verify-issues   HTTP HEAD-check each cited GitHub issue URL (checks for 404)\n"
            "  --verify-repos    Call GitHub API for each repo in the table:\n"
            "                      - confirms repo exists\n"
            "                      - checks reported star count is within +-50% of actual\n"
            "  --issues-only     Skip RESEARCH.md-shaped checks (sections, repo table, sources,\n"
            "                    Genesis Architect header). Use this when verifying citation\n"
            "                    URLs in PITFALLS.md or any non-RESEARCH file.\n"
            "\n"
            "Environment:\n"
            "  GITHUB_TOKEN      Optional. Raises GitHub API rate limit from 60 to 5000 req/hr.\n"
        )
        sys.exit(1)

    path = sys.argv[1]
    if any(c in path for c in ['\x00', ';', '|', '&', '`', '$']):
        print("Error: invalid characters in path argument")
        sys.exit(1)
    verify_issues = "--verify-issues" in sys.argv
    verify_repos = "--verify-repos" in sys.argv
    issues_only = "--issues-only" in sys.argv

    issues = validate(
        path,
        verify_issues=verify_issues,
        verify_repos=verify_repos,
        issues_only=issues_only,
    )

    label = path
    if not issues:
        print(f"{label} is valid.")
        sys.exit(0)
    else:
        print(f"{label} has {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)


if __name__ == "__main__":
    main()
