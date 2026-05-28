"""GitHub API - search repos and fetch issues."""

import urllib.request
import urllib.error
import urllib.parse
import json
from typing import Any


_RATE_LIMIT_MSG = """\
GitHub rate limit reached (60 requests/hour without a token).
To continue, create a free token:
  1. Go to https://github.com/settings/tokens/new
  2. Select scope: public_repo (read-only is enough)
  3. Copy the token and run:
       genesis config set GITHUB_TOKEN <your-token>
Then re-run your command.
"""


class GitHubRateLimitError(Exception):
    pass


def _get(url: str, token: str | None = None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "genesis-architect/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            # Check X-RateLimit-Remaining header
            remaining = e.headers.get("X-RateLimit-Remaining", "")
            if remaining == "0":
                raise GitHubRateLimitError(_RATE_LIMIT_MSG) from e
            raise GitHubRateLimitError(_RATE_LIMIT_MSG) from e
        if e.code == 429:
            raise GitHubRateLimitError(_RATE_LIMIT_MSG) from e
        raise


def search_repos(
    query: str,
    token: str | None = None,
    limit: int = 15,
    language: str | None = None,
) -> list[dict]:
    base = f"{query} in:description,readme stars:>50"
    if language:
        base += f" language:{language}"
    q = urllib.parse.quote(base)
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&per_page={limit}"
    data = _get(url, token)
    return [
        {"name": r["full_name"], "stars": r["stargazers_count"], "url": r["html_url"],
         "description": r.get("description", "")}
        for r in data.get("items", [])
    ]


def fetch_issues(repo: str, token: str | None = None, limit: int = 20) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/issues?state=closed&per_page={limit}&labels=bug"
    try:
        issues = _get(url, token)
        return [{"title": i["title"], "body": (i.get("body") or "")[:500], "url": i["html_url"]}
                for i in issues if "pull_request" not in i]
    except GitHubRateLimitError:
        raise
    except Exception:
        return []
