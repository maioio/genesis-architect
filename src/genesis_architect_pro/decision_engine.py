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
    ApprovalChoice,
    ApprovalDecision,
    ApprovalRequest,
    CommitResult,
    DecisionEntry,
    GDEMode,
    Intent,
    LifecycleStage,
    SessionContext,
    SessionReport,
    WriteOperation,
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

    def approve(self, report: SessionReport) -> ApprovalRequest:
        """Build an ApprovalRequest from a completed session report.

        The caller inspects the request and decides which write operations
        to approve, then calls commit() with an ApprovalDecision.

        APPROVE stage fires only when the gate outcome is not HARD_BLOCK.
        If there are no pending write operations, returns an empty request
        (the subsequent commit() call will be a no-op).

        Args:
            report: The SessionReport returned by run().

        Returns:
            ApprovalRequest summarising pending writes and gate status.

        Raises:
            RuntimeError: If the session has a HARD_BLOCK gate — commit would
                be rejected anyway, so callers should not reach APPROVE.
        """
        from genesis_architect_pro.gde_types import GateOutcome

        if report.gate_report.overall == GateOutcome.HARD_BLOCK:
            hard = [g.gate_id for g in report.gate_report.hard_blocks]
            raise RuntimeError(
                f"Cannot approve: session has HARD_BLOCK gate(s): {hard}. "
                "These are non-overridable. The session must be discarded."
            )

        ctx = load_session(self.project_dir)
        pending = ctx.pending_write_operations if ctx else []

        gate_summary = report.gate_report.overall.value
        write_summary = (
            f"{len(pending)} write operation(s) pending"
            if pending
            else "No write operations pending"
        )
        summary = (
            f"Session {report.session_id[:8]}… | "
            f"mode={report.mode.value} | "
            f"confidence={report.overall_confidence:.2f} | "
            f"gate={gate_summary} | "
            f"{write_summary}"
        )

        return ApprovalRequest(
            session_id=report.session_id,
            pending_writes=list(pending),
            gate_report=report.gate_report,
            overall_confidence=report.overall_confidence,
            summary=summary,
        )

    def commit(
        self,
        report: SessionReport,
        decision: ApprovalDecision,
    ) -> CommitResult:
        """Execute approved write operations atomically.

        COMMIT stage:
        - APPROVE choice: executes all approved_operation_ids from pending_writes
        - REJECT choice: discards all writes, clears session
        - DEFER choice: does nothing, leaves session file intact for later
        - PARTIAL choice: executes only operation_ids listed in decision.approved_operation_ids

        Hard-blocked gates cannot be overridden: commit() will return a failed
        CommitResult rather than executing writes.

        Args:
            report: The SessionReport returned by run().
            decision: The user's ApprovalDecision.

        Returns:
            CommitResult with lists of committed and rolled-back operation_ids.
        """
        import json
        from genesis_architect_pro.gde_types import GateOutcome

        result = CommitResult(session_id=decision.session_id)

        # Hard blocks are unconditional — never execute
        if report.gate_report.overall == GateOutcome.HARD_BLOCK:
            hard = [g.gate_id for g in report.gate_report.hard_blocks]
            result.errors.append(f"HARD_BLOCK gates present: {hard}. No writes executed.")
            result.success = False
            return result

        # REJECT or DEFER — no writes
        if decision.choice == ApprovalChoice.REJECT:
            ctx = load_session(self.project_dir)
            if ctx:
                ctx.pending_write_operations.clear()
                save_session(ctx, self.project_dir)
            result.success = True
            return result

        if decision.choice == ApprovalChoice.DEFER:
            result.success = True
            return result

        # APPROVE or PARTIAL — execute writes
        ctx = load_session(self.project_dir)
        pending: list[WriteOperation] = ctx.pending_write_operations if ctx else []

        if decision.choice == ApprovalChoice.APPROVE:
            to_commit = pending
        else:  # PARTIAL
            approved_ids = set(decision.approved_operation_ids)
            to_commit = [op for op in pending if op.operation_id in approved_ids]
            not_approved = [op for op in pending if op.operation_id not in approved_ids]
            result.rolled_back.extend(op.operation_id for op in not_approved)

        for op in to_commit:
            try:
                self._execute_write_operation(op)
                result.committed.append(op.operation_id)
            except Exception as exc:
                result.errors.append(f"{op.operation_id}: {exc}")
                result.rolled_back.append(op.operation_id)

        # Log commit decision
        if ctx:
            ctx.stage = LifecycleStage.COMMIT
            self._log(
                ctx,
                "COMMIT_EXECUTED",
                "user",
                f"choice={decision.choice.value}",
                f"committed={len(result.committed)} rolled_back={len(result.rolled_back)}",
            )
            ctx.pending_write_operations.clear()
            save_session(ctx, self.project_dir)
            for entry in ctx.decision_log[-1:]:
                append_decision_log(entry, self.project_dir)

        result.success = not result.errors
        return result

    def _execute_write_operation(self, op: WriteOperation) -> None:
        """Write op.payload to op.target_path under project_dir.

        Supports str, bytes, and dict (serialised as JSON) payloads.
        Creates parent directories automatically. Uses atomic tmp-rename.
        """
        import json
        import tempfile

        target = self.project_dir / op.target_path
        target.parent.mkdir(parents=True, exist_ok=True)

        if op.payload is None:
            return

        if isinstance(op.payload, bytes):
            content = op.payload
            mode = "wb"
        elif isinstance(op.payload, str):
            content = op.payload.encode()
            mode = "wb"
        elif isinstance(op.payload, dict):
            content = json.dumps(op.payload, indent=2).encode()
            mode = "wb"
        else:
            content = str(op.payload).encode()
            mode = "wb"

        # Atomic write via tmp → rename
        tmp_path = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp_path.write_bytes(content)
            tmp_path.replace(target)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

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
