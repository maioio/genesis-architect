"""Decision Engine skeleton. Turns alternatives + evidence into a recommendation
with confidence and "what would change it" (Constitution 06). P1 = skeleton:
the data model + a deterministic scorer. Committee execution and real Evidence
Pack wiring are P2+ (explicitly out of P1 scope)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Alternative:
    name: str
    summary: str = ""
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    # weight (0..1) the caller may set from evidence reliability; default neutral.
    score: float = 0.0


@dataclass
class Decision:
    question: str
    alternatives: list[Alternative]
    choice: str | None = None
    confidence: str = "low"            # high | medium | low
    rationale: str = ""
    what_would_change_it: str = ""
    needs_committee: bool = False
    journaled: bool = False


class DecisionEngine:
    """Skeleton decision-maker. Deterministic: scores alternatives by
    (#pros - #cons - #risks) plus any caller-supplied score, recommends the top
    one, and flags when stakes are close enough to warrant a committee.

    Modular: it never imports concrete engines. Callers pass Alternatives built
    from whatever evidence source - so new engines feed it without changing it.
    """

    def __init__(self, committee_margin: float = 1.0) -> None:
        self.committee_margin = committee_margin

    def _score(self, alt: Alternative) -> float:
        return alt.score + len(alt.pros) - len(alt.cons) - len(alt.risks)

    def decide(self, question: str, alternatives: list[Alternative]) -> Decision:
        if not alternatives:
            return Decision(question=question, alternatives=[],
                            confidence="low",
                            rationale="No alternatives supplied; cannot decide.",
                            what_would_change_it="Provide at least one alternative.")

        ranked = sorted(alternatives, key=self._score, reverse=True)
        top = ranked[0]
        runner = ranked[1] if len(ranked) > 1 else None

        # Confidence from separation between top and runner-up.
        if runner is None:
            confidence = "medium"
            close = False
        else:
            gap = self._score(top) - self._score(runner)
            close = gap < self.committee_margin
            confidence = "high" if gap >= 2 else ("medium" if gap >= 1 else "low")

        evidence_n = len(top.evidence_refs)
        # Honesty: confidence cannot be high without supporting evidence.
        if confidence == "high" and evidence_n == 0:
            confidence = "medium"

        return Decision(
            question=question,
            alternatives=ranked,
            choice=top.name,
            confidence=confidence,
            rationale=f"'{top.name}' ranks highest "
                      f"({len(top.pros)} pros, {len(top.cons)} cons, "
                      f"{len(top.risks)} risks; {evidence_n} evidence refs).",
            what_would_change_it=(
                f"Stronger evidence for '{runner.name}'" if runner
                else "A competing alternative with better trade-offs"),
            needs_committee=close and len(ranked) > 1,
        )
