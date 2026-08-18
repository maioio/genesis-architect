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
    from_web_result,
    from_video_signal,
    rank,
    format_ranked,
)
from genesis_architect_pro.video_research import (
    parse_exa_results,
    format_media_signals,
)
from genesis_architect_pro.research_outline import Outline


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
    video_signals: list = field(default_factory=list)   # MediaSignal list
    ecosystem_notes: list[str] = field(default_factory=list)
    research_quality: str = "THIN"   # FULL | PARTIAL | THIN
    floor_met: bool = False
    duration_seconds: float = 0.0
    from_vault: bool = False
    domain: str = ""   # code | non_code | "" = classify from the vision
    outline: Outline | None = None
    item_findings: dict[str, dict[str, str]] = field(default_factory=dict)
    # None = no outline was used, not "0% covered" - same discipline as
    # RepoResult.stars: an absent metric must never render as a real zero.
    coverage: float | None = None
    # "item:field" entries not confidently known - see is_uncertain(). A
    # value literally equal to "[uncertain]" is uncertain too, without
    # needing an entry here; this list exists for callers that keep the
    # marker and the value apart (Phase 2's own per-item JSON does both).
    uncertain: list[str] = field(default_factory=list)

    def quality_reason(self) -> str:
        deep = sum(1 for r in self.repos if r.deep_analyzed)
        issues = len(self.pitfall_candidates)
        if deep >= 8 and issues >= 5:
            return f"FULL ({deep} repos deep-analyzed, {issues} issues)"
        if deep >= 5 or issues >= 2:
            return f"PARTIAL ({deep} repos deep-analyzed, {issues} issues)"
        return f"THIN ({deep} repos deep-analyzed, {issues} issues)"

    def to_dict(self) -> dict:
        """Machine-readable form, for `--json` consumers.

        Agents read this CLI far more often than humans do, and parsing Rich
        output is guesswork. Everything the rendered summary shows is here,
        including the floor verdict and each candidate's score breakdown.
        """
        floor_ok, floor_msg = check_floor(self)
        return {
            "vision": self.vision,
            "domain": self.domain or classify_domain(self.vision),
            "research_quality": self.research_quality,
            "quality_reason": self.quality_reason(),
            "floor_met": floor_ok,
            "floor_message": floor_msg,
            "from_vault": self.from_vault,
            "duration_seconds": round(self.duration_seconds, 3),
            "repos": [r.__dict__ for r in self.repos],
            "pitfall_candidates": [p.__dict__ for p in self.pitfall_candidates],
            "media_signals": [
                s.__dict__ if hasattr(s, "__dict__") else s for s in self.video_signals
            ],
            "ecosystem_notes": self.ecosystem_notes,
            "outline": self.outline.__dict__ if self.outline else None,
            "item_findings": self.item_findings,
            "coverage": self.coverage,
            "uncertain": self.uncertain,
        }


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
        summary.domain = data.get("domain", "")
        summary.from_vault = True
        pitfalls_raw = data.get("pitfall_candidates", [])
        summary.pitfall_candidates = [RankedPitfall(**p) for p in pitfalls_raw]
        outline_raw = data.get("outline")
        summary.outline = Outline(**outline_raw) if outline_raw else None
        summary.item_findings = data.get("item_findings", {})
        summary.coverage = data.get("coverage")
        summary.uncertain = data.get("uncertain", [])
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
        "domain": summary.domain,
        "outline": summary.outline.__dict__ if summary.outline else None,
        "item_findings": summary.item_findings,
        "coverage": summary.coverage,
        "uncertain": summary.uncertain,
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


def compute_coverage(summary: ResearchSummary) -> float | None:
    """Fields filled / fields defined, across the outline's items x fields grid.

    None when there is nothing to measure against - no outline, or an
    outline with no items or no fields - rather than 0.0, which would read
    as "measured and found empty" instead of "not applicable here".

    Coverage counts presence, not confidence: a field marked [uncertain] by
    the caller still counts as filled, because completeness (did we look?)
    and confidence (do we trust what we found?) are different questions -
    the second is what R3's `uncertain` list is for, not this one.
    Only items and fields the outline actually declares are counted, so a
    stray entry in item_findings can't inflate coverage past what was asked.
    """
    outline = summary.outline
    if outline is None or not outline.items or not outline.fields:
        return None

    total = len(outline.items) * len(outline.fields)
    filled = 0
    for item in outline.items:
        values = summary.item_findings.get(item, {})
        for f in outline.fields:
            value = values.get(f)
            if isinstance(value, str) and value.strip():
                filled += 1

    return filled / total


def is_uncertain(summary: ResearchSummary, item: str, field_name: str) -> bool:
    """True if this cell of the grid is flagged unconfident, by either
    mechanism the source pack uses: the value itself literally reads
    "[uncertain]", or the "item:field" pair is named in summary.uncertain.
    """
    value = summary.item_findings.get(item, {}).get(field_name)
    if isinstance(value, str) and value.strip() == "[uncertain]":
        return True
    return f"{item}:{field_name}" in summary.uncertain


# ---------------------------------------------------------------------------
# Research floor gate
# ---------------------------------------------------------------------------

FLOOR_MIN_REPOS = 12
FLOOR_MIN_DEEP = 5

# Non-code domains have no GitHub corpus to meet a repo floor against. The gate
# still has to hold - it is the one thing that stops Genesis from presenting
# thin research as if it were sufficient - so for these the *unit* changes to
# authoritative sources while the gate itself stays exactly as strict.
FLOOR_MIN_SOURCES = 8
FLOOR_MIN_AUTHORITATIVE = 3

# An outline states the target before gathering, so once one is in use the
# floor no longer needs to guess a domain-specific unit (repos vs sources) -
# coverage against the declared grid replaces both. Stricter than the gate's
# own 0.50 pause-and-ask threshold in gde_gate_engine.py: the floor decides
# whether to show results at all, the gate decides whether to pause first.
FLOOR_MIN_COVERAGE = 0.70

# Signals that the vision is about software someone publishes as a repo.
_CODE_DOMAIN_SIGNALS = (
    "api", "cli", "sdk", "library", "framework", "app", "application", "service",
    "server", "backend", "frontend", "database", "compiler", "parser", "plugin",
    "extension", "package", "microservice", "webhook", "daemon", "bot",
    "dashboard", "pipeline", "scraper", "crawler", "runtime", "kernel", "driver",
    "container", "kubernetes", "docker", "terraform", "react", "python",
    "typescript", "rust", "golang", "build", "deploy", "refactor", "migrate",
)

# Signals that the answer lives in standards, archives, and practice - not repos.
_NON_CODE_DOMAIN_SIGNALS = (
    "standard", "guideline", "guidelines", "convention", "conventions",
    "brand", "branding", "identity", "typography", "editorial", "archive",
    "studio", "portfolio", "curriculum", "syllabus", "policy", "regulation",
    "compliance", "legal", "contract", "workflow", "process", "methodology",
    "taxonomy", "glossary", "style guide", "specification document",
    "onboarding", "hiring", "pricing", "positioning", "market", "audience",
)


def classify_domain(vision: str) -> str:
    """``code`` | ``non_code`` - which floor unit applies to this vision.

    Deliberately keyword-based and biased toward ``code``: mis-routing a
    software vision to the source floor would weaken the gate that matters
    most, while mis-routing a non-software vision merely restores the old
    behaviour. Ties resolve to ``code``.
    """
    text = f" {vision.lower()} "
    code_hits = sum(1 for kw in _CODE_DOMAIN_SIGNALS if f" {kw} " in text or f" {kw}s " in text)
    non_code_hits = sum(
        1 for kw in _NON_CODE_DOMAIN_SIGNALS if f" {kw} " in text or f" {kw}s " in text
    )
    return "non_code" if non_code_hits > code_hits else "code"


def _source_hosts(summary: ResearchSummary) -> set[str]:
    """Every distinct host behind the candidates, corroborating URLs included.

    Deduplication folds repeat findings into ``corroborated_by`` and ranking
    caps the visible list, so counting candidates would undercount the sources
    actually consulted - the exact mistake that makes a source floor unfair.
    """
    from genesis_architect.core.urls import host_of

    hosts: set[str] = set()
    for p in summary.pitfall_candidates:
        for url in [p.url, *p.corroborated_by]:
            host = host_of(url) if url else ""
            if host:
                hosts.add(host)
    return hosts


def _authoritative_source_count(summary: ResearchSummary) -> int:
    """Distinct hosts that are official or high-signal community, not just any host."""
    from genesis_architect_pro.pitfall_ranker import _authority_tier

    return sum(
        1 for host in _source_hosts(summary)
        if _authority_tier(f"https://{host}/") in ("official", "community")
    )


def check_floor(summary: ResearchSummary) -> tuple[bool, str]:
    """
    Returns (passed, message).
    Phase 5 prerequisite gate - must pass before showing architecture choice.

    The gate never disappears; only its unit adapts to what is actually
    available to measure against. When an outline was used, coverage against
    its declared grid IS the floor - domain-agnostic, since the grid already
    states exactly what "enough" means for this research, without needing to
    guess a unit from a code/non-code split. Without an outline, the gate
    falls back to counting: repos for a software vision, because that is
    where the evidence is; authoritative sources for a vision with no repo
    corpus (extracting a house standard from a studio archive, say), where
    counting repos would measure the wrong thing entirely and report failure
    for a problem that was never repo-shaped, at equivalent strictness.
    """
    coverage = compute_coverage(summary)
    if coverage is not None:
        if coverage >= FLOOR_MIN_COVERAGE:
            return True, (
                f"Floor met: {coverage:.0%} coverage on the outline grid "
                f"({FLOOR_MIN_COVERAGE:.0%} required, outline-driven)"
            )
        return False, (
            f"Floor not met: {coverage:.0%}/{FLOOR_MIN_COVERAGE:.0%} coverage "
            f"on the outline grid. Options: A) Fill in more of the grid  "
            f"B) Accept thin research (--override)  C) Architect Mode"
        )

    domain = summary.domain or classify_domain(summary.vision)

    if domain == "non_code":
        sources = len(_source_hosts(summary))
        authoritative = _authoritative_source_count(summary)
        if sources >= FLOOR_MIN_SOURCES and authoritative >= FLOOR_MIN_AUTHORITATIVE:
            return True, (
                f"Floor met: {sources} sources, {authoritative} authoritative hosts "
                f"(non-code domain - repos are not the unit here)"
            )
        return False, (
            f"Floor not met: {sources}/{FLOOR_MIN_SOURCES} sources, "
            f"{authoritative}/{FLOOR_MIN_AUTHORITATIVE} authoritative hosts. "
            f"This vision has no repo corpus, so the floor counts sources, not repos. "
            f"Options: A) Broaden to more authoritative sources  "
            f"B) Accept thin research (--override)  C) Architect Mode"
        )

    total = len(summary.repos)
    deep = sum(1 for r in summary.repos if r.deep_analyzed)
    if total >= FLOOR_MIN_REPOS and deep >= FLOOR_MIN_DEEP:
        return True, f"Floor met: {total} repos, {deep} deep-analyzed"
    return False, (
        f"Floor not met: {total}/{FLOOR_MIN_REPOS} repos, {deep}/{FLOOR_MIN_DEEP} deep-analyzed. "
        f"Options: A) Broaden search  B) Accept thin research (--override)  "
        f"C) Architect Mode  D) Not a repo-shaped problem - rerun with "
        f"--domain non-code to have the floor count authoritative sources instead"
    )


# ---------------------------------------------------------------------------
# Stream merging
# ---------------------------------------------------------------------------

def merge_streams(
    github_issues: list,          # list of issue_miner.Issue objects
    web_results: list[dict],      # stream B: web/ecosystem results, any provider
    media_results: list[dict],    # stream D: video/social results, any provider
    vision: str,
) -> tuple[list[RankedPitfall], list]:
    """
    Convert all stream outputs to RankedPitfall, rank them.
    Returns (ranked_pitfalls, media_signals).

    The stream parameters are named for what they carry, not for who fetched
    it: stream B runs on Exa, Tavily or Firecrawl interchangeably, and naming
    the field after one provider makes the stored JSON claim a provenance it
    does not have. Each item may carry its own ``provider`` field instead.
    """
    candidates: list[RankedPitfall] = []

    # Stream C: GitHub issues
    for issue in github_issues:
        candidates.append(from_github_issue(issue))

    # Stream B: web ecosystem results
    for result in web_results:
        candidates.append(from_web_result(result))

    # Stream D: media signals -> pitfall candidates
    media_signals = parse_exa_results(media_results, vision)
    for signal in media_signals:
        if signal.signal_type in ("lessons_learned", "architecture_talk"):
            candidates.append(from_video_signal(signal))

    ranked = rank(candidates, top_n=10)
    return ranked, media_signals


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
    if (summary.domain or classify_domain(summary.vision)) == "non_code":
        lines.append(
            "_Non-code domain: the research floor counts authoritative sources, "
            "not repositories._"
        )
    lines.append("")

    # Research grid (outline-driven): uncertain cells are skipped, not
    # printed - the same discipline as never coercing an unreported star
    # count to look like a confirmed 0.
    outline = summary.outline
    if outline and outline.items and outline.fields:
        grid_lines = []
        for item in outline.items:
            values = summary.item_findings.get(item, {})
            rows = [
                f"  - {f}: {values[f]}"
                for f in outline.fields
                if isinstance(values.get(f), str) and values[f].strip()
                and not is_uncertain(summary, item, f)
            ]
            if rows:
                grid_lines.append(f"- **{item}**")
                grid_lines.extend(rows)
        if grid_lines:
            lines.append("### Research Grid")
            lines.extend(grid_lines)
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

    # Media signals, followed by the command that brings the result back.
    # Stream D hands out /watch commands; without naming the return leg here,
    # the loop looks one-way and the watched talk never re-enters the research.
    if summary.video_signals:
        lines.append(format_media_signals(summary.video_signals))
        lines.append(
            f"After running a `/watch` command above, feed its analysis back in:\n"
            f'    genesis research "{summary.vision}" --absorb watch-output.txt\n'
        )

    # Floor status
    floor_ok, floor_msg = check_floor(summary)
    if not floor_ok:
        lines.append(f"\n**{floor_msg}**")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shim helpers (for use when full MCP results are passed in as dicts)
# ---------------------------------------------------------------------------

STREAM_ALIASES = {
    "exa_results": "web_results",
    "video_exa_results": "media_results",
}


def normalize_streams(raw: dict) -> dict:
    """Map legacy provider-named stream keys onto the canonical names.

    Data collected before the rename still loads unchanged; if a payload
    carries both spellings, the canonical key wins and the alias is appended
    rather than dropped.
    """
    out = dict(raw)
    for legacy, canonical in STREAM_ALIASES.items():
        if legacy not in out:
            continue
        legacy_items = out.pop(legacy) or []
        existing = out.get(canonical) or []
        out[canonical] = list(existing) + list(legacy_items)
    return out


def build_summary_from_raw(
    vision: str,
    repos: list[dict],
    github_issues: list,
    web_results: list[dict] | None = None,
    media_results: list[dict] | None = None,
    project_root: Path | None = None,
    domain: str = "",
    *,
    exa_results: list[dict] | None = None,        # legacy alias for web_results
    video_exa_results: list[dict] | None = None,  # legacy alias for media_results
    outline: Outline | None = None,
    item_findings: dict[str, dict[str, str]] | None = None,
) -> ResearchSummary:
    """
    Build a ResearchSummary from raw data collected by Genesis during Phase 2.
    Call this after all streams complete to get the ranked, merged view.
    """
    start = time.time()

    web_results = list(web_results or []) + list(exa_results or [])
    media_results = list(media_results or []) + list(video_exa_results or [])

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

    ranked, media_signals = merge_streams(github_issues, web_results, media_results, vision)

    summary = ResearchSummary(
        vision=vision,
        repos=repo_results,
        pitfall_candidates=ranked,
        video_signals=media_signals,
        duration_seconds=time.time() - start,
        domain=domain or classify_domain(vision),
        outline=outline,
        item_findings=item_findings or {},
    )
    summary.research_quality = compute_quality(summary)
    summary.floor_met = check_floor(summary)[0]
    summary.coverage = compute_coverage(summary)

    if project_root:
        save_to_vault(summary, project_root)

    return summary
