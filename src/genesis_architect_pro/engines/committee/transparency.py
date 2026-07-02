"""Committee engine — Transparency Profile enforcement.

The Committee engine runs identically in FREE and PRO tiers.
This module strips PRO-only fields from CommitteeResult for FREE users.
"""

from __future__ import annotations

from genesis_architect_pro.engines.committee.types import (
    CommitteeResult,
    TransparencyProfile,
)


def apply_transparency(result: CommitteeResult, profile: TransparencyProfile) -> CommitteeResult:
    """Return a CommitteeResult appropriate for the given transparency profile.

    FREE: verdict, confidence, consensus_type, rounds_run only.
    PRO:  all fields populated.

    The result is a new dataclass instance — the original is never mutated.
    """
    if profile == TransparencyProfile.PRO:
        return result

    # FREE: return a copy with PRO-only fields nulled out
    return CommitteeResult(
        verdict=result.verdict,
        confidence=result.confidence,
        consensus_type=result.consensus_type,
        rounds_run=result.rounds_run,
        advisor_positions=None,
        peer_review_round=None,
        divergence_map=None,
        voting_record=None,
        minority_view=None,
        manufactured_warning=None,
    )
