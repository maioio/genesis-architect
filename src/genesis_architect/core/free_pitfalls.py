"""Lightweight pitfall hook.

Returns the top GitHub pitfalls from similar repos using simple engagement
ordering. It is intentionally cheap and dependency-free, which makes it the
right choice for fast paths and previews.

For the full picture use :mod:`genesis_architect.pro.research_orchestrator`,
which does a multi-source merge with recency/corroboration scoring plus video
and registry signals. Both ship in this package - nothing here is gated.
"""

from __future__ import annotations

from genesis_architect.core.issue_miner import Issue, format_pitfall, mine_repo

FREE_PITFALL_CAP = 3


def top_free_pitfalls(
    repo_slugs: list[str],
    cap: int = FREE_PITFALL_CAP,
    limit_per_repo: int = 100,
    min_engagement: int = 3,
) -> list[Issue]:
    """Mine the given repos and return the top `cap` pitfalls by engagement.

    Free tier: plain engagement sort, hard cap. No ranking algorithm,
    no dedup heuristics, no cross-source merge (those are Pro).
    """
    collected: list[Issue] = []
    for slug in repo_slugs:
        collected.extend(mine_repo(slug, limit=limit_per_repo, min_engagement=min_engagement))
    collected.sort(key=lambda i: i.engagement, reverse=True)
    return collected[:cap]


def format_free_summary(pitfalls: list[Issue]) -> str:
    """Render the capped pitfalls plus an upgrade pointer."""
    if not pitfalls:
        return (
            "No high-engagement pitfalls found in the scanned repos.\n"
            "Try more or larger repos, or upgrade to Pro for multi-source "
            "research (video, Reddit, package registries)."
        )
    lines = [f"Top {len(pitfalls)} pitfalls from similar projects (free tier):\n"]
    for idx, issue in enumerate(pitfalls, start=1):
        lines.append(format_pitfall(issue, idx))
    lines.append(
        "\nThis is the free preview (top "
        f"{FREE_PITFALL_CAP} by engagement). Genesis Architect Pro ranks "
        "across GitHub, video, Reddit, and package registries, with "
        "severity scoring and cross-session memory. "
        "https://github.com/maioio/genesis-architect"
    )
    return "\n".join(lines)
