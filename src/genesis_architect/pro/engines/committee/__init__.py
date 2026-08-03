"""Genesis Committee Engine — core primitive for GDE.

Exposes:
  run_committee(request, llm_call=...) -> CommitteeResult
  CommitteeRequest, CommitteeResult, CommitteeContext (re-exported for callers)
"""

from genesis_architect.pro.engines.committee.pipeline import run_committee
from genesis_architect.pro.engines.committee.types import (
    CommitteeContext,
    CommitteeMode,
    CommitteeRequest,
    CommitteeResult,
    ConsensusType,
    TransparencyProfile,
    Urgency,
)

__all__ = [
    "run_committee",
    "CommitteeRequest",
    "CommitteeResult",
    "CommitteeContext",
    "CommitteeMode",
    "ConsensusType",
    "TransparencyProfile",
    "Urgency",
]
