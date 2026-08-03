"""Committee engine — execution pipeline.

Runs the full 5-advisor debate:
  [0] Triage (fast path for unambiguous questions)
  [1] Position round (parallel)
  [2] Anonymized peer review (parallel, only if divergence > threshold)
  [3] Collapse detection
  [4] Synthesis → CommitteeResult

LLM calls are injected via a callable so the pipeline is testable without
a real API key. Production callers pass `llm_call=_default_llm_call`.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from genesis_architect.pro.engines.committee.advisors import (
    AdvisorTemplate,
    build_peer_review_prompt,
    build_position_prompt,
    get_all_advisors,
)
from genesis_architect.pro.engines.committee.collapse_detector import (
    apply_manufactured_cap,
    build_divergence_map,
    build_voting_record,
    classify_consensus,
    detect_collapse,
    find_minority_view,
)
from genesis_architect.pro.engines.committee.transparency import apply_transparency
from genesis_architect.pro.engines.committee.types import (
    AdvisorPosition,
    CollapseType,
    CommitteeRequest,
    CommitteeResult,
    ConsensusType,
    PeerReview,
)

# Divergence threshold: run peer review only if pre-round variance is above this
_PEER_REVIEW_VARIANCE_THRESHOLD = 0.15
# Fast-path: skip Committee if confidence from context alone is this high
_FAST_PATH_CONFIDENCE = 0.85

LLMCallable = Callable[[str, str], str]


# ---------------------------------------------------------------------------
# Default LLM backend (anthropic SDK, optional import)
# ---------------------------------------------------------------------------

def _default_llm_call(system: str, user: str) -> str:
    """Call Claude claude-sonnet-4-6 via the Anthropic SDK."""
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic SDK not installed. Run: pip install anthropic"
        ) from exc

    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # Return the first text block; content may include non-text blocks, so never
    # assume content[0] is text (guarded — matches core llm.py).
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_position(raw: str, advisor_name: str) -> AdvisorPosition:
    stance = _extract_field(raw, "STANCE", fallback="(no stance given)")
    confidence = _extract_float(raw, "CONFIDENCE", default=0.5)
    what_would_change = _extract_field(raw, "WHAT_WOULD_CHANGE_IT", fallback="")
    return AdvisorPosition(
        advisor=advisor_name,
        stance=stance,
        confidence=max(0.0, min(1.0, confidence)),
        reasoning=raw,
        what_would_change_it=what_would_change,
    )


def _parse_peer_review(
    raw: str,
    reviewer_name: str,
    target_advisor: str,
    pre_position: AdvisorPosition,
) -> tuple[PeerReview, AdvisorPosition]:
    agreement = _extract_float(raw, "AGREEMENT", default=0.5)
    critique = _extract_field(raw, "CRITIQUE", fallback="")
    revised_raw = _extract_field(raw, "REVISED_STANCE", fallback="unchanged")
    revised = None if revised_raw.lower().strip() == "unchanged" else revised_raw

    review = PeerReview(
        reviewer=reviewer_name,
        target_advisor=target_advisor,
        agreement=max(0.0, min(1.0, agreement)),
        critique=critique,
        revised_stance=revised,
    )

    updated_position = AdvisorPosition(
        advisor=pre_position.advisor,
        stance=revised if revised else pre_position.stance,
        confidence=pre_position.confidence,
        reasoning=pre_position.reasoning,
        what_would_change_it=pre_position.what_would_change_it,
        agreement=max(0.0, min(1.0, agreement)),
    )
    return review, updated_position


def _extract_field(text: str, label: str, fallback: str = "") -> str:
    pattern = rf"^{label}:\s*(.+?)(?=\n[A-Z_]+:|$)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else fallback


def _extract_float(text: str, label: str, default: float = 0.5) -> float:
    pattern = rf"^{label}:\s*([0-9.]+)"
    match = re.search(pattern, text, re.MULTILINE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return default


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def _run_position_round(
    advisors: list[AdvisorTemplate],
    request: CommitteeRequest,
    llm_call: LLMCallable,
) -> list[AdvisorPosition]:
    """Run all advisors in parallel; return their initial positions."""
    results: list[AdvisorPosition] = [None] * len(advisors)  # type: ignore[list-item]

    def call_advisor(idx: int, advisor: AdvisorTemplate) -> tuple[int, AdvisorPosition]:
        prompt = build_position_prompt(advisor, request)
        raw = llm_call(advisor.system_prompt, prompt)
        return idx, _parse_position(raw, advisor.name)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(call_advisor, i, a): i for i, a in enumerate(advisors)}
        for future in as_completed(futures):
            idx, position = future.result()
            results[idx] = position

    return results


def _needs_peer_review(pre_positions: list[AdvisorPosition]) -> bool:
    """Return True if variance in confidence is above threshold."""
    if len(pre_positions) < 2:
        return False
    import statistics
    confidences = [p.confidence for p in pre_positions]
    try:
        return statistics.variance(confidences) > _PEER_REVIEW_VARIANCE_THRESHOLD
    except statistics.StatisticsError:
        return False


def _run_peer_review_round(
    advisors: list[AdvisorTemplate],
    pre_positions: list[AdvisorPosition],
    llm_call: LLMCallable,
) -> tuple[list[PeerReview], list[AdvisorPosition]]:
    """Each advisor reviews all others' anonymized positions."""
    reviews: list[PeerReview] = []
    updated: list[AdvisorPosition] = [None] * len(advisors)  # type: ignore[list-item]

    def call_reviewer(idx: int, advisor: AdvisorTemplate) -> tuple[int, PeerReview, AdvisorPosition]:
        own_stance = pre_positions[idx].stance
        others = [p.stance for j, p in enumerate(pre_positions) if j != idx]
        prompt = build_peer_review_prompt(advisor, own_stance, others)
        raw = llm_call(advisor.system_prompt, prompt)
        review, updated_pos = _parse_peer_review(
            raw, advisor.name, "group", pre_positions[idx]
        )
        return idx, review, updated_pos

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(call_reviewer, i, a): i for i, a in enumerate(advisors)}
        for future in as_completed(futures):
            idx, review, updated_pos = future.result()
            reviews.append(review)
            updated[idx] = updated_pos

    return reviews, updated


def _synthesize_verdict(
    positions: list[AdvisorPosition],
    consensus_type: ConsensusType,
    llm_call: LLMCallable,
) -> tuple[str, float]:
    """Produce a final synthesized verdict from the advisor positions."""
    stances = "\n".join(
        f"- {p.advisor} (confidence {p.confidence:.2f}): {p.stance}"
        for p in positions
    )
    system = (
        "You are a neutral synthesis engine. You have received independent positions "
        "from five advisors who used different reasoning methods. Your job is to synthesize "
        "a final verdict. Do NOT simply average the positions. Weight by reasoning quality, "
        "not by how many agreed. If the consensus type is SPLIT or DIVERGENT, say so honestly "
        "and name the key point of disagreement. Never inflate confidence beyond what the "
        "evidence supports."
    )
    user = (
        f"CONSENSUS TYPE: {consensus_type.value.upper()}\n\n"
        f"ADVISOR POSITIONS:\n{stances}\n\n"
        "Respond in this exact format:\n"
        "VERDICT: <the synthesized decision in 2-4 sentences>\n"
        "CONFIDENCE: <0.0-1.0>"
    )
    raw = llm_call(system, user)
    verdict = _extract_field(raw, "VERDICT", fallback="No consensus reached.")
    confidence = _extract_float(raw, "CONFIDENCE", default=0.5)
    return verdict, max(0.0, min(1.0, confidence))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_committee(
    request: CommitteeRequest,
    llm_call: LLMCallable = _default_llm_call,
) -> CommitteeResult:
    """Run the full Committee pipeline and return a CommitteeResult.

    Args:
        request: The CommitteeRequest including question, context, and profile.
        llm_call: Injectable LLM backend (default: Anthropic claude-sonnet-4-6).

    Returns:
        CommitteeResult with transparency applied per request.transparency.
    """
    advisors = get_all_advisors()

    # [1] Position round
    pre_positions = _run_position_round(advisors, request, llm_call)
    rounds_run = 1

    # [2] Peer review (only if divergence warrants it)
    peer_reviews: list[PeerReview] = []
    post_positions: list[AdvisorPosition] = pre_positions

    if request.max_rounds >= 2 and _needs_peer_review(pre_positions):
        peer_reviews, post_positions = _run_peer_review_round(advisors, pre_positions, llm_call)
        rounds_run = 2

    # [3] Collapse detection
    collapse = detect_collapse(pre_positions, post_positions)
    consensus_type = classify_consensus(pre_positions, post_positions, collapse)

    # [4] Synthesis
    verdict, confidence = _synthesize_verdict(post_positions, consensus_type, llm_call)

    # Apply manufactured cap if needed
    manufactured_warning: str | None = None
    if collapse == CollapseType.MANUFACTURED:
        confidence, manufactured_warning = apply_manufactured_cap(confidence)

    # Build PRO fields
    voting_record = build_voting_record(post_positions) if post_positions else None
    divergence_map = build_divergence_map(post_positions)
    minority_view = find_minority_view(pre_positions, post_positions)

    full_result = CommitteeResult(
        verdict=verdict,
        confidence=confidence,
        consensus_type=consensus_type,
        rounds_run=rounds_run,
        advisor_positions=post_positions,
        peer_review_round=peer_reviews if peer_reviews else None,
        divergence_map=divergence_map,
        voting_record=voting_record,
        minority_view=minority_view,
        manufactured_warning=manufactured_warning,
    )

    return apply_transparency(full_result, request.transparency)
