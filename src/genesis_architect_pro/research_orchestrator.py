"""
Research Orchestrator - coordinates all Phase 2 streams and produces ranked output.

Runs streams A/B/C/D in the correct order:
  A (GitHub repos) + B (Exa ecosystem) + D (Video metadata) -> parallel
  C (Issue mining) -> after A completes (needs repo list)

Saves results to vault and returns a ResearchSummary ready for Phase 3/5.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from genesis_architect.core import vault as _vault
from genesis_architect_pro.pitfall_ranker import (
    RankedPitfall,
    from_github_issue,
    from_exa_result,
    from_video_signal,
    rank,
    format_ranked,
)
from genesis_architect_pro.video_research import (
    parse_exa_results,
    format_media_signals,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RepoResult:
    slug: str           # owner/repo
    stars: int | None   # None = source didn't report a star count (not "0 stars")
    url: str
    description: str
    deep_analyzed: bool = False


@dataclass
class ResearchSummary:
    vision: str
    repos: list[RepoResult] = field(default_factory=list)
    pitfall_candidates: list[RankedPitfall] = field(default_factory=list)
    video_signals: list = field(default_factory=list)   # VideoSignal list
    ecosystem_notes: list[str] = field(default_factory=list)
    research_quality: str = "THIN"   # FULL | PARTIAL | THIN
    floor_met: bool = False
    duration_seconds: float = 0.0
    from_vault: bool = False

    def quality_reason(self) -> str:
        deep = sum(1 for r in self.repos if r.deep_analyzed)
        issues = len(self.pitfall_candidates)
        if deep >= 8 and issues >= 5:
            return f"FULL ({deep} repos deep-analyzed, {issues} issues)"
        if deep >= 5 or issues >= 2:
            return f"PARTIAL ({deep} repos deep-analyzed, {issues} issues)"
        return f"THIN ({deep} repos deep-analyzed, {issues} issues)"


# ---------------------------------------------------------------------------
# Vault integration
# ---------------------------------------------------------------------------

_VAULT_TTL_DAYS = 7   # re-use cached research for same vision for 7 days


def _vault_key(vision: str) -> str:
    return f"research:{vision.lower().strip()[:80]}"


def load_from_vault(vision: str, project_root: Path) -> ResearchSummary | None:
    """Return cached ResearchSummary if fresh, else None."""
    import json as _json
    entry = _vault.get(_vault_key(vision), project_root)
    if entry is None:
        return None
    age_days = (time.time() - entry.get("created_at", 0)) / 86400
    if age_days > _VAULT_TTL_DAYS:
        return None
    try:
        raw = entry.get("solution", "{}")
        data = _json.loads(raw) if isinstance(raw, str) else raw
        summary = ResearchSummary(vision=data["vision"])
        summary.repos = [RepoResult(**r) for r in data.get("repos", [])]
        summary.ecosystem_notes = data.get("ecosystem_notes", [])
        summary.research_quality = data.get("research_quality", "THIN")
        summary.floor_met = data.get("floor_met", False)
        summary.from_vault = True
        pitfalls_raw = data.get("pitfall_candidates", [])
        summary.pitfall_candidates = [RankedPitfall(**p) for p in pitfalls_raw]
        return summary
    except Exception:
        return None


def save_to_vault(summary: ResearchSummary, project_root: Path) -> None:
    """Persist ResearchSummary to vault as a JSON blob."""
    import json
    data = {
        "vision": summary.vision,
        "repos": [r.__dict__ for r in summary.repos],
        "pitfall_candidates": [p.__dict__ for p in summary.pitfall_candidates],
        "ecosystem_notes": summary.ecosystem_notes,
        "research_quality": summary.research_quality,
        "floor_met": summary.floor_met,
    }
    _vault.put(
        key=_vault_key(summary.vision),
        solution=json.dumps(data),
        source_url="genesis:research_orchestrator",
        project_root=project_root,
    )


# ---------------------------------------------------------------------------
# Quality signal
# ---------------------------------------------------------------------------

def compute_quality(summary: ResearchSummary) -> str:
    deep = sum(1 for r in summary.repos if r.deep_analyzed)
    issues = len(summary.pitfall_candidates)
    # FULL: real GitHub MCP used (deep_analyzed repos present), 8+, 5+ issues
    if deep >= 8 and issues >= 5:
        return "FULL"
    # PARTIAL: some deep analysis or some issues
    if deep >= 5 or issues >= 2:
        return "PARTIAL"
    return "THIN"


# ---------------------------------------------------------------------------
# Research floor gate
# ---------------------------------------------------------------------------

FLOOR_MIN_REPOS = 12
FLOOR_MIN_DEEP = 5


def check_floor(summary: ResearchSummary) -> tuple[bool, str]:
    """
    Returns (passed, message).
    Phase 5 prerequisite gate - must pass before showing architecture choice.
    """
    total = len(summary.repos)
    deep = sum(1 for r in summary.repos if r.deep_analyzed)
    if total >= FLOOR_MIN_REPOS and deep >= FLOOR_MIN_DEEP:
        return True, f"Floor met: {total} repos, {deep} deep-analyzed"
    return False, (
        f"Floor not met: {total}/{FLOOR_MIN_REPOS} repos, {deep}/{FLOOR_MIN_DEEP} deep-analyzed. "
        f"Options: A) Broaden search  B) Accept thin research (--override)  C) Architect Mode"
    )


# ---------------------------------------------------------------------------
# Stream merging
# ---------------------------------------------------------------------------

def merge_streams(
    github_issues: list,        # list of issue_miner.Issue objects
    exa_results: list[dict],    # raw Exa results from stream B
    video_exa_results: list[dict],  # raw Exa results from stream D
    vision: str,
) -> tuple[list[RankedPitfall], list]:
    """
    Convert all stream outputs to RankedPitfall, rank them.
    Returns (ranked_pitfalls, video_signals).
    """
    from genesis_architect_pro.license import require_license
    require_license("multi-source research orchestration")

    candidates: list[RankedPitfall] = []

    # Stream C: GitHub issues
    for issue in github_issues:
        candidates.append(from_github_issue(issue))

    # Stream B: Exa ecosystem results
    for result in exa_results:
        candidates.append(from_exa_result(result))

    # Stream D: Video signals -> pitfall candidates
    video_signals = parse_exa_results(video_exa_results, vision)
    for signal in video_signals:
        if signal.signal_type in ("lessons_learned", "architecture_talk"):
            candidates.append(from_video_signal(signal))

    ranked = rank(candidates, top_n=10)
    return ranked, video_signals


# ---------------------------------------------------------------------------
# Summary formatter (for Phase 5 display)
# ---------------------------------------------------------------------------

def format_summary(summary: ResearchSummary) -> str:
    """Render the research summary for the user.

    Graceful degradation contract: every section is gated by `if`, so a source
    that returned nothing (e.g. Reddit when Apify is offline) simply does not
    appear. We never show "source unavailable" or a failure line to the user -
    the summary stays clean and is built only from sources that actually
    produced results. Never fabricate a section to fill a gap.
    """
    lines = []

    # Header
    quality = summary.research_quality
    reason = summary.quality_reason()
    from_cache = " (from vault cache)" if summary.from_vault else ""
    lines.append(f"## Research Summary{from_cache}")
    lines.append(f"**Research quality: {quality}** ({reason})")
    lines.append("")

    # Repo table
    if summary.repos:
        lines.append("### Analyzed Repositories")
        lines.append("| Repository | Stars | Deep Analyzed |")
        lines.append("|-----------|-------|---------------|")
        # Unknown star counts sort last, never treated as equal to (or below) 0.
        ranked_repos = sorted(
            summary.repos,
            key=lambda x: (-1, 0) if x.stars is None else (0, x.stars),
            reverse=True,
        )
        for r in ranked_repos[:15]:
            deep = "Yes" if r.deep_analyzed else "-"
            stars_display = f"{r.stars:,}" if r.stars is not None else "unknown"
            lines.append(f"| [{r.slug}]({r.url}) | {stars_display} | {deep} |")
        lines.append("")

    # Ecosystem notes
    if summary.ecosystem_notes:
        lines.append("### Ecosystem Signals")
        for note in summary.ecosystem_notes:
            lines.append(f"- {note}")
        lines.append("")

    # Ranked pitfalls
    if summary.pitfall_candidates:
        lines.append(format_ranked(summary.pitfall_candidates))

    # Video signals
    if summary.video_signals:
        lines.append(format_media_signals(summary.video_signals))

    # Floor status
    floor_ok, floor_msg = check_floor(summary)
    if not floor_ok:
        lines.append(f"\n**{floor_msg}**")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shim helpers (for use when full MCP results are passed in as dicts)
# ---------------------------------------------------------------------------

def build_summary_from_raw(
    vision: str,
    repos: list[dict],
    github_issues: list,
    exa_results: list[dict],
    video_exa_results: list[dict],
    project_root: Path | None = None,
) -> ResearchSummary:
    """
    Build a ResearchSummary from raw data collected by Genesis during Phase 2.
    Call this after all streams complete to get the ranked, merged view.
    """
    start = time.time()

    repo_results = [
        RepoResult(
            slug=r.get("name", r.get("slug", "")),
            # Some search sources (e.g. the GitHub MCP repo-search tool) don't
            # report a star count at all - leave it None rather than coercing
            # to 0, which would misrepresent "unreported" as "unpopular".
            stars=r.get("stars", r.get("stargazers_count")),
            url=r.get("url", r.get("html_url", "")),
            description=r.get("description", ""),
            deep_analyzed=r.get("deep_analyzed", False),
        )
        for r in repos
    ]

    ranked, video_signals = merge_streams(github_issues, exa_results, video_exa_results, vision)

    summary = ResearchSummary(
        vision=vision,
        repos=repo_results,
        pitfall_candidates=ranked,
        video_signals=video_signals,
        duration_seconds=time.time() - start,
    )
    summary.research_quality = compute_quality(summary)
    summary.floor_met = check_floor(summary)[0]

    if project_root:
        save_to_vault(summary, project_root)

    return summary
