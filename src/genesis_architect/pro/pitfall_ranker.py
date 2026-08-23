"""
Pitfall Ranker - scores and ranks pitfall candidates from all Phase 2 streams.

Scoring:
  score = confidence_pts
        + recency_bonus        (needs a real publish/create date)
        + engagement_bonus     (needs real comment/reaction counts)
        + corroboration_bonus
        + authority_bonus      (engagement-free: how official is the host?)
        + substance_bonus      (engagement-free: does the text carry evidence?)

The last two exist because most sources carry no engagement at all. Web and
video results arrive with no comment counts, so an engagement-only ranker
collapses them to one identical score - an official forum thread containing
working code ranks exactly level with a vendor marketing page. Authority and
substance are derived from what every result *does* carry (its host and its
text), so a coarse ordering survives even when every other signal is absent.

Sources: GitHub Issues (stream C), web (stream B), media/video (stream D).
All sources normalize to RankedPitfall before scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from genesis_architect.core.urls import host_matches, host_of


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RankedPitfall:
    title: str
    url: str
    source: str          # github_issues | reddit | hn | stackoverflow | web | video
    confidence: str      # high | medium | low
    signal_type: str     # pitfall | architecture_regret | security | performance | maintenance
    raw_text: str        # excerpt, max 500 chars
    engagement: int = 0  # comments + reactions. 0 = none reported by the source.
    days_old: int = -1   # -1 = unknown
    corroborated_by: list[str] = field(default_factory=list)  # URLs of same pitfall elsewhere
    score: float = 0.0   # computed by rank()
    # Provider relevance (Exa/Tavily 0.0-1.0). Kept separate from engagement:
    # it measures query match, not human attention, and must never be scored
    # as if a human had upvoted anything.
    relevance: float = 0.0
    provider: str = ""   # exa | tavily | firecrawl | github | ... ("" = unrecorded)
    score_breakdown: dict = field(default_factory=dict)  # component -> points


# ---------------------------------------------------------------------------
# Confidence points
# ---------------------------------------------------------------------------

_CONFIDENCE_PTS = {"high": 3, "medium": 2, "low": 1}


def _confidence_from_source(source: str, engagement: int, url: str = "") -> str:
    if source == "github_issues":
        return "high" if engagement >= 5 else "medium"
    if source in ("hn", "reddit"):
        return "high" if engagement >= 50 else "medium"
    if source == "stackoverflow":
        return "medium"   # caller upgrades to high if accepted answer
    if source == "video":
        return "medium"
    # A web result with no engagement is not automatically low-confidence:
    # an official forum or tracker is a stronger source than a random blog
    # even when nobody reported a vote count for it.
    if url and _authority_tier(url) == "official":
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


_DATE_FIELDS = (
    "published_date", "publishedDate", "created_at", "createdAt",
    "date", "published", "updated_at",
)


def days_old_from(data: dict) -> int:
    """Best-effort age in days from whichever date field the source provided.

    Returns -1 when no field is present or none of them parse - the ranker
    treats -1 as "unknown" and applies no recency bonus, rather than guessing
    an age and rewarding a result for it.
    """
    from datetime import datetime, timezone

    for key in _DATE_FIELDS:
        raw = data.get(key)
        if not raw or not isinstance(raw, str):
            continue
        text = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            # Fall back to a bare YYYY-MM-DD prefix (covers RFC-ish strings).
            match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
            if not match:
                continue
            parsed = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - parsed).days
        return max(delta, 0)
    return -1


# ---------------------------------------------------------------------------
# Engagement bonus
# ---------------------------------------------------------------------------

def _engagement_bonus(engagement: int) -> float:
    return 1.0 if engagement >= 10 else 0.0


# ---------------------------------------------------------------------------
# Authority bonus (engagement-free)
# ---------------------------------------------------------------------------

# Domains where the maintainers of the thing being discussed actually answer.
# Matched by host or subdomain via host_matches - never by substring, so
# https://github.com.attacker.test/x cannot borrow GitHub's standing.
_OFFICIAL_DOMAINS = (
    "github.com", "gitlab.com",
    "stackoverflow.com", "stackexchange.com", "superuser.com", "serverfault.com",
    "developer.mozilla.org", "learn.microsoft.com", "developer.apple.com",
    "developer.android.com", "developers.google.com",
    "w3.org", "ietf.org", "rfc-editor.org", "iso.org", "khronos.org",
    "ecma-international.org", "unicode.org", "python.org", "gnu.org",
)

# Leading host labels that mark an operator-run surface (community.adobe.com,
# discourse.llvm.org, bugs.webkit.org). Matched against the first label only,
# which anchors the test instead of letting it float anywhere in the host.
#
# This is a coarse quality signal, not a trust boundary: anyone can name a
# subdomain `community`. It exists to order results when nothing else
# distinguishes them, and a site that goes to the trouble of running a real
# forum is on average a better source than one that does not.
_OFFICIAL_LABELS = frozenset({
    "community", "forum", "forums", "discourse", "discuss", "lists", "mailman",
    "docs", "documentation", "wiki", "kb", "support", "bugs", "bugzilla", "issues",
})

# High-signal community aggregators: practitioner discussion, not vendor copy.
_COMMUNITY_DOMAINS = (
    "news.ycombinator.com", "lobste.rs", "reddit.com", "slashdot.org",
    "arxiv.org", "acm.org", "ieee.org", "usenix.org",
)


def _authority_tier(url: str) -> str:
    """official | community | unknown - how accountable is the host?"""
    host = host_of(url)
    if not host:
        return "unknown"
    if host_matches(url, *_COMMUNITY_DOMAINS):
        return "community"
    if host_matches(url, *_OFFICIAL_DOMAINS):
        return "official"
    if host.split(".")[0] in _OFFICIAL_LABELS:
        return "official"
    return "unknown"


def _authority_bonus(url: str) -> float:
    return {"official": 2.0, "community": 1.0}.get(_authority_tier(url), 0.0)


# ---------------------------------------------------------------------------
# Substance bonus (engagement-free)
# ---------------------------------------------------------------------------

# Something that looks like real code or a real error, not prose about code.
_CODE_MARKERS = re.compile(
    r"```|`[^`\n]{3,}`|"
    r"\b(?:def|class|function|const|let|var|import|from|return|async|await)\s+\w|"
    r"\w+\([^)]*\)\s*[;{]|"
    r"\b(?:Error|Exception|Traceback|stack trace|at line \d+)\b|"
    r"[{}\[\]]\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Concrete measurements - the mark of someone who actually ran the thing.
_MEASUREMENT_MARKERS = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:ms|s|sec|seconds|min|minutes|px|dpi|MB|GB|KB|%|fps|req/s|x)\b|"
    r"\bv?\d+\.\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)


def _substance_bonus(raw_text: str) -> float:
    """Reward text carrying evidence over text describing a problem in prose."""
    if not raw_text:
        return 0.0
    points = 0.0
    if _CODE_MARKERS.search(raw_text):
        points += 1.0
    if len(_MEASUREMENT_MARKERS.findall(raw_text)) >= 2:
        points += 0.5
    return points


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
        # Representative = most accountable host first, then real engagement,
        # then confidence. Authority leads because a group of duplicates is
        # usually one official thread plus several sites paraphrasing it, and
        # engagement alone cannot tell them apart when nobody reports counts.
        rep = max(group, key=lambda p: (
            _authority_bonus(p.url),
            p.engagement,
            _CONFIDENCE_PTS.get(p.confidence, 0),
        ))
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
    """Total score, and record the per-component split on the pitfall.

    The breakdown is kept because a ranking nobody can explain is a ranking
    nobody can trust: when two results tie, the caller can see whether it was
    a real tie or a missing signal.
    """
    breakdown = {
        "confidence": float(_CONFIDENCE_PTS.get(pitfall.confidence, 1)),
        "recency": _recency_bonus(pitfall.days_old),
        "engagement": _engagement_bonus(pitfall.engagement),
        "corroboration": len(pitfall.corroborated_by) * 3.0,  # +3 per corroborating source
        "authority": _authority_bonus(pitfall.url),
        "substance": _substance_bonus(pitfall.raw_text),
    }
    pitfall.score_breakdown = breakdown
    return float(sum(breakdown.values()))


def rank(pitfalls: list[RankedPitfall], top_n: int = 10) -> list[RankedPitfall]:
    """
    Deduplicate, score, sort descending. Returns top_n results.
    Mutates .score in place.

    Ties break on relevance (provider query match) then title, so the order is
    stable across runs instead of depending on collection order.
    """
    deduped = deduplicate(pitfalls)
    for p in deduped:
        p.score = score(p)
    deduped.sort(key=lambda p: (p.score, p.relevance, p.title), reverse=True)
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
        days_old=days_old_from(issue_dict),
        provider=issue_dict.get("provider", "github"),
    )


def from_web_result(result: dict) -> RankedPitfall:
    """Convert one web search result (Exa, Tavily, Firecrawl, ...) to RankedPitfall.

    ``score`` from a search provider is a query-relevance float, not a human
    signal - it goes to ``relevance``. ``engagement`` is only filled from
    fields that really do count people (comments, votes, reactions).
    """
    url = result.get("url", "")
    # Match on the parsed host, not a substring. The source label drives a
    # confidence weight, so a URL like https://evil.test/reddit.com/x must not
    # be able to borrow reddit's credibility.
    source = "reddit" if host_matches(url, "reddit.com") else \
             "hn" if host_matches(url, "ycombinator.com") else \
             "stackoverflow" if host_matches(url, "stackoverflow.com") else \
             "web"
    engagement = int(
        result.get("engagement")
        or result.get("comments", 0) or 0
    ) + int(result.get("points", 0) or result.get("upvotes", 0) or 0)
    try:
        relevance = float(result.get("relevance", result.get("score", 0.0)) or 0.0)
    except (TypeError, ValueError):
        relevance = 0.0
    return RankedPitfall(
        title=result.get("title", ""),
        url=url,
        source=source,
        confidence=_confidence_from_source(source, engagement, url),
        signal_type="pitfall",
        raw_text=(result.get("text") or result.get("snippet") or
                  result.get("content") or "")[:500],
        engagement=engagement,
        days_old=days_old_from(result),
        relevance=relevance,
        provider=result.get("provider", ""),
    )


# The old name shipped in the public API; web results are no longer Exa-only.
from_exa_result = from_web_result


def from_video_signal(signal) -> RankedPitfall:
    """Convert a video_research.MediaSignal to RankedPitfall."""
    return RankedPitfall(
        title=signal.title,
        url=signal.url,
        source="video",
        confidence="medium" if signal.relevance == "high" else "low",
        signal_type="pitfall" if signal.signal_type == "lessons_learned" else "architecture_regret",
        raw_text=signal.description[:500],
        engagement=0,
        days_old=getattr(signal, "days_old", -1),
        provider=getattr(signal, "provider", ""),
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def why_ranked(pitfall: RankedPitfall) -> str:
    """One-line explanation of a pitfall's score, listing only what scored.

    Components worth 0 are omitted rather than shown as zeros, so the line
    reads as the evidence that was actually found.
    """
    labels = {
        "confidence": "confidence",
        "recency": "recent",
        "engagement": "engagement",
        "corroboration": "corroborated",
        "authority": "authoritative host",
        "substance": "code/numbers in text",
    }
    parts = [
        f"{labels[key]} +{value:g}"
        for key, value in (pitfall.score_breakdown or {}).items()
        if value and key in labels
    ]
    return ", ".join(parts) if parts else "no scoring signals"


def format_ranked(pitfalls: list[RankedPitfall]) -> str:
    """Format top ranked pitfalls for Phase 5 display."""
    if not pitfalls:
        return "No pitfall candidates found."
    lines = ["### Ranked Pitfall Candidates\n"]
    for i, p in enumerate(pitfalls, 1):
        icon = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(p.confidence, "⚪")
        lines.append(f"{i}. {icon} **{p.title}** (score: {p.score:g})")
        meta = [f"Source: {p.source}"]
        if p.provider:
            meta.append(f"via {p.provider}")
        # "Engagement: 0" is noise when the source never reported a count -
        # only show it when a real number came back.
        if p.engagement:
            meta.append(f"Engagement: {p.engagement}")
        meta.append(f"Type: {p.signal_type}")
        lines.append("   " + " | ".join(meta))
        lines.append(f"   Why this rank: {why_ranked(p)}")
        lines.append(f"   [{p.url}]({p.url})")
        if p.corroborated_by:
            lines.append(f"   Corroborated by {len(p.corroborated_by)} other source(s)")
        lines.append("")

    if len({p.score for p in pitfalls}) == 1 and len(pitfalls) > 1:
        lines.append(
            "> Every candidate scored identically - the sources carried no dates, "
            "no engagement counts, and no distinguishing evidence. Treat this "
            "list as unranked.\n"
        )
    return "\n".join(lines)
