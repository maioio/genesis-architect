"""Committee engine — core types.

All dataclasses and enums for the Committee engine. No logic here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CommitteeMode(str, Enum):
    ARCHITECTURE = "architecture"
    RESEARCH = "research"
    GATE = "gate"
    RECOVERY = "recovery"
    GENERAL = "general"


class Urgency(str, Enum):
    BLOCKING = "blocking"
    HIGH = "high"
    NORMAL = "normal"
    BACKGROUND = "background"


class TransparencyProfile(str, Enum):
    FREE = "free"
    PRO = "pro"


class ConsensusType(str, Enum):
    EARNED = "earned"
    MANUFACTURED = "manufactured"
    SPLIT = "split"
    DIVERGENT = "divergent"


class CollapseType(str, Enum):
    EARNED = "earned"
    MANUFACTURED = "manufactured"


@dataclass
class CommitteeContext:
    """Evidence and project state passed to the Committee."""
    evidence: str = ""
    prior_decisions: list[str] = field(default_factory=list)
    engine_outputs: dict[str, str] = field(default_factory=dict)
    project_path: str = ""


@dataclass
class CommitteeRequest:
    question: str
    context: CommitteeContext
    mode: CommitteeMode = CommitteeMode.GENERAL
    urgency: Urgency = Urgency.NORMAL
    transparency: TransparencyProfile = TransparencyProfile.PRO
    max_rounds: int = 2


@dataclass
class AdvisorPosition:
    advisor: str
    stance: str
    confidence: float
    reasoning: str
    what_would_change_it: str = ""
    # Set during peer review:
    agreement: float = 0.5


@dataclass
class PeerReview:
    reviewer: str
    target_advisor: str
    agreement: float
    critique: str
    revised_stance: str | None = None


@dataclass
class VotingRecord:
    for_: int = 0
    against: int = 0
    abstain: int = 0

    @property
    def total(self) -> int:
        return self.for_ + self.against + self.abstain


@dataclass
class CommitteeResult:
    verdict: str
    confidence: float
    consensus_type: ConsensusType
    rounds_run: int = 1
    # PRO-only fields — None when transparency == FREE
    advisor_positions: list[AdvisorPosition] | None = None
    peer_review_round: list[PeerReview] | None = None
    divergence_map: dict[str, float] | None = None
    voting_record: VotingRecord | None = None
    minority_view: str | None = None
    manufactured_warning: str | None = None
