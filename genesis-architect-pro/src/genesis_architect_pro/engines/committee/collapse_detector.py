"""Committee engine — collapse / anti-sycophancy detector.

Detects whether post-review consensus is EARNED (emerged organically)
or MANUFACTURED (advisors converged after seeing each other's positions,
suggesting social pressure rather than genuine agreement).

Based on: Zhang et al. 2025, Cambridge MAD 2026.
"""

from __future__ import annotations

import statistics

from genesis_architect_pro.engines.committee.types import (
    AdvisorPosition,
    CollapseType,
    ConsensusType,
    VotingRecord,
)

_MANUFACTURED_VARIANCE_RATIO = 0.3
_MANUFACTURED_AGREEMENT_THRESHOLD = 0.85
_HIGH_VARIANCE_THRESHOLD = 0.2
_SPLIT_MAJORITY = 3
_DIVERGENT_MAX_AGREEMENT = 0.4
_MANUFACTURED_CONFIDENCE_CAP = 0.65


def detect_collapse(
    pre_positions: list[AdvisorPosition],
    post_positions: list[AdvisorPosition],
) -> CollapseType:
    """Determine if post-review convergence is earned or manufactured.

    Args:
        pre_positions: Advisor positions from round 1 (before peer review).
        post_positions: Advisor positions from round 2 (after seeing peers).

    Returns:
        CollapseType.MANUFACTURED if consensus appears socially pressured.
        CollapseType.EARNED otherwise.
    """
    if len(pre_positions) < 2 or len(post_positions) < 2:
        return CollapseType.EARNED

    pre_confidences = [p.confidence for p in pre_positions]
    post_agreements = [p.agreement for p in post_positions]

    pre_variance = _safe_variance(pre_confidences)
    post_agreement_mean = statistics.mean(post_agreements)

    # Heuristic 1: variance collapsed dramatically after peer review
    if len(post_positions) >= 2:
        post_confidences = [p.confidence for p in post_positions]
        post_variance = _safe_variance(post_confidences)
        if pre_variance > 0 and post_variance < pre_variance * _MANUFACTURED_VARIANCE_RATIO:
            return CollapseType.MANUFACTURED

    # Heuristic 2: high post-review agreement despite high pre-review variance
    if (
        post_agreement_mean > _MANUFACTURED_AGREEMENT_THRESHOLD
        and pre_variance > _HIGH_VARIANCE_THRESHOLD
    ):
        return CollapseType.MANUFACTURED

    return CollapseType.EARNED


def classify_consensus(
    pre_positions: list[AdvisorPosition],
    post_positions: list[AdvisorPosition],
    collapse: CollapseType,
) -> ConsensusType:
    """Map collapse type + position distribution to a ConsensusType."""
    if collapse == CollapseType.MANUFACTURED:
        return ConsensusType.MANUFACTURED

    # Use post-review positions if available, otherwise pre
    positions = post_positions if post_positions else pre_positions
    agreements = [p.agreement for p in positions]
    mean_agreement = statistics.mean(agreements) if agreements else 0.5

    if mean_agreement < _DIVERGENT_MAX_AGREEMENT:
        return ConsensusType.DIVERGENT

    # Count advisors "for" the majority stance via agreement threshold
    for_count = sum(1 for a in agreements if a >= 0.6)
    against_count = len(agreements) - for_count

    if for_count >= _SPLIT_MAJORITY:
        return ConsensusType.EARNED
    if against_count >= _SPLIT_MAJORITY:
        return ConsensusType.DIVERGENT
    return ConsensusType.SPLIT


def build_voting_record(post_positions: list[AdvisorPosition]) -> VotingRecord:
    """Build a VotingRecord from post-review advisor agreements."""
    record = VotingRecord()
    for p in post_positions:
        if p.agreement >= 0.65:
            record.for_ += 1
        elif p.agreement <= 0.35:
            record.against += 1
        else:
            record.abstain += 1
    return record


def build_divergence_map(positions: list[AdvisorPosition]) -> dict[str, float]:
    """Return {advisor_name: confidence} from the given positions."""
    return {p.advisor: p.confidence for p in positions}


def apply_manufactured_cap(confidence: float) -> tuple[float, str]:
    """Cap confidence and return warning if it exceeds the manufactured ceiling."""
    if confidence > _MANUFACTURED_CONFIDENCE_CAP:
        return (
            _MANUFACTURED_CONFIDENCE_CAP,
            (
                f"Confidence capped at {_MANUFACTURED_CONFIDENCE_CAP:.0%}: "
                "post-review convergence appears manufactured (advisors agreed "
                "after seeing each other's positions, not before)."
            ),
        )
    return confidence, ""


def find_minority_view(
    pre_positions: list[AdvisorPosition],
    post_positions: list[AdvisorPosition],
) -> str | None:
    """Return the strongest dissenting view, if any."""
    positions = post_positions if post_positions else pre_positions
    if not positions:
        return None

    # Dissenter = lowest agreement with the group
    dissenter = min(positions, key=lambda p: p.agreement)
    if dissenter.agreement > 0.5:
        return None  # no meaningful minority

    if dissenter.stance:
        return f"{dissenter.advisor}: {dissenter.stance}"
    return None


def _safe_variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.variance(values)
