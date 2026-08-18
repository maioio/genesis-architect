"""Genesis Decision Engine — gate engine.

Evaluates the 13 named approval gates against a SessionContext and
produces a GateReport. Gate policy is a static table here — not scattered
in orchestration logic.

Hard-block gates (PLAN_WRITE, RULES_FAIL) are NEVER overridable.
All other gates may be overridden if override_allowed=True.

Gate IDs and their trigger conditions:
  PLAN_WRITE        — any write op targeting planned.json → HARD_BLOCK
  RULES_FAIL        — rules engine returned a hard failure → HARD_BLOCK
  CONFIDENCE_LOW    — overall_confidence < 0.40 → BLOCK_AND_ASK
  DRIFT_CRITICAL    — drift score > 80 in engine results → BLOCK_AND_ASK
  WRITE_SCOPE       — pending_write_operations non-empty → WARN
  SECURITY_RISK     — security signal detected in engine output → BLOCK_AND_ASK
  POLICY_VIOLATION  — rules engine returned policy violation → BLOCK_AND_ASK
  REQUIRED_FAILED   — any required engine failed → WARN
  DEGRADED_MODE     — overall_confidence < 0.60 → WARN
  NO_ENGINES        — zero engines ran for the mode → WARN
  RESEARCH_STALE    — research results older than 24h signal → WARN
  COMMIT_CONFLICT   — write op conflicts with existing committed model → BLOCK_AND_ASK
  RED_TEAM_CRITICAL — red_team_critic found a critical-severity finding → BLOCK_AND_ASK
  RESEARCH_COVERAGE_LOW — an outline-driven research pass reports coverage
                     below threshold → BLOCK_AND_ASK
"""

from __future__ import annotations

import datetime

from genesis_architect_pro.gde_types import (
    GateAction,
    GateReport,
    GateResult,
    SessionContext,
)

# ---------------------------------------------------------------------------
# Confidence thresholds
# ---------------------------------------------------------------------------

_CONFIDENCE_BLOCK_THRESHOLD = 0.40
_CONFIDENCE_DEGRADED_THRESHOLD = 0.60

# Drift score threshold (stored in engine output under 'drift_score' key)
_DRIFT_CRITICAL_SCORE = 80.0

# Research coverage threshold (stored in engine output under 'coverage' key,
# 0.0-1.0). None means no outline was used and is never "low" - only an
# actual measured fraction below this counts.
_RESEARCH_COVERAGE_LOW_THRESHOLD = 0.50

# ---------------------------------------------------------------------------
# Gate policy table
# ---------------------------------------------------------------------------
# Each entry: (gate_id, title, override_allowed, action, confidence_penalty)

_GATE_POLICY: list[tuple[str, str, bool, GateAction, float]] = [
    # Hard blocks — never overridable
    ("PLAN_WRITE",       "Planned file write blocked",          False, GateAction.HARD_BLOCK,    0.0),
    ("RULES_FAIL",       "Rules engine hard failure",           False, GateAction.HARD_BLOCK,    0.0),
    # Soft blocks — require user approval
    ("CONFIDENCE_LOW",   "Confidence below safe threshold",     True,  GateAction.BLOCK_AND_ASK, 0.15),
    ("DRIFT_CRITICAL",   "Critical drift detected",             True,  GateAction.BLOCK_AND_ASK, 0.15),
    ("SECURITY_RISK",    "Security risk in proposed changes",   True,  GateAction.BLOCK_AND_ASK, 0.15),
    ("POLICY_VIOLATION", "Policy violation detected",           True,  GateAction.BLOCK_AND_ASK, 0.15),
    ("COMMIT_CONFLICT",  "Write conflict with committed model", True,  GateAction.BLOCK_AND_ASK, 0.10),
    ("RED_TEAM_CRITICAL", "Red-team found a critical vulnerability", True, GateAction.BLOCK_AND_ASK, 0.15),
    ("RESEARCH_COVERAGE_LOW", "Research coverage below threshold",   True,  GateAction.BLOCK_AND_ASK, 0.10),
    # Warnings — surface and continue
    ("WRITE_SCOPE",      "Write operations pending",            True,  GateAction.WARN,          0.05),
    ("REQUIRED_FAILED",  "Required engine(s) failed",           True,  GateAction.WARN,          0.05),
    ("DEGRADED_MODE",    "Session running in degraded mode",    True,  GateAction.WARN,          0.05),
    ("NO_ENGINES",       "No engines ran for this mode",        True,  GateAction.WARN,          0.00),
    ("RESEARCH_STALE",   "Research results may be stale",       True,  GateAction.WARN,          0.00),
]

# Build lookup dict for O(1) access
_POLICY: dict[str, tuple[str, bool, GateAction, float]] = {
    gate_id: (title, override_allowed, action, penalty)
    for gate_id, title, override_allowed, action, penalty in _GATE_POLICY
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_gates(ctx: SessionContext, required_gate_ids: list[str]) -> GateReport:
    """Evaluate all required gates against the current SessionContext.

    Args:
        ctx: Fully populated SessionContext (after EXECUTE stage).
        required_gate_ids: List of gate IDs to evaluate (from ExecutionPlan).

    Returns:
        GateReport with categorised results and overall outcome.
    """
    report = GateReport()

    for gate_id in required_gate_ids:
        if gate_id not in _POLICY:
            continue  # unknown gate — skip silently
        title, override_allowed, default_action, penalty = _POLICY[gate_id]

        fired, reason, detail = _evaluate_gate(gate_id, ctx)
        if not fired:
            result = GateResult(
                gate_id=gate_id,
                action=GateAction.PASS,
                override_allowed=override_allowed,
                title=title,
                reason="Gate condition not met — pass",
                detail="",
                confidence_penalty=0.0,
            )
            report.passed.append(result)
            continue

        result = GateResult(
            gate_id=gate_id,
            action=default_action,
            override_allowed=override_allowed,
            title=title,
            reason=reason,
            detail=detail,
            confidence_penalty=penalty,
            presented_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        if default_action is GateAction.HARD_BLOCK:
            report.hard_blocks.append(result)
        elif default_action is GateAction.BLOCK_AND_ASK:
            report.blocks.append(result)
        else:
            report.warnings.append(result)

    report.recompute_overall()
    return report


# ---------------------------------------------------------------------------
# Per-gate condition checks
# ---------------------------------------------------------------------------


def _evaluate_gate(gate_id: str, ctx: SessionContext) -> tuple[bool, str, str]:
    """Return (fired, reason, detail) for a single gate."""
    fn = _GATE_CHECKS.get(gate_id)
    if fn is None:
        return False, "", ""
    return fn(ctx)


def _check_plan_write(ctx: SessionContext) -> tuple[bool, str, str]:
    for op in ctx.pending_write_operations:
        target = str(op.target_path).lower().replace("\\", "/")
        if "planned.json" in target:
            return (
                True,
                "Write operation targets planned.json — unconditionally blocked",
                f"target_path={op.target_path!r}, engine={op.engine_id!r}",
            )
    return False, "", ""


def _check_rules_fail(ctx: SessionContext) -> tuple[bool, str, str]:
    rules_result = ctx.engine_results.get("rules_engine")
    if rules_result is None:
        return False, "", ""
    hard = rules_result.output.get("hard_failure", False)
    if hard:
        return (
            True,
            "Rules engine reported a hard failure",
            str(rules_result.output.get("hard_failure_reason", "")),
        )
    return False, "", ""


def _check_confidence_low(ctx: SessionContext) -> tuple[bool, str, str]:
    if ctx.overall_confidence < _CONFIDENCE_BLOCK_THRESHOLD:
        return (
            True,
            f"Confidence {ctx.overall_confidence:.2f} is below threshold {_CONFIDENCE_BLOCK_THRESHOLD}",
            "Too many engine failures or gate penalties accumulated.",
        )
    return False, "", ""


def _check_drift_critical(ctx: SessionContext) -> tuple[bool, str, str]:
    # Check drift_scorer or drift_detector engine output
    for engine_id in ("drift_scorer", "drift_detector"):
        result = ctx.engine_results.get(engine_id)
        if result and result.status.value != "failed":
            score = result.output.get("drift_score")
            if score is not None and float(score) > _DRIFT_CRITICAL_SCORE:
                return (
                    True,
                    f"Critical drift score {score} exceeds threshold {_DRIFT_CRITICAL_SCORE}",
                    f"engine={engine_id!r}",
                )
    return False, "", ""


def _check_write_scope(ctx: SessionContext) -> tuple[bool, str, str]:
    if ctx.pending_write_operations:
        count = len(ctx.pending_write_operations)
        ops = ", ".join(op.operation_id for op in ctx.pending_write_operations[:5])
        return (
            True,
            f"{count} write operation(s) pending approval",
            ops,
        )
    return False, "", ""


def _check_security_risk(ctx: SessionContext) -> tuple[bool, str, str]:
    for engine_id, result in ctx.engine_results.items():
        if result.output.get("security_risk", False):
            return (
                True,
                f"Engine '{engine_id}' flagged a security risk",
                str(result.output.get("security_risk_detail", "")),
            )
    return False, "", ""


def _check_policy_violation(ctx: SessionContext) -> tuple[bool, str, str]:
    rules_result = ctx.engine_results.get("rules_engine")
    if rules_result and rules_result.output.get("policy_violation", False):
        return (
            True,
            "Rules engine detected a policy violation",
            str(rules_result.output.get("policy_violation_detail", "")),
        )
    return False, "", ""


def _check_required_failed(ctx: SessionContext) -> tuple[bool, str, str]:
    from genesis_architect_pro.gde_types import EngineStatus
    failed = [
        eid for eid, r in ctx.engine_results.items()
        if r.status is EngineStatus.FAILED
    ]
    if failed:
        return (
            True,
            f"{len(failed)} engine(s) failed: {', '.join(failed[:3])}",
            str(failed),
        )
    return False, "", ""


def _check_degraded_mode(ctx: SessionContext) -> tuple[bool, str, str]:
    if ctx.overall_confidence < _CONFIDENCE_DEGRADED_THRESHOLD:
        return (
            True,
            f"Session confidence {ctx.overall_confidence:.2f} below degraded threshold {_CONFIDENCE_DEGRADED_THRESHOLD}",
            "",
        )
    return False, "", ""


def _check_no_engines(ctx: SessionContext) -> tuple[bool, str, str]:
    if not ctx.engine_results:
        return True, "No engines produced results for this session", ""
    return False, "", ""


def _check_research_stale(ctx: SessionContext) -> tuple[bool, str, str]:
    for engine_id, result in ctx.engine_results.items():
        if result.output.get("results_stale", False):
            return (
                True,
                f"Engine '{engine_id}' reports stale research results",
                str(result.output.get("stale_reason", "")),
            )
    return False, "", ""


def _check_commit_conflict(ctx: SessionContext) -> tuple[bool, str, str]:
    for op in ctx.pending_write_operations:
        if op.payload and isinstance(op.payload, dict) and op.payload.get("conflict", False):
            return (
                True,
                f"Write operation '{op.operation_id}' conflicts with committed model",
                f"target={op.target_path!r}",
            )
    return False, "", ""


def _check_red_team_critical(ctx: SessionContext) -> tuple[bool, str, str]:
    result = ctx.engine_results.get("red_team_critic")
    if result is None:
        return False, "", ""
    critical_count = result.output.get("critical_findings", 0)
    if critical_count:
        findings = result.output.get("findings", [])
        critical_descriptions = [
            f["description"] for f in findings if f.get("severity") == "critical"
        ]
        return (
            True,
            f"Red-team critique found {critical_count} critical finding(s)",
            "; ".join(critical_descriptions[:3]),
        )
    return False, "", ""


def _check_research_coverage_low(ctx: SessionContext) -> tuple[bool, str, str]:
    """Fires when an outline-driven research pass reports coverage below
    threshold. `coverage` is None whenever no outline was used at all - that
    is "not applicable", never "low", so it is skipped rather than treated
    as a failure. Scans every engine's output rather than one named engine
    ID, since research coverage is a signal any research-producing engine
    may report, not a property of one fixed engine.
    """
    for engine_id, result in ctx.engine_results.items():
        coverage = result.output.get("coverage")
        if coverage is None:
            continue
        if float(coverage) < _RESEARCH_COVERAGE_LOW_THRESHOLD:
            outline = result.output.get("outline") or {}
            topic = outline.get("topic", "")
            return (
                True,
                f"Engine '{engine_id}' reports research coverage "
                f"{float(coverage):.0%}, below the "
                f"{_RESEARCH_COVERAGE_LOW_THRESHOLD:.0%} threshold",
                f"outline={topic!r}" if topic else "",
            )
    return False, "", ""


# ---------------------------------------------------------------------------
# Gate check dispatch table
# ---------------------------------------------------------------------------

_GATE_CHECKS: dict[str, object] = {
    "PLAN_WRITE":       _check_plan_write,
    "RULES_FAIL":       _check_rules_fail,
    "CONFIDENCE_LOW":   _check_confidence_low,
    "DRIFT_CRITICAL":   _check_drift_critical,
    "WRITE_SCOPE":      _check_write_scope,
    "SECURITY_RISK":    _check_security_risk,
    "POLICY_VIOLATION": _check_policy_violation,
    "REQUIRED_FAILED":  _check_required_failed,
    "DEGRADED_MODE":    _check_degraded_mode,
    "NO_ENGINES":       _check_no_engines,
    "RESEARCH_STALE":   _check_research_stale,
    "COMMIT_CONFLICT":  _check_commit_conflict,
    "RED_TEAM_CRITICAL": _check_red_team_critical,
    "RESEARCH_COVERAGE_LOW": _check_research_coverage_low,
}
