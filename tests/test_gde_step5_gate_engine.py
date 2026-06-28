"""Tests for Step 5: gde_gate_engine.py"""

from __future__ import annotations

import pytest

from genesis_architect_pro.gde_gate_engine import (
    _CONFIDENCE_BLOCK_THRESHOLD,
    _CONFIDENCE_DEGRADED_THRESHOLD,
    _DRIFT_CRITICAL_SCORE,
    evaluate_gates,
)
from genesis_architect_pro.gde_types import (
    EngineResult,
    EngineStatus,
    GateAction,
    GateOutcome,
    GateReport,
    SessionContext,
    WriteOperation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**kwargs) -> SessionContext:
    return SessionContext(**kwargs)


def _add_engine_result(ctx: SessionContext, engine_id: str, output: dict, status=EngineStatus.SUCCESS):
    ctx.engine_results[engine_id] = EngineResult(
        engine_id=engine_id,
        status=status,
        output=output,
    )


def _add_write_op(ctx: SessionContext, operation_id: str, target_path: str, payload=None):
    ctx.pending_write_operations.append(
        WriteOperation(
            engine_id="test_engine",
            operation_id=operation_id,
            description="test write",
            target_path=target_path,
            payload=payload,
        )
    )


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_gate_report(self):
        ctx = _ctx()
        report = evaluate_gates(ctx, [])
        assert isinstance(report, GateReport)

    def test_empty_gates_all_pass(self):
        ctx = _ctx()
        report = evaluate_gates(ctx, [])
        assert report.overall is GateOutcome.PASS
        assert report.hard_blocks == []
        assert report.blocks == []
        assert report.warnings == []

    def test_unknown_gate_ignored(self):
        ctx = _ctx()
        report = evaluate_gates(ctx, ["NONEXISTENT_GATE"])
        assert report.overall is GateOutcome.PASS


# ---------------------------------------------------------------------------
# PLAN_WRITE — hard block, never overridable
# ---------------------------------------------------------------------------


class TestPlanWriteGate:
    def test_no_write_ops_passes(self):
        ctx = _ctx()
        report = evaluate_gates(ctx, ["PLAN_WRITE"])
        assert report.overall is GateOutcome.PASS

    def test_non_planned_write_passes(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", "some/other/file.json")
        report = evaluate_gates(ctx, ["PLAN_WRITE"])
        assert report.overall is GateOutcome.PASS

    def test_planned_json_write_hard_blocks(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", ".genesis/planned.json")
        report = evaluate_gates(ctx, ["PLAN_WRITE"])
        assert report.overall is GateOutcome.HARD_BLOCK
        assert len(report.hard_blocks) == 1
        assert report.hard_blocks[0].gate_id == "PLAN_WRITE"

    def test_planned_json_not_overridable(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", "planned.json")
        report = evaluate_gates(ctx, ["PLAN_WRITE"])
        assert report.hard_blocks[0].override_allowed is False

    def test_planned_json_windows_path(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", ".genesis\\planned.json")
        report = evaluate_gates(ctx, ["PLAN_WRITE"])
        assert report.overall is GateOutcome.HARD_BLOCK


# ---------------------------------------------------------------------------
# RULES_FAIL — hard block, never overridable
# ---------------------------------------------------------------------------


class TestRulesFailGate:
    def test_no_rules_engine_passes(self):
        ctx = _ctx()
        report = evaluate_gates(ctx, ["RULES_FAIL"])
        assert report.overall is GateOutcome.PASS

    def test_rules_engine_no_failure_passes(self):
        ctx = _ctx()
        _add_engine_result(ctx, "rules_engine", {"hard_failure": False})
        report = evaluate_gates(ctx, ["RULES_FAIL"])
        assert report.overall is GateOutcome.PASS

    def test_rules_engine_hard_failure_blocks(self):
        ctx = _ctx()
        _add_engine_result(ctx, "rules_engine", {"hard_failure": True, "hard_failure_reason": "license expired"})
        report = evaluate_gates(ctx, ["RULES_FAIL"])
        assert report.overall is GateOutcome.HARD_BLOCK

    def test_rules_fail_not_overridable(self):
        ctx = _ctx()
        _add_engine_result(ctx, "rules_engine", {"hard_failure": True})
        report = evaluate_gates(ctx, ["RULES_FAIL"])
        assert report.hard_blocks[0].override_allowed is False


# ---------------------------------------------------------------------------
# CONFIDENCE_LOW
# ---------------------------------------------------------------------------


class TestConfidenceLowGate:
    def test_high_confidence_passes(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        report = evaluate_gates(ctx, ["CONFIDENCE_LOW"])
        assert report.overall is GateOutcome.PASS

    def test_at_threshold_passes(self):
        ctx = _ctx()
        ctx.overall_confidence = _CONFIDENCE_BLOCK_THRESHOLD
        report = evaluate_gates(ctx, ["CONFIDENCE_LOW"])
        assert report.overall is GateOutcome.PASS

    def test_below_threshold_blocks(self):
        ctx = _ctx()
        ctx.overall_confidence = _CONFIDENCE_BLOCK_THRESHOLD - 0.01
        report = evaluate_gates(ctx, ["CONFIDENCE_LOW"])
        assert report.overall is GateOutcome.BLOCK

    def test_confidence_low_overridable(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.10
        report = evaluate_gates(ctx, ["CONFIDENCE_LOW"])
        assert report.blocks[0].override_allowed is True


# ---------------------------------------------------------------------------
# DRIFT_CRITICAL
# ---------------------------------------------------------------------------


class TestDriftCriticalGate:
    def test_no_drift_engine_passes(self):
        ctx = _ctx()
        report = evaluate_gates(ctx, ["DRIFT_CRITICAL"])
        assert report.overall is GateOutcome.PASS

    def test_low_drift_passes(self):
        ctx = _ctx()
        _add_engine_result(ctx, "drift_scorer", {"drift_score": 50})
        report = evaluate_gates(ctx, ["DRIFT_CRITICAL"])
        assert report.overall is GateOutcome.PASS

    def test_critical_drift_blocks(self):
        ctx = _ctx()
        _add_engine_result(ctx, "drift_scorer", {"drift_score": _DRIFT_CRITICAL_SCORE + 1})
        report = evaluate_gates(ctx, ["DRIFT_CRITICAL"])
        assert report.overall is GateOutcome.BLOCK

    def test_drift_detector_also_checked(self):
        ctx = _ctx()
        _add_engine_result(ctx, "drift_detector", {"drift_score": 99})
        report = evaluate_gates(ctx, ["DRIFT_CRITICAL"])
        assert report.overall is GateOutcome.BLOCK

    def test_failed_drift_engine_not_triggered(self):
        ctx = _ctx()
        _add_engine_result(ctx, "drift_scorer", {"drift_score": 99}, status=EngineStatus.FAILED)
        report = evaluate_gates(ctx, ["DRIFT_CRITICAL"])
        assert report.overall is GateOutcome.PASS


# ---------------------------------------------------------------------------
# WRITE_SCOPE
# ---------------------------------------------------------------------------


class TestWriteScopeGate:
    def test_no_write_ops_passes(self):
        ctx = _ctx()
        report = evaluate_gates(ctx, ["WRITE_SCOPE"])
        assert report.overall is GateOutcome.PASS

    def test_write_ops_warns(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", "some/file.py")
        report = evaluate_gates(ctx, ["WRITE_SCOPE"])
        assert report.overall is GateOutcome.WARN

    def test_write_scope_overridable(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", "some/file.py")
        report = evaluate_gates(ctx, ["WRITE_SCOPE"])
        assert report.warnings[0].override_allowed is True


# ---------------------------------------------------------------------------
# SECURITY_RISK
# ---------------------------------------------------------------------------


class TestSecurityRiskGate:
    def test_no_security_risk_passes(self):
        ctx = _ctx()
        _add_engine_result(ctx, "some_engine", {"security_risk": False})
        report = evaluate_gates(ctx, ["SECURITY_RISK"])
        assert report.overall is GateOutcome.PASS

    def test_security_risk_blocks(self):
        ctx = _ctx()
        _add_engine_result(ctx, "some_engine", {"security_risk": True, "security_risk_detail": "SQL injection"})
        report = evaluate_gates(ctx, ["SECURITY_RISK"])
        assert report.overall is GateOutcome.BLOCK


# ---------------------------------------------------------------------------
# REQUIRED_FAILED
# ---------------------------------------------------------------------------


class TestRequiredFailedGate:
    def test_no_failures_passes(self):
        ctx = _ctx()
        _add_engine_result(ctx, "eng1", {})
        report = evaluate_gates(ctx, ["REQUIRED_FAILED"])
        assert report.overall is GateOutcome.PASS

    def test_failed_engine_warns(self):
        ctx = _ctx()
        _add_engine_result(ctx, "eng1", {}, status=EngineStatus.FAILED)
        report = evaluate_gates(ctx, ["REQUIRED_FAILED"])
        assert report.overall is GateOutcome.WARN


# ---------------------------------------------------------------------------
# DEGRADED_MODE
# ---------------------------------------------------------------------------


class TestDegradedModeGate:
    def test_high_confidence_passes(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        report = evaluate_gates(ctx, ["DEGRADED_MODE"])
        assert report.overall is GateOutcome.PASS

    def test_below_degraded_threshold_warns(self):
        ctx = _ctx()
        ctx.overall_confidence = _CONFIDENCE_DEGRADED_THRESHOLD - 0.01
        report = evaluate_gates(ctx, ["DEGRADED_MODE"])
        assert report.overall is GateOutcome.WARN


# ---------------------------------------------------------------------------
# NO_ENGINES
# ---------------------------------------------------------------------------


class TestNoEnginesGate:
    def test_engines_ran_passes(self):
        ctx = _ctx()
        _add_engine_result(ctx, "eng1", {})
        report = evaluate_gates(ctx, ["NO_ENGINES"])
        assert report.overall is GateOutcome.PASS

    def test_no_engines_warns(self):
        ctx = _ctx()
        report = evaluate_gates(ctx, ["NO_ENGINES"])
        assert report.overall is GateOutcome.WARN


# ---------------------------------------------------------------------------
# COMMIT_CONFLICT
# ---------------------------------------------------------------------------


class TestCommitConflictGate:
    def test_no_conflict_passes(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", "file.py", payload={"conflict": False})
        report = evaluate_gates(ctx, ["COMMIT_CONFLICT"])
        assert report.overall is GateOutcome.PASS

    def test_conflict_blocks(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", "file.py", payload={"conflict": True})
        report = evaluate_gates(ctx, ["COMMIT_CONFLICT"])
        assert report.overall is GateOutcome.BLOCK


# ---------------------------------------------------------------------------
# Overall outcome precedence
# ---------------------------------------------------------------------------


class TestOverallOutcome:
    def test_hard_block_wins_over_block(self):
        ctx = _ctx()
        _add_write_op(ctx, "op1", "planned.json")   # PLAN_WRITE → HARD_BLOCK
        ctx.overall_confidence = 0.10               # CONFIDENCE_LOW → BLOCK
        report = evaluate_gates(ctx, ["PLAN_WRITE", "CONFIDENCE_LOW"])
        assert report.overall is GateOutcome.HARD_BLOCK

    def test_block_wins_over_warn(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.10              # CONFIDENCE_LOW → BLOCK
        _add_write_op(ctx, "op1", "some/file.py")  # WRITE_SCOPE → WARN
        report = evaluate_gates(ctx, ["CONFIDENCE_LOW", "WRITE_SCOPE"])
        assert report.overall is GateOutcome.BLOCK

    def test_all_pass_is_pass(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        report = evaluate_gates(ctx, ["CONFIDENCE_LOW", "WRITE_SCOPE"])
        assert report.overall is GateOutcome.PASS


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_in_init(self):
        import genesis_architect_pro as pkg
        assert hasattr(pkg, "evaluate_gates")

    def test_importable_directly(self):
        from genesis_architect_pro.gde_gate_engine import evaluate_gates as eg
        assert callable(eg)
