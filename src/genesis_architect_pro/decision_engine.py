"""Genesis Decision Engine — main entry point.

Public API:
    GenesisDecisionEngine  — the orchestrator class
    run_session()          — convenience function

Usage::

    from genesis_architect_pro import GenesisDecisionEngine

    gde = GenesisDecisionEngine(project_dir=Path("."))
    report = gde.run("diagnose the project and identify drift")

The GDE is stateless between calls. Each call to run() creates a fresh
SessionContext (or resumes a saved one if resume=True).
"""

from __future__ import annotations

from pathlib import Path

from genesis_architect_pro.engine_registry import EngineRegistry, get_default_registry
from genesis_architect_pro.gde_gate_engine import evaluate_gates
from genesis_architect_pro.gde_planner import build_plan
from genesis_architect_pro.gde_runner import run_plan
from genesis_architect_pro.gde_session import (
    append_decision_log,
    load_session,
    save_session,
)
from genesis_architect_pro.gde_types import (
    ApprovalDecision,
    DecisionEntry,
    GDEMode,
    Intent,
    LifecycleStage,
    SessionContext,
    SessionReport,
)
from genesis_architect_pro.intent_classifier import classify


class GenesisDecisionEngine:
    """Central orchestrator for all GDE sessions.

    Args:
        project_dir: Root directory of the project being analysed.
        registry: Engine registry to use. Defaults to the module-level registry.
        parallel: Whether to run engines within a phase concurrently.
    """

    def __init__(
        self,
        project_dir: Path | str = ".",
        registry: EngineRegistry | None = None,
        parallel: bool = True,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.registry = registry if registry is not None else get_default_registry()
        self.parallel = parallel

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        user_input: str,
        resume: bool = False,
    ) -> SessionReport:
        """Run a full GDE session for the given user input.

        Lifecycle:
            INTAKE  → classify intent
            PLAN    → build execution plan
            EXECUTE → run engines
            GATE    → evaluate gates
            REPORT  → build session report
            APPROVE → (deferred — caller inspects report.gate_report)
            COMMIT  → (deferred — caller calls commit() with ApprovalDecision)

        Args:
            user_input: Free-text instruction from the user.
            resume: If True, attempt to load a saved session from project_dir.

        Returns:
            SessionReport with all results, gate report, and decision log.
        """
        # INTAKE
        ctx = self._intake(user_input, resume)

        # PLAN
        ctx.stage = LifecycleStage.PLAN
        intent = ctx.intent
        assert intent is not None
        plan = build_plan(intent, registry=self.registry)
        self._log(ctx, "PLAN_BUILT", "gde", f"mode={intent.mode.value}", f"{len(plan.phases)} phases")

        # EXECUTE
        run_plan(plan, ctx, parallel=self.parallel)

        # GATE
        ctx.stage = LifecycleStage.GATE
        gate_report = evaluate_gates(ctx, plan.required_gate_ids)
        self._log(ctx, "GATE_EVALUATED", "gde", "gate_engine", gate_report.overall.value)

        # REPORT
        ctx.stage = LifecycleStage.REPORT
        report = SessionReport(
            session_id=ctx.session_id,
            mode=ctx.mode,
            stage=ctx.stage,
            project_risk_level=ctx.project_risk_level,
            overall_confidence=ctx.overall_confidence,
            gate_report=gate_report,
            engine_results=dict(ctx.engine_results),
            decision_log=list(ctx.decision_log),
        )

        # Persist session and decision log
        save_session(ctx, self.project_dir)
        for entry in ctx.decision_log:
            append_decision_log(entry, self.project_dir)

        return report

    def classify_intent(self, user_input: str) -> Intent:
        """Classify user input without running a full session."""
        return classify(user_input)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _intake(self, user_input: str, resume: bool) -> SessionContext:
        """Build or resume a SessionContext and classify intent."""
        if resume:
            saved = load_session(self.project_dir)
            if saved is not None:
                saved.stage = LifecycleStage.INTAKE
                return saved

        intent = classify(user_input)
        ctx = SessionContext(
            mode=intent.mode,
            stage=LifecycleStage.INTAKE,
            project_dir=self.project_dir,
            intent=intent,
        )
        self._log(
            ctx,
            "INTENT_CLASSIFIED",
            "gde",
            f"mode={intent.mode.value}",
            f"confidence={intent.confidence:.2f}",
        )
        return ctx

    def _log(
        self,
        ctx: SessionContext,
        decision_type: str,
        actor: str,
        subject: str,
        outcome: str,
    ) -> None:
        from datetime import datetime, timezone

        entry = DecisionEntry(
            session_id=ctx.session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage=ctx.stage,
            decision_type=decision_type,
            actor=actor,
            subject=subject,
            detail="",
            confidence_before=ctx.overall_confidence,
            confidence_after=ctx.overall_confidence,
            outcome=outcome,
        )
        ctx.record(entry)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def run_session(
    user_input: str,
    project_dir: Path | str = ".",
    registry: EngineRegistry | None = None,
    parallel: bool = True,
    resume: bool = False,
) -> SessionReport:
    """Convenience wrapper: create a GDE and run one session.

    Args:
        user_input: Free-text instruction from the user.
        project_dir: Root of the project.
        registry: Engine registry. Defaults to module-level registry.
        parallel: Whether to run engines in a phase concurrently.
        resume: Whether to attempt resuming a saved session.

    Returns:
        SessionReport.
    """
    gde = GenesisDecisionEngine(
        project_dir=project_dir,
        registry=registry,
        parallel=parallel,
    )
    return gde.run(user_input, resume=resume)
