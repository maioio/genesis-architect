"""
Genesis PRO - Governance Foundation (P1).

Orchestration infrastructure ONLY. This subpackage is fully additive: it does
not import or modify any existing engine, the free core, or any public API.
Engines register themselves through the EngineRegistry; the Orchestrator drives
the Thinking Loop lifecycle and consults the Decision Engine + Approval Gates.

Nothing here executes real engine work yet (that is P2+). This phase defines the
types, contracts, state machine, and skeletons so future engines can plug in
without changing the orchestrator or the decision engine.
"""

from genesis_architect_pro.governance.types import (
    LifecyclePhase,
    AutonomyLevel,
    GateDecision,
    EngineResult,
    SessionContext,
)
from genesis_architect_pro.governance.contracts import Engine, EngineSpec
from genesis_architect_pro.governance.registry import EngineRegistry
from genesis_architect_pro.governance.gates import ApprovalGate, GatePolicy
from genesis_architect_pro.governance.decision import DecisionEngine, Decision, Alternative
from genesis_architect_pro.governance.orchestrator import Orchestrator, LifecycleStateMachine

__all__ = [
    "LifecyclePhase", "AutonomyLevel", "GateDecision", "EngineResult", "SessionContext",
    "Engine", "EngineSpec", "EngineRegistry",
    "ApprovalGate", "GatePolicy",
    "DecisionEngine", "Decision", "Alternative",
    "Orchestrator", "LifecycleStateMachine",
]
