"""
Developer Field Intelligence — Reddit Answers + field workflow (Pro).

Field intelligence is what practitioners actually hit: failures, workarounds, and
"is it worth it" verdicts that official docs never tell you. This module builds
the **Reddit Answers research workflow** and the verification rule that keeps
field findings honest.

Binding rule (Constitution / research engine): Reddit and YouTube are high-value
field intelligence, but **not final technical truth**. Every important field
claim must be verified against stronger engineering-truth sources (official docs,
source code, GitHub issues, releases, security DBs) before it influences a
recommendation.

This module is the query/workflow layer — it does NOT fetch the network itself
(routing is handled elsewhere per the tool rules). It produces the queries to
run, classifies findings, and enforces verification status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from genesis_architect.pro.source_registry import load_registry

# The developer-style query templates Reddit Answers is searched with.
# `{tool}` / `{alt}` are filled per request.
REDDIT_ANSWERS_TEMPLATES = (
    "{tool} problems",
    "{tool} not working",
    "{tool} production issues",
    "{tool} vs {alt}",
    "{tool} worth it",
    "{tool} migration",
    "{tool} setup",
    "{tool} bugs",
)

# Engineering-truth tiers a field claim is verified against.
_VERIFY_AGAINST = ("official", "source", "security")


def build_reddit_answers_queries(tool: str, alternative: str = "") -> list[str]:
    """Build the developer-style Reddit Answers queries for a tool. Templates
    that need an alternative are included only when one is supplied."""
    tool = (tool or "").strip()
    if not tool:
        return []
    alt = (alternative or "").strip()
    queries: list[str] = []
    for tmpl in REDDIT_ANSWERS_TEMPLATES:
        if "{alt}" in tmpl:
            if not alt:
                continue
            queries.append(tmpl.format(tool=tool, alt=alt))
        else:
            queries.append(tmpl.format(tool=tool))
    return queries


@dataclass
class FieldFinding:
    """One pain point / workaround / verdict extracted from the field."""
    claim: str
    source_id: str = "reddit_answers"   # which registry source it came from
    url: str = ""
    sentiment: str = "neutral"          # positive | negative | neutral
    verified: bool = False              # confirmed against engineering truth?
    verified_by: list = field(default_factory=list)   # source ids that confirm
    contradicted_by: list = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.contradicted_by:
            return "contradicted"
        if self.verified:
            return "verified"
        return "unverified"


@dataclass
class FieldReport:
    tool: str
    queries: list = field(default_factory=list)
    findings: list = field(default_factory=list)   # list[FieldFinding]

    def verified(self) -> list:
        return [f for f in self.findings if f.status == "verified"]

    def unverified(self) -> list:
        return [f for f in self.findings if f.status == "unverified"]

    def contradicted(self) -> list:
        return [f for f in self.findings if f.status == "contradicted"]

    def summary(self) -> str:
        return (f"Field report for '{self.tool}': {len(self.findings)} findings "
                f"({len(self.verified())} verified, "
                f"{len(self.unverified())} unverified, "
                f"{len(self.contradicted())} contradicted). "
                f"Unverified field claims are NOT engineering truth.")


def verify_finding(finding: FieldFinding, *,
                   confirming_sources: list | None = None,
                   contradicting_sources: list | None = None,
                   project_root: Path | str = ".") -> FieldFinding:
    """Apply the verification rule: a field finding becomes 'verified' only when
    confirmed by an engineering-truth source (official/source/security). Sources
    from non-truth tiers (e.g. market/field) do NOT count as verification.

    Returns the same finding, mutated with verification status.
    """
    reg = load_registry(project_root)

    def truth_only(ids: list | None) -> list:
        out = []
        for sid in (ids or []):
            s = reg.get(sid)
            if s is not None and s.tier in _VERIFY_AGAINST:
                out.append(sid)
        return out

    finding.verified_by = truth_only(confirming_sources)
    finding.contradicted_by = truth_only(contradicting_sources)
    finding.verified = bool(finding.verified_by) and not finding.contradicted_by
    return finding


def run_field_workflow(tool: str, alternative: str = "") -> FieldReport:
    """Produce the Reddit Answers query plan for a tool. Findings are added by
    the caller after the queries are executed (routing/fetch is external), then
    each is passed through verify_finding before it influences a decision."""
    return FieldReport(tool=tool,
                       queries=build_reddit_answers_queries(tool, alternative),
                       findings=[])
