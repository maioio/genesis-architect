"""Orchestrator + Lifecycle state machine. Drives a SessionContext through
INTAKE -> PLAN -> EXECUTE -> GATE -> REPORT -> APPROVE -> COMMIT, consulting the
registry, decision engine, and approval gates.

P1 = infrastructure: the state machine advances phases and invokes registered
engines through the Engine contract. It executes whatever engines are
registered; in P1 no real engines are registered by default, so it runs as a
safe no-op skeleton. Real engine adapters register in P2+.
"""

from __future__ import annotations

from genesis_architect_pro.governance.types import (
    LifecyclePhase, GateDecision, EngineResult, SessionContext,
)
from genesis_architect_pro.governance.registry import EngineRegistry
from genesis_architect_pro.governance.gates import ApprovalGate
from genesis_architect_pro.governance.decision import DecisionEngine


class LifecycleStateMachine:
    """Deterministic phase advancer. Enforces the fixed phase order; a phase may
    be skipped only with a recorded reason."""

    def __init__(self) -> None:
        self._order = LifecyclePhase.order()

    def next_phase(self, current: LifecyclePhase) -> LifecyclePhase | None:
        idx = self._order.index(current)
        return self._order[idx + 1] if idx + 1 < len(self._order) else None

    def is_terminal(self, phase: LifecyclePhase) -> bool:
        return phase is self._order[-1]


class Orchestrator:
    """The governance brain (foundation). Routes a task through the lifecycle,
    invoking registered engines per phase and gating dangerous/first-build
    actions. Modular: it knows engines only through the registry + Engine
    contract, never by concrete type."""

    def __init__(self, registry: EngineRegistry | None = None,
                 gate: ApprovalGate | None = None,
                 decision_engine: DecisionEngine | None = None) -> None:
        self.registry = registry or EngineRegistry()
        self.gate = gate or ApprovalGate()
        self.decision = decision_engine or DecisionEngine()
        self.sm = LifecycleStateMachine()

    def _run_engines_for_phase(self, ctx: SessionContext) -> None:
        for spec in self.registry.for_phase(ctx.phase.value):
            engine = spec.engine
            try:
                if hasattr(engine, "available") and not engine.available():
                    ctx.add_result(EngineResult(
                        engine=spec.name, ok=False,
                        error="engine unavailable in this environment"))
                    continue
                result = engine.run(ctx)
            except Exception as exc:  # contract says engines shouldn't raise;
                # if one does, we degrade gracefully (honesty clause).
                result = EngineResult(engine=spec.name, ok=False, error=str(exc))
            ctx.add_result(result)

    def run(self, ctx: SessionContext, *, first_build: bool = False) -> SessionContext:
        """Advance the full lifecycle. Returns the populated SessionContext.

        Gates: before EXECUTE and before COMMIT the orchestrator consults the
        approval gate. A BLOCK stops the lifecycle at that phase (recorded).
        """
        ctx.phase = LifecyclePhase.INTAKE
        ctx.record(f"phase -> {ctx.phase.value}")

        while True:
            # Gate the two consequential transitions.
            if ctx.phase is LifecyclePhase.EXECUTE:
                dangerous = any(
                    s.dangerous for s in self.registry.for_phase(ctx.phase.value))
                if self.gate.check("execute", ctx, dangerous=dangerous,
                                   first_build=first_build) is GateDecision.BLOCK:
                    ctx.record("blocked at EXECUTE (approval denied)")
                    break
                self._run_engines_for_phase(ctx)
            elif ctx.phase is LifecyclePhase.COMMIT:
                if self.gate.check("commit", ctx,
                                   first_build=first_build) is GateDecision.BLOCK:
                    ctx.record("blocked at COMMIT (approval denied)")
                    break
                self._run_engines_for_phase(ctx)
                ctx.record("committed")
                break
            else:
                self._run_engines_for_phase(ctx)

            nxt = self.sm.next_phase(ctx.phase)
            if nxt is None:
                break
            ctx.phase = nxt
            ctx.record(f"phase -> {ctx.phase.value}")

        return ctx
