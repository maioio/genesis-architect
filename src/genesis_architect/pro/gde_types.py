"""Genesis Decision Engine — core types.

All dataclasses, enums, and type aliases used by the GDE.
No engine logic lives here. Import from this module only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class GDEMode(str, Enum):
    """Execution modes the GDE can operate in."""

    RECOVERY = "recovery"
    RESEARCH = "research"
    REFACTOR = "refactor"
    GATE = "gate"
    BUILD = "build"
    DOCUMENT = "document"
    COMMITTEE = "committee"


class LifecycleStage(str, Enum):
    """Named stages of a single GDE session."""

    IDLE = "idle"
    INTAKE = "intake"
    PLAN = "plan"
    EXECUTE = "execute"
    GATE = "gate"
    REPORT = "report"
    APPROVE = "approve"
    COMMIT = "commit"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    ROLLBACK = "rollback"


class EngineCategory(str, Enum):
    """Broad behavioural category of a registered engine."""

    ANALYSIS = "analysis"       # pure read, returns structured data
    PERSISTENCE = "persistence" # reads and/or writes disk state
    REPORT = "report"           # formats structured data, no disk access
    RESEARCH = "research"       # calls external sources (APIs, web)
    GATE = "gate"               # evaluates policy, returns pass/warn/fail
    MEMORY = "memory"           # reads/writes .genesis/ session state


class EngineStatus(str, Enum):
    """Outcome of a single engine execution."""

    SUCCESS = "success"
    DEGRADED = "degraded"   # ran but with reduced confidence
    FAILED = "failed"       # raised or timed out
    SKIPPED = "skipped"     # dependency failed; could not run


class GateAction(str, Enum):
    """What the gate engine does when a condition fires."""

    PASS = "pass"               # no action required
    WARN = "warn"               # surface to user, continue
    BLOCK_AND_ASK = "block_ask" # surface to user, wait for approval
    HARD_BLOCK = "hard_block"   # halt unconditionally


class GateOutcome(str, Enum):
    """Aggregate outcome of the full gate evaluation pass."""

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    HARD_BLOCK = "hard_block"


class ApprovalChoice(str, Enum):
    """User's response to an approval request."""

    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Engine descriptor
# ---------------------------------------------------------------------------


@dataclass
class EngineDescriptor:
    """Metadata that fully describes one engine to the GDE.

    All engines are registered via this descriptor. The GDE uses it to
    discover engines, resolve execution order, enforce isolation, and
    collect write-operation declarations for approval gating.

    `requires` and `handoffs` are the two edges of the engine graph and mean
    different things:

      requires  — BACKWARD edge, a hard ordering constraint. The planner
                  topologically sorts on it, and it must stay acyclic.
      handoffs  — FORWARD edge, advisory. "Having run, this is what is most
                  useful next." It is deliberately NOT part of cycle
                  detection: an iterative loop (analyse → decide → re-analyse)
                  is a legitimate workflow, not a structural defect. Handoff
                  targets are existence-checked so they cannot rot into
                  dangling references, and nothing more.
    """

    id: str
    name: str
    module: str
    entry_point: str
    category: EngineCategory
    input_keys: list[str]
    output_keys: list[str]
    requires: list[str] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)
    # Known ways this engine misleads when it goes wrong. Declared next to the
    # engine rather than centrally, so the constraint sits with the thing it
    # constrains. Surfaced when the engine fails or degrades, which is exactly
    # when an operator is deciding whether a bad result is a known mode or a
    # new problem.
    failure_modes: list[str] = field(default_factory=list)
    is_optional: bool = True
    write_operations: list[str] = field(default_factory=list)
    timeout_seconds: int = 60
    modes: list[GDEMode] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("EngineDescriptor.id must not be empty")
        if not self.name or not self.name.strip():
            raise ValueError("EngineDescriptor.name must not be empty")
        if not self.module or not self.module.strip():
            raise ValueError("EngineDescriptor.module must not be empty")
        if not self.entry_point or not self.entry_point.strip():
            raise ValueError("EngineDescriptor.entry_point must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("EngineDescriptor.timeout_seconds must be > 0")
        if not isinstance(self.category, EngineCategory):
            raise TypeError(f"category must be EngineCategory, got {type(self.category)}")


# ---------------------------------------------------------------------------
# Engine result
# ---------------------------------------------------------------------------


@dataclass
class EngineResult:
    """Output produced by a single engine execution."""

    engine_id: str
    status: EngineStatus
    output: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")


# ---------------------------------------------------------------------------
# Write operation
# ---------------------------------------------------------------------------


@dataclass
class WriteOperation:
    """A disk write that requires approval before execution."""

    engine_id: str
    operation_id: str       # unique within the session
    description: str        # human-readable: what will be written
    target_path: str        # relative path under project_dir
    is_reversible: bool = True
    payload: Any = None     # the data to write; engine-specific


# ---------------------------------------------------------------------------
# Gate types
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    """Outcome of one gate condition evaluation."""

    gate_id: str
    action: GateAction
    override_allowed: bool
    title: str
    reason: str
    detail: str = ""
    confidence_penalty: float = 0.0
    # Companion instrumentation — ISO 8601 timestamps
    presented_at: str = ""    # when gate fired and was surfaced to user
    responded_at: str = ""    # when user approved/rejected/overrode


@dataclass
class GateReport:
    """Aggregate result of all gate evaluations for a session."""

    passed: list[GateResult] = field(default_factory=list)
    warnings: list[GateResult] = field(default_factory=list)
    blocks: list[GateResult] = field(default_factory=list)
    hard_blocks: list[GateResult] = field(default_factory=list)
    overall: GateOutcome = GateOutcome.PASS

    def recompute_overall(self) -> None:
        if self.hard_blocks:
            self.overall = GateOutcome.HARD_BLOCK
        elif self.blocks:
            self.overall = GateOutcome.BLOCK
        elif self.warnings:
            self.overall = GateOutcome.WARN
        else:
            self.overall = GateOutcome.PASS


# ---------------------------------------------------------------------------
# Approval types
# ---------------------------------------------------------------------------


@dataclass
class ApprovalRequest:
    """What is presented to the user before write operations execute."""

    session_id: str
    pending_writes: list[WriteOperation]
    gate_report: GateReport
    overall_confidence: float
    summary: str


@dataclass
class ApprovalDecision:
    """The user's response to an approval request."""

    session_id: str
    choice: ApprovalChoice
    approved_operation_ids: list[str] = field(default_factory=list)
    reason: str = ""


# ---------------------------------------------------------------------------
# Commit result
# ---------------------------------------------------------------------------


@dataclass
class CommitResult:
    """Result of executing approved write operations."""

    session_id: str
    committed: list[str] = field(default_factory=list)      # operation_ids
    rolled_back: list[str] = field(default_factory=list)    # operation_ids
    errors: list[str] = field(default_factory=list)
    success: bool = True


# ---------------------------------------------------------------------------
# Decision log
# ---------------------------------------------------------------------------


@dataclass
class DecisionEntry:
    """One immutable entry in the GDE decision log."""

    session_id: str
    timestamp: str          # ISO 8601
    stage: LifecycleStage
    decision_type: str      # ENGINE_INVOKED | ENGINE_FAILED | GATE_FIRED | etc.
    actor: str              # "gde" | "user" | engine_id
    subject: str
    detail: str
    confidence_before: float
    confidence_after: float
    outcome: str


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------


@dataclass
class Intent:
    """Classified user intent, produced by the intent classifier (Step 2)."""

    raw_text: str
    mode: GDEMode
    confidence: float
    signals: list[str] = field(default_factory=list)
    clarifying_questions: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Execution plan
# ---------------------------------------------------------------------------


@dataclass
class ExecutionPlan:
    """Ordered execution plan produced by the planner (Step 3).

    `phases` is a list of parallel groups. Each outer entry is one sequential
    phase; engines within an inner list may run concurrently.
    """

    mode: GDEMode
    phases: list[list[EngineDescriptor]] = field(default_factory=list)
    required_gate_ids: list[str] = field(default_factory=list)
    estimated_duration_seconds: int = 0
    write_operations_pending: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Session context
# ---------------------------------------------------------------------------


@dataclass
class SessionContext:
    """The single shared data structure that flows through a GDE session.

    Built at INTAKE; extended during EXECUTE. Append-only for engine outputs.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mode: GDEMode = GDEMode.RECOVERY
    stage: LifecycleStage = LifecycleStage.IDLE
    project_dir: Path = field(default_factory=lambda: Path("."))
    # Companion instrumentation
    session_started_at: str = ""   # ISO 8601, set at INTAKE
    last_user_interaction_at: str = ""  # ISO 8601, updated on any user action

    # Project state — populated at INTAKE
    import_graph: dict[str, Any] = field(default_factory=dict)
    model_state: dict[str, Any] = field(default_factory=dict)
    session_memory: dict[str, Any] = field(default_factory=dict)

    # Intent — set after classification (Step 2)
    intent: Intent | None = None

    # Accumulated engine outputs — grows during EXECUTE
    engine_results: dict[str, EngineResult] = field(default_factory=dict)

    # Derived aggregates — computed after EXECUTE
    overall_confidence: float = 1.0
    project_risk_level: str = "none"
    pending_write_operations: list[WriteOperation] = field(default_factory=list)

    # Decision log — append-only throughout the session
    decision_log: list[DecisionEntry] = field(default_factory=list)

    def record(self, entry: DecisionEntry) -> None:
        """Append one entry to the decision log."""
        self.decision_log.append(entry)

    def apply_confidence_penalty(self, delta: float) -> None:
        """Subtract delta from overall_confidence, clamped to [0.10, 1.00]."""
        self.overall_confidence = max(0.10, min(1.00, self.overall_confidence - delta))

    def merge_engine_result(self, result: EngineResult) -> None:
        """Store result and merge its output keys into engine_results."""
        self.engine_results[result.engine_id] = result


# ---------------------------------------------------------------------------
# Session report (top-level output of a GDE session)
# ---------------------------------------------------------------------------


@dataclass
class SessionReport:
    """The final output of a completed GDE session."""

    session_id: str
    mode: GDEMode
    stage: LifecycleStage
    project_risk_level: str
    overall_confidence: float
    gate_report: GateReport
    engine_results: dict[str, EngineResult]
    decision_log: list[DecisionEntry]
    approval_decision: ApprovalDecision | None = None
    commit_result: CommitResult | None = None
    warnings: list[str] = field(default_factory=list)
