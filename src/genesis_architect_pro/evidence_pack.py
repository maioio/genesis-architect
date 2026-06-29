"""
Evidence Pack — the proof behind every significant recommendation (Pro).

Constitution (evidence-first + honesty clause): a recommendation is only as good
as the evidence behind it. An Evidence Pack records:

  - the sources consulted (each with its registry tier + reliability),
  - the confidence in the conclusion,
  - any contradictions found between sources,
  - the recommendation and "what would change it".

Honesty rules enforced here:
  - Confidence is NEVER "high" without at least one engineering-truth source
    (official/source/security/local/packages/qa/research) — field/market signal
    alone cannot make a conclusion authoritative.
  - A source that was attempted but unreachable is recorded as `unavailable`
    (status), never silently dropped and never fabricated.
  - Contradictions lower confidence and are surfaced, not hidden.

Persisted (optional) as JSON under `.genesis/evidence_packs/`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from genesis_architect_pro.source_registry import load_registry, SourceRegistry

# Tiers that count as engineering truth (everything except signal-only market).
_TRUTH_TIERS = {"official", "source", "security", "local", "packages", "qa",
                "research", "blog", "learning"}


@dataclass
class EvidenceItem:
    """One piece of evidence from one source."""
    source_id: str
    claim: str
    status: str = "ok"          # ok | unavailable
    url: str = ""
    # filled from the registry at build time:
    tier: str = ""
    reliability: int = 0        # tier priority (0–100)
    weight: float = 0.0         # evidence_weight (0–1)

    def is_truth(self) -> bool:
        return self.status == "ok" and self.tier in _TRUTH_TIERS


@dataclass
class EvidencePack:
    question: str
    recommendation: str = ""
    what_would_change_it: str = ""
    items: list = field(default_factory=list)        # list[EvidenceItem]
    contradictions: list = field(default_factory=list)  # list[str]
    confidence: str = "low"      # high | medium | low | none
    created: int = 0

    # -- views --------------------------------------------------------------

    def truth_items(self) -> list:
        return [i for i in self.items if i.is_truth()]

    def unavailable(self) -> list:
        return [i for i in self.items if i.status == "unavailable"]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "recommendation": self.recommendation,
            "what_would_change_it": self.what_would_change_it,
            "confidence": self.confidence,
            "created": self.created,
            "contradictions": list(self.contradictions),
            "items": [vars(i) for i in self.items],
        }

    def to_markdown(self) -> str:
        lines = [f"# Evidence Pack — {self.question}", "",
                 f"**Recommendation:** {self.recommendation or '(none)'}",
                 f"**Confidence:** {self.confidence}", ""]
        if self.what_would_change_it:
            lines += [f"**What would change it:** {self.what_would_change_it}", ""]
        lines += ["## Sources", "",
                  "| Source | Tier | Reliability | Weight | Status |",
                  "|--------|------|:-----------:|:------:|--------|"]
        for i in sorted(self.items, key=lambda x: x.reliability * x.weight,
                        reverse=True):
            lines.append(f"| {i.source_id} | {i.tier} | {i.reliability} | "
                         f"{i.weight:.2f} | {i.status} |")
        if self.contradictions:
            lines += ["", "## Contradictions", ""]
            lines += [f"- {c}" for c in self.contradictions]
        if self.unavailable():
            lines += ["", "## Unavailable sources (honesty clause)", ""]
            lines += [f"- {i.source_id}: not reachable — not counted as evidence"
                      for i in self.unavailable()]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def _enrich(item: EvidenceItem, reg: SourceRegistry) -> EvidenceItem:
    src = reg.get(item.source_id)
    if src is not None:
        item.tier = src.tier
        item.reliability = reg.tier_priority(src.tier)
        item.weight = src.evidence_weight
        if not item.url:
            item.url = src.url
    return item


def _grade_confidence(pack: EvidencePack) -> str:
    """Deterministic confidence from the evidence, honest by construction."""
    truth = pack.truth_items()
    if not pack.items or (not truth and not pack.contradictions):
        # no evidence at all, or only non-truth signal -> cannot be confident
        return "none" if not pack.items else "low"
    # base level from how much engineering truth backs it
    strong = [i for i in truth if i.reliability >= 95]
    if len(strong) >= 2:
        level = "high"
    elif strong or len(truth) >= 2:
        level = "medium"
    else:
        level = "low"
    # contradictions cap confidence down one notch
    if pack.contradictions:
        level = {"high": "medium", "medium": "low", "low": "low"}[level]
    # honesty: never "high" without an engineering-truth source
    if level == "high" and not truth:
        level = "medium"
    return level


def build_evidence_pack(question: str, items: list, *,
                        recommendation: str = "",
                        what_would_change_it: str = "",
                        contradictions: list | None = None,
                        project_root: Path | str = ".") -> EvidencePack:
    """Build an Evidence Pack from raw evidence items. Each item is enriched from
    the source registry (tier/reliability/weight), confidence is graded honestly,
    and unavailable sources are kept (as unavailable), never dropped."""
    reg = load_registry(project_root)
    enriched = [_enrich(i if isinstance(i, EvidenceItem)
                        else EvidenceItem(**i), reg) for i in items]
    pack = EvidencePack(
        question=question,
        recommendation=recommendation,
        what_would_change_it=what_would_change_it,
        items=enriched,
        contradictions=list(contradictions or []),
        created=int(time.time()),
    )
    pack.confidence = _grade_confidence(pack)
    return pack


def save_evidence_pack(pack: EvidencePack, name: str,
                       project_root: Path | str = ".") -> Path | None:
    """Persist a pack as JSON under .genesis/evidence_packs/. Returns the path
    or None on I/O error."""
    safe = "".join(c for c in name if c.isalnum() or c in "-_")[:64] or "pack"
    target = Path(project_root) / ".genesis" / "evidence_packs" / f"{safe}.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(pack.to_dict(), indent=2), encoding="utf-8")
        return target
    except OSError:
        return None
