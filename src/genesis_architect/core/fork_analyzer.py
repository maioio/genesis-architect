"""Phase 2 fork analysis - finds top 3 most actively maintained forks."""

import urllib.request
import urllib.error
import urllib.parse
import json
from datetime import datetime, timezone, timedelta

from genesis_architect.core.github import GitHubRateLimitError, _RATE_LIMIT_MSG


def _get(url: str, token: str | None = None) -> list | dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "genesis-architect/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            remaining = e.headers.get("X-RateLimit-Remaining", "")
            if e.code == 429 or remaining == "0":
                raise GitHubRateLimitError(_RATE_LIMIT_MSG) from e
        raise


def _recent_merged_pr_count(repo: str, token: str | None, since_days: int = 180) -> int:
    """Count merged PRs in the last `since_days` days. Ignores star count."""
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        params = urllib.parse.urlencode({
            "state": "closed", "sort": "updated", "direction": "desc",
            "per_page": 30, "since": since_iso,
        })
        prs = _get(f"https://api.github.com/repos/{repo}/pulls?{params}", token)
        return sum(1 for pr in prs if pr.get("merged_at"))
    except GitHubRateLimitError:
        raise
    except Exception:
        return 0


def top_active_forks(repo: str, token: str | None = None, limit: int = 3) -> list[dict]:
    """
    Return the top `limit` forks ranked by number of merged PRs
    in the last 6 months. Ignores star count entirely.
    """
    try:
        forks = _get(
            f"https://api.github.com/repos/{repo}/forks?sort=newest&per_page=20",
            token,
        )
    except GitHubRateLimitError:
        raise
    except Exception:
        return []

    scored = []
    for fork in forks:
        name = fork["full_name"]
        activity = _recent_merged_pr_count(name, token)
        if activity > 0:
            scored.append({
                "name": name,
                "url": fork["html_url"],
                "recent_merged_prs": activity,
                "pushed_at": fork.get("pushed_at", ""),
            })

    scored.sort(key=lambda f: f["recent_merged_prs"], reverse=True)
    return scored[:limit]
