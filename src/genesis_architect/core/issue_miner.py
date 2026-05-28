#!/usr/bin/env python3
"""
issue_miner.py - Mine GitHub Issues for production pitfalls.

Uses GitHub GraphQL API (single request per repo) for efficiency.
Requires GITHUB_TOKEN env var. Falls back to REST if GraphQL unavailable.

Usage:
  python scripts/issue_miner.py pallets/click tiangolo/typer tqdm/tqdm
  python scripts/issue_miner.py pallets/click --limit 50 --output pitfalls.json
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from pathlib import Path


GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"

SECURITY_KEYWORDS = {"cve", "vulnerability", "traversal", "injection", "exploit", "bypass", "overflow"}
PERFORMANCE_KEYWORDS = {"slow", "memory", "leak", "timeout", "oom", "performance", "hang", "freeze"}
BREAKING_KEYWORDS = {"breaking", "regression", "broke", "broken", "removed", "deprecated"}
BUG_LABELS = {"bug", "regression", "breaking-change", "security", "performance"}


@dataclass
class Issue:
    repo: str
    number: int
    title: str
    url: str
    comments: int
    reactions: int
    category: str
    labels: list[str]
    closed: bool

    @property
    def engagement(self) -> int:
        return self.comments + self.reactions


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    h = {"User-Agent": "genesis-architect-issue-miner/1.0", "Accept": "application/json"}
    if token:
        h["Authorization"] = f"bearer {token}"
    return h


def _match_keywords(text: str, keywords: set[str]) -> bool:
    """Return True if any keyword matches as a whole word in text."""
    for k in keywords:
        if re.search(r"\b" + re.escape(k) + r"\b", text):
            return True
    return False


def _classify(title: str, labels: list[str]) -> str:
    t = title.lower()
    label_set = {l.lower() for l in labels}
    if _match_keywords(t, SECURITY_KEYWORDS) or "security" in label_set:
        return "security"
    if _match_keywords(t, PERFORMANCE_KEYWORDS) or "performance" in label_set:
        return "performance"
    if _match_keywords(t, BREAKING_KEYWORDS) or "regression" in label_set or "breaking-change" in label_set:
        return "breaking"
    return "bug"


def _graphql_query(owner: str, repo: str, limit: int) -> str:
    return """
    query {
      repository(owner: "%s", name: "%s") {
        issues(first: %d, states: CLOSED, orderBy: {field: COMMENTS, direction: DESC}) {
          nodes {
            number
            title
            url
            comments { totalCount }
            reactions { totalCount }
            labels(first: 10) { nodes { name } }
          }
        }
      }
    }
    """ % (owner, repo, min(limit, 100))


def fetch_via_graphql(owner: str, repo: str, limit: int) -> list[Issue]:
    query = {"query": _graphql_query(owner, repo, limit)}
    data = json.dumps(query).encode("utf-8")
    req = urllib.request.Request(GRAPHQL_URL, data=data, headers=_headers())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # NOSONAR - external API, URL from hardcoded constants
            result = json.loads(resp.read())
        nodes = result.get("data", {}).get("repository", {}).get("issues", {}).get("nodes", [])
        issues = []
        for n in nodes:
            labels = [l["name"] for l in n.get("labels", {}).get("nodes", [])]
            issues.append(Issue(
                repo=f"{owner}/{repo}",
                number=n["number"],
                title=n["title"],
                url=n["url"],
                comments=n["comments"]["totalCount"],
                reactions=n["reactions"]["totalCount"],
                category=_classify(n["title"], labels),
                labels=labels,
                closed=True,
            ))
        return issues
    except Exception as e:
        print(f"  GraphQL failed for {owner}/{repo}: {e}. Falling back to REST.", file=sys.stderr)
        return fetch_via_rest(owner, repo, limit)


def fetch_via_rest(owner: str, repo: str, limit: int) -> list[Issue]:
    issues = []
    page = 1
    while len(issues) < limit:
        url = (f"{REST_URL}/repos/{owner}/{repo}/issues"
               f"?state=closed&per_page=100&page={page}&sort=comments")
        req = urllib.request.Request(url, headers=_headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # NOSONAR - external API, URL from hardcoded constants
                items = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print("  GitHub rate limit hit. Set GITHUB_TOKEN for higher limits.")
            break
        except Exception as e:
            print(f"  REST error: {e}")
            break
        if not items:
            break
        for item in items:
            if "pull_request" in item:
                continue
            labels = [l["name"] for l in item.get("labels", [])]
            issues.append(Issue(
                repo=f"{owner}/{repo}",
                number=item["number"],
                title=item["title"],
                url=item["html_url"],
                comments=item.get("comments", 0),
                reactions=item.get("reactions", {}).get("total_count", 0),
                category=_classify(item["title"], labels),
                labels=labels,
                closed=True,
            ))
            if len(issues) >= limit:
                break
        page += 1
    return issues


def mine_repo(repo_slug: str, limit: int = 100, min_engagement: int = 3) -> list[Issue]:
    if "/" not in repo_slug:
        print(f"  Invalid repo: {repo_slug} (expected owner/name)")
        return []
    owner, repo = repo_slug.split("/", 1)
    print(f"Mining {owner}/{repo}...", flush=True)
    all_issues = fetch_via_graphql(owner, repo, limit)
    filtered = [i for i in all_issues if i.engagement >= min_engagement]
    filtered.sort(key=lambda i: i.engagement, reverse=True)
    print(f"  Found {len(filtered)} issues (engagement >= {min_engagement}) from {len(all_issues)} total")
    return filtered


def format_pitfall(issue: Issue, index: int) -> str:
    return (
        f"## Pitfall {index}: {issue.title}\n"
        f"**Seen in**: [{issue.repo}#{issue.number}]({issue.url})\n"
        f"**Category**: {issue.category}\n"
        f"**Engagement**: {issue.comments} comments, {issue.reactions} reactions\n"
        f"**Labels**: {', '.join(issue.labels) if issue.labels else 'none'}\n"
        f"**Root cause**: TODO: add root cause analysis\n"
        f"**Mitigation**: TODO: add mitigation\n"
    )


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: issue_miner.py <owner/repo> [<owner/repo>...] [--limit N] [--output file.json]")
        sys.exit(1)

    limit = 100
    output_file = None
    repos = []

    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_file = args[i + 1]
            i += 2
        else:
            repos.append(args[i])
            i += 1

    if not repos:
        print("Error: no repos specified")
        sys.exit(1)

    all_issues: list[Issue] = []
    for repo in repos:
        all_issues.extend(mine_repo(repo, limit=limit))

    print(f"\nTotal: {len(all_issues)} issues across {len(repos)} repo(s)")

    if output_file:
        Path(output_file).write_text(
            json.dumps([asdict(i) for i in all_issues], indent=2),
            encoding="utf-8",
        )
        print(f"Saved to {output_file}")
    else:
        print("\n--- Top pitfalls ---")
        for idx, issue in enumerate(all_issues[:10], 1):
            print(f"\n{format_pitfall(issue, idx)}")


if __name__ == "__main__":
    main()
