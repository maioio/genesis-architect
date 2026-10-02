"""Engine interface contracts. Future engines implement Engine and register a
spec; the orchestrator/decision engine work against these contracts only - never
against concrete engine classes. This is what keeps the system modular."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from genesis_architect_pro.governance.types import EngineResult, SessionContext


@runtime_checkable
class Engine(Protocol):
    """Contract every governed engine must satisfy.

    P1 defines the contract only. Existing engines are NOT modified to implement
    it now; adapters will wrap them in P2+ without changing their code.
    """

    name: str

    def available(self) -> bool:
        """True if this engine can run in the current environment (read-only)."""
        ...

    def run(self, ctx: SessionContext) -> EngineResult:
        """Do the engine's work for this session. Must never raise - failures
        return EngineResult(ok=False, error=...)."""
        ...


@dataclass
class EngineSpec:
    """Registration metadata for an engine. The orchestrator selects engines by
    phase + tier from these specs - it does not hardcode engine names."""
    name: str
    engine: object               # an Engine implementation (duck-typed)
    phases: list[str] = field(default_factory=list)   # LifecyclePhase.value list
    tier: str = "pro"            # "free" | "pro"
    description: str = ""
    dangerous: bool = False      # if True, actions require a hard approval gate
