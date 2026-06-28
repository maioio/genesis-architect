"""Governance core types. Pure data; no engine imports, no side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LifecyclePhase(Enum):
    """The orchestration lifecycle (a focused projection of the 15-step
    Thinking Loop for P1 infrastructure)."""
    INTAKE = "intake"
    PLAN = "plan"
    EXECUTE = "execute"
    GATE = "gate"
    REPORT = "report"
    APPROVE = "approve"
    COMMIT = "commit"

    @classmethod
    def order(cls) -> list["LifecyclePhase"]:
        return [cls.INTAKE, cls.PLAN, cls.EXECUTE, cls.GATE,
                cls.REPORT, cls.APPROVE, cls.COMMIT]


class AutonomyLevel(Enum):
    """Progressive autonomy ladder (Constitution 12)."""
    GUIDED = 0      # ask before each major step
    ASSISTED = 1    # ask on decisions + dangerous actions
    TRUSTED = 2     # proceed on routine; report; ask on risk
    AUTONOMOUS = 3  # work independently; still hard-stop on dangerous actions


class GateDecision(Enum):
    PASS = "pass"
    BLOCK = "block"
    NEEDS_APPROVAL = "needs_approval"


@dataclass
class EngineResult:
    """Normalized result every engine returns to the orchestrator.

    `ok=False` with a populated `error` is how engines fail gracefully - the
    orchestrator never sees a raw exception (honesty clause: report, do not hide).
    """
    engine: str
    ok: bool = True
    data: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class SessionContext:
    """Carries state across the lifecycle for one task. Additive: holds only
    governance state; does not wrap or replace any existing session object."""
    task: str = ""
    project_dir: str = "."
    autonomy: AutonomyLevel = AutonomyLevel.GUIDED
    phase: LifecyclePhase = LifecyclePhase.INTAKE
    results: dict[str, EngineResult] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)        # phase transitions
    metadata: dict[str, Any] = field(default_factory=dict)

    def record(self, message: str) -> None:
        self.history.append(message)

    def add_result(self, result: EngineResult) -> None:
        self.results[result.engine] = result
