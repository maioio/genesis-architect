"""Approval Gate framework. Maps actions to gate decisions per the autonomy
ladder + dangerous-action rule (Constitution 12). P1: the framework + policy;
actual prompting is the adapter's job (UI-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass

from genesis_architect_pro.governance.types import (
    AutonomyLevel, GateDecision, SessionContext,
)


@dataclass
class GatePolicy:
    """Decides whether an action passes, blocks, or needs approval.

    Rule (binding): dangerous actions ALWAYS need approval, at every autonomy
    level including AUTONOMOUS. Routine actions soften as autonomy rises.
    """

    def evaluate(self, *, dangerous: bool, first_build: bool,
                 autonomy: AutonomyLevel) -> GateDecision:
        # Dangerous actions hard-stop regardless of autonomy.
        if dangerous:
            return GateDecision.NEEDS_APPROVAL
        # First build of a project is a hard gate (Constitution 04/12).
        if first_build:
            return (GateDecision.PASS if autonomy == AutonomyLevel.AUTONOMOUS
                    else GateDecision.NEEDS_APPROVAL)
        # Routine work: gated at GUIDED, otherwise proceeds.
        if autonomy == AutonomyLevel.GUIDED:
            return GateDecision.NEEDS_APPROVAL
        return GateDecision.PASS


class ApprovalGate:
    """A gate instance the orchestrator consults before acting. The actual
    user prompt is delegated to an `approver` callable supplied by the adapter
    (Claude Code: AskUserQuestion; desktop: dialog). P1 default approver denies,
    so nothing dangerous can pass unattended in tests/headless use."""

    def __init__(self, policy: GatePolicy | None = None, approver=None) -> None:
        self.policy = policy or GatePolicy()
        # approver: (action: str, ctx) -> bool. Default: deny (safe).
        self._approver = approver or (lambda action, ctx: False)

    def check(self, action: str, ctx: SessionContext, *,
              dangerous: bool = False, first_build: bool = False) -> GateDecision:
        decision = self.policy.evaluate(
            dangerous=dangerous, first_build=first_build, autonomy=ctx.autonomy,
        )
        ctx.record(f"gate[{action}] -> {decision.value}")
        if decision is GateDecision.NEEDS_APPROVAL:
            granted = bool(self._approver(action, ctx))
            return GateDecision.PASS if granted else GateDecision.BLOCK
        return decision
