"""GitHub API - search repos and fetch issues."""

import json
import urllib.error
import urllib.parse
import urllib.request
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


class GitHubQueryError(Exception):
    """The search query was rejected by GitHub (HTTP 422)."""


#: GitHub rejects a search with HTTP 422 once the `q` parameter exceeds this
#: many characters. Documented at
#: https://docs.github.com/rest/search#limitations-on-query-length
GITHUB_MAX_QUERY_CHARS = 256

#: Room the qualifiers need (` in:description,readme stars:>50 language:...`).
_QUALIFIER_BUDGET = 60


def _fit_query(text: str, budget: int) -> str:
    """Trim a free-text vision to fit GitHub's query-length limit.

    A vision long enough to be useful to a human is often too long for the
    search API, which answers with a bare 422. Cutting on a word boundary
    keeps the query meaningful instead of truncating mid-token.
    """
    text = " ".join(text.split())
    if len(text) <= budget:
        return text
    cut = text[:budget]
    if " " in cut:
        cut = cut[:cut.rindex(" ")]
    return cut.rstrip(" ,.;:-")


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
        if e.code == 422:
            # Almost always an over-long or malformed query. Callers trim to
            # the documented limit, so reaching here means something else was
            # wrong; say so plainly rather than surfacing a bare HTTPError.
            raise GitHubQueryError(
                "GitHub rejected the search query (HTTP 422). Queries are "
                f"limited to {GITHUB_MAX_QUERY_CHARS} characters and cannot "
                "contain unbalanced quotes or stray qualifiers. Try a shorter, "
                "more specific description."
            ) from e
        raise


def search_repos(
    query: str,
    token: str | None = None,
    limit: int = 15,
    language: str | None = None,
) -> list[dict]:
    # Trim first: a long vision is a good prompt but an invalid search query,
    # and GitHub answers over-long queries with a bare 422.
    budget = GITHUB_MAX_QUERY_CHARS - _QUALIFIER_BUDGET
    base = f"{_fit_query(query, budget)} in:description,readme stars:>50"
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
