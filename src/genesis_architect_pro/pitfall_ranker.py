"""
Pitfall Ranker - scores and ranks pitfall candidates from all Phase 2 streams.

Implements the ranking algorithm from mcp-strategy.md:
  score = confidence_pts + recency_bonus + corroboration_bonus + engagement_bonus

Sources: GitHub Issues (stream C), Exa/web (stream B), Video signals (stream D).
All sources normalize to RankedPitfall before scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RankedPitfall:
    title: str
    url: str
    source: str          # github_issues | reddit | hn | stackoverflow | exa_blog | video
    confidence: str      # high | medium | low
    signal_type: str     # pitfall | architecture_regret | security | performance | maintenance
    raw_text: str        # excerpt, max 500 chars
    engagement: int = 0  # comments + reactions (0 for non-GitHub sources)
    days_old: int = -1   # -1 = unknown
    corroborated_by: list[str] = field(default_factory=list)  # URLs of same pitfall elsewhere
    score: float = 0.0   # computed by rank()


# ---------------------------------------------------------------------------
# Confidence points
# ---------------------------------------------------------------------------

_CONFIDENCE_PTS = {"high": 3, "medium": 2, "low": 1}


def _confidence_from_source(source: str, engagement: int) -> str:
    if source == "github_issues":
        return "high" if engagement >= 5 else "medium"
    if source in ("hn", "reddit"):
        return "high" if engagement >= 50 else "medium"
    if source == "stackoverflow":
        return "medium"   # caller upgrades to high if accepted answer
    if source == "video":
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Recency bonus
# ---------------------------------------------------------------------------

def _recency_bonus(days_old: int) -> float:
    if days_old < 0:
        return 0.0
    if days_old <= 365:
        return 2.0
    if days_old <= 730:
        return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# Engagement bonus
# ---------------------------------------------------------------------------

def _engagement_bonus(engagement: int) -> float:
    return 1.0 if engagement >= 10 else 0.0


# ---------------------------------------------------------------------------
# Deduplication + corroboration
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "the", "a", "an", "is", "in", "on", "at", "to", "for", "of",
    "and", "or", "not", "with", "when", "after", "before",
}


def _title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z]+", title.lower())
    return {w for w in words if w not in _STOP_WORDS and len(w) > 3}


def _similar(a: RankedPitfall, b: RankedPitfall, threshold: float = 0.4) -> bool:
    """Jaccard similarity on title tokens."""
    ta, tb = _title_tokens(a.title), _title_tokens(b.title)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def deduplicate(pitfalls: list[RankedPitfall]) -> list[RankedPitfall]:
    """
    Merge similar pitfalls. The one with highest raw score wins; others
    contribute their URLs to corroborated_by and their engagement is summed.
    """
    groups: list[list[RankedPitfall]] = []
    for p in pitfalls:
        placed = False
        for group in groups:
            if _similar(p, group[0]):
                group.append(p)
                placed = True
                break
        if not placed:
            groups.append([p])

    merged = []
    for group in groups:
        # representative = highest engagement then highest confidence
        rep = max(group, key=lambda p: (p.engagement, _CONFIDENCE_PTS.get(p.confidence, 0)))
        extra_urls = [p.url for p in group if p.url != rep.url]
        rep.corroborated_by = extra_urls
        rep.engagement = sum(p.engagement for p in group)
        # upgrade confidence if corroborated across sources
        if extra_urls and rep.confidence != "high":
            rep.confidence = "high"
        merged.append(rep)

    return merged


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score(pitfall: RankedPitfall) -> float:
    pts = _CONFIDENCE_PTS.get(pitfall.confidence, 1)
    pts += _recency_bonus(pitfall.days_old)
    pts += _engagement_bonus(pitfall.engagement)
    pts += len(pitfall.corroborated_by) * 3   # +3 per corroborating source
    return float(pts)


def rank(pitfalls: list[RankedPitfall], top_n: int = 10) -> list[RankedPitfall]:
    """
    Deduplicate, score, sort descending. Returns top_n results.
    Mutates .score in place.
    """
    deduped = deduplicate(pitfalls)
    for p in deduped:
        p.score = score(p)
    deduped.sort(key=lambda p: p.score, reverse=True)
    return deduped[:top_n]


# ---------------------------------------------------------------------------
# Converters: bring external data into RankedPitfall
# ---------------------------------------------------------------------------

def from_github_issue(issue_dict: dict) -> RankedPitfall:
    """Convert issue_miner.Issue (as dict or dataclass) to RankedPitfall."""
    if hasattr(issue_dict, "__dict__"):
        issue_dict = issue_dict.__dict__
    engagement = issue_dict.get("comments", 0) + issue_dict.get("reactions", 0)
    return RankedPitfall(
        title=issue_dict.get("title", ""),
        url=issue_dict.get("url", ""),
        source="github_issues",
        confidence=_confidence_from_source("github_issues", engagement),
        signal_type=issue_dict.get("category", "pitfall"),
        raw_text=(issue_dict.get("title", "") + " " + issue_dict.get("body", ""))[:500],
        engagement=engagement,
        days_old=-1,
    )


def from_exa_result(result: dict) -> RankedPitfall:
    """Convert an Exa search result dict to RankedPitfall."""
    url = result.get("url", "")
    source = "reddit" if "reddit.com" in url else \
             "hn" if "ycombinator.com" in url else \
             "stackoverflow" if "stackoverflow.com" in url else \
             "exa_blog"
    engagement = result.get("score", 0)
    return RankedPitfall(
        title=result.get("title", ""),
        url=url,
        source=source,
        confidence=_confidence_from_source(source, engagement),
        signal_type="pitfall",
        raw_text=result.get("text", result.get("snippet", ""))[:500],
        engagement=engagement,
        days_old=-1,
    )


def from_video_signal(signal) -> RankedPitfall:
    """Convert a video_research.VideoSignal to RankedPitfall."""
    return RankedPitfall(
        title=signal.title,
        url=signal.url,
        source="video",
        confidence="medium" if signal.relevance == "high" else "low",
        signal_type="pitfall" if signal.signal_type == "lessons_learned" else "architecture_regret",
        raw_text=signal.description[:500],
        engagement=0,
        days_old=-1,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_ranked(pitfalls: list[RankedPitfall]) -> str:
    """Format top ranked pitfalls for Phase 5 display."""
    if not pitfalls:
        return "No pitfall candidates found."
    lines = ["### Ranked Pitfall Candidates\n"]
    for i, p in enumerate(pitfalls, 1):
        icon = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(p.confidence, "⚪")
        lines.append(f"{i}. {icon} **{p.title}** (score: {p.score:.0f})")
        lines.append(f"   Source: {p.source} | Engagement: {p.engagement} | Type: {p.signal_type}")
        lines.append(f"   [{p.url}]({p.url})")
        if p.corroborated_by:
            lines.append(f"   Corroborated by {len(p.corroborated_by)} other source(s)")
        lines.append("")
    return "\n".join(lines)
