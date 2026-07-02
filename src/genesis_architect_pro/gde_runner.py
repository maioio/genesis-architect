"""Genesis Decision Engine — engine runner.

Executes one ExecutionPlan phase by phase, collecting EngineResults into
a SessionContext. Supports:
- Sequential phase execution
- Optional per-phase parallel execution (via concurrent.futures)
- Timeout enforcement per engine
- Graceful degradation on failure (never raises; records and continues)
- Confidence penalty application per architecture spec

Confidence penalties (from architecture spec):
  Optional engine failure:  -0.10
  Required engine failure:  -0.20
  Engine degraded:          -0.05
  Dependency skipped:       propagated from skipped engine

No planning logic lives here. The runner is given a ready ExecutionPlan.
"""

from __future__ import annotations

import importlib
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from typing import Any, Callable

from genesis_architect_pro.gde_types import (
    DecisionEntry,
    EngineDescriptor,
    EngineResult,
    EngineStatus,
    ExecutionPlan,
    LifecycleStage,
    SessionContext,
)

# Confidence penalties
_PENALTY_OPTIONAL_FAIL = 0.10
_PENALTY_REQUIRED_FAIL = 0.20
_PENALTY_DEGRADED = 0.05


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_plan(
    plan: ExecutionPlan,
    ctx: SessionContext,
    parallel: bool = True,
) -> SessionContext:
    """Execute all phases in the plan, updating ctx in place.

    Args:
        plan: The execution plan (phases of engine groups).
        ctx: The session context to populate with results.
        parallel: If True, engines within a phase run concurrently.
                  If False, they run sequentially (useful for testing).

    Returns:
        The same ctx (mutated), now containing all engine results.
    """
    ctx.stage = LifecycleStage.EXECUTE

    for phase_index, phase in enumerate(plan.phases):
        if parallel and len(phase) > 1:
            _run_phase_parallel(phase, ctx)
        else:
            for desc in phase:
                _run_single(desc, ctx)

    return ctx


# ---------------------------------------------------------------------------
# Phase execution
# ---------------------------------------------------------------------------


def _run_phase_parallel(phase: list[EngineDescriptor], ctx: SessionContext) -> None:
    with ThreadPoolExecutor(max_workers=len(phase)) as pool:
        futures = {pool.submit(_run_single, desc, ctx): desc for desc in phase}
        for future in futures:
            try:
                future.result()
            except Exception:
                pass  # _run_single never raises; this is a safety net


def _run_single(desc: EngineDescriptor, ctx: SessionContext) -> None:
    """Run one engine, handle failure, apply penalties, record in ctx."""
    # Skip if any required dependency failed or was skipped
    for dep_id in desc.requires:
        dep_result = ctx.engine_results.get(dep_id)
        if dep_result is not None and dep_result.status in (
            EngineStatus.FAILED,
            EngineStatus.SKIPPED,
        ):
            _record_skipped(desc, ctx, reason=f"dependency '{dep_id}' failed/skipped")
            return

    start_ms = int(time.monotonic() * 1000)

    try:
        output = _invoke(desc, ctx)
        duration_ms = int(time.monotonic() * 1000) - start_ms

        status = EngineStatus.SUCCESS
        confidence = float(output.pop("_confidence", 1.0))
        warnings = list(output.pop("_warnings", []))

        result = EngineResult(
            engine_id=desc.id,
            status=status,
            output=output,
            confidence=max(0.0, min(1.0, confidence)),
            warnings=warnings,
            duration_ms=duration_ms,
        )

        if warnings:
            result.status = EngineStatus.DEGRADED
            ctx.apply_confidence_penalty(_PENALTY_DEGRADED)

        ctx.merge_engine_result(result)
        _log(ctx, desc, result, LifecycleStage.EXECUTE)

    except Exception as exc:  # noqa: BLE001
        duration_ms = int(time.monotonic() * 1000) - start_ms
        _record_failure(desc, ctx, error=str(exc), duration_ms=duration_ms)


# ---------------------------------------------------------------------------
# Engine invocation
# ---------------------------------------------------------------------------


def _invoke(desc: EngineDescriptor, ctx: SessionContext) -> dict[str, Any]:
    """Dynamically import and call the engine's entry point.

    The entry point must be a callable at `desc.module.desc.entry_point`
    that accepts a SessionContext and returns a dict.

    Special keys in the returned dict:
      _confidence: float — engine's self-reported confidence (default 1.0)
      _warnings: list[str] — warnings to surface (triggers DEGRADED status)
    """
    module = importlib.import_module(desc.module)
    fn: Callable[[SessionContext], dict[str, Any]] = getattr(module, desc.entry_point)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, ctx)
        try:
            return future.result(timeout=desc.timeout_seconds)
        except FuturesTimeout:
            raise TimeoutError(
                f"Engine '{desc.id}' timed out after {desc.timeout_seconds}s"
            )


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _record_skipped(
    desc: EngineDescriptor,
    ctx: SessionContext,
    reason: str,
) -> None:
    result = EngineResult(
        engine_id=desc.id,
        status=EngineStatus.SKIPPED,
        error=reason,
    )
    ctx.merge_engine_result(result)
    _log(ctx, desc, result, LifecycleStage.EXECUTE)


def _record_failure(
    desc: EngineDescriptor,
    ctx: SessionContext,
    error: str,
    duration_ms: int = 0,
) -> None:
    result = EngineResult(
        engine_id=desc.id,
        status=EngineStatus.FAILED,
        error=error,
        duration_ms=duration_ms,
    )
    ctx.merge_engine_result(result)

    penalty = _PENALTY_REQUIRED_FAIL if not desc.is_optional else _PENALTY_OPTIONAL_FAIL
    ctx.apply_confidence_penalty(penalty)
    _log(ctx, desc, result, LifecycleStage.EXECUTE)


def _log(
    ctx: SessionContext,
    desc: EngineDescriptor,
    result: EngineResult,
    stage: LifecycleStage,
) -> None:
    entry = DecisionEntry(
        session_id=ctx.session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        stage=stage,
        decision_type="ENGINE_INVOKED",
        actor="gde",
        subject=desc.id,
        detail=result.error or result.status.value,
        confidence_before=ctx.overall_confidence,
        confidence_after=ctx.overall_confidence,
        outcome=result.status.value,
    )
    ctx.record(entry)
