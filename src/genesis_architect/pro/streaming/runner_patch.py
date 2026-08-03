"""Genesis Companion streaming — GDE runner instrumentation.

Monkey-patches `gde_runner._run_single` to emit streaming events before
and after each engine execution, without modifying the runner source.

Also patches `gde_gate_engine` to emit gate events.

Usage::

    from genesis_architect.pro.streaming.runner_patch import install, uninstall

    install()   # call once at Companion startup
    # ... GDE sessions now emit events via default_emitter
    uninstall() # call at shutdown (optional; restores original functions)

The patch is idempotent: calling install() twice has no effect.
"""

from __future__ import annotations

from typing import Callable

import genesis_architect.pro.gde_runner as _runner_module
from genesis_architect.pro.gde_types import (
    EngineDescriptor,
    EngineStatus,
    SessionContext,
)
from genesis_architect.pro.streaming.events import (
    default_emitter,
    engine_done,
    engine_failed,
    engine_start,
    gate_fired,
    session_confidence,
)

_ORIGINAL_RUN_SINGLE: Callable | None = None
_INSTALLED = False

# Confidence penalties (mirrors gde_runner constants)
_PENALTY_OPTIONAL_FAIL = 0.10
_PENALTY_REQUIRED_FAIL = 0.20


# ---------------------------------------------------------------------------
# Patched _run_single
# ---------------------------------------------------------------------------

def _patched_run_single(desc: EngineDescriptor, ctx: SessionContext) -> None:
    """Wrap the original _run_single with before/after streaming events."""
    # Determine phase index from the plan stored in ctx (best-effort)
    phase_index = _guess_phase(desc, ctx)
    total_phases = _guess_total_phases(ctx)

    default_emitter.emit(
        engine_start(desc.id, phase=phase_index, total_phases=total_phases, session_id=ctx.session_id)
    )


    # Call original
    _ORIGINAL_RUN_SINGLE(desc, ctx)  # type: ignore[misc]

    result = ctx.engine_results.get(desc.id)
    if result is None:
        return

    if result.status == EngineStatus.FAILED:
        penalty = _PENALTY_REQUIRED_FAIL if not desc.is_optional else _PENALTY_OPTIONAL_FAIL
        default_emitter.emit(
            engine_failed(
                desc.id,
                error=result.error or "unknown error",
                confidence_penalty=penalty,
                session_id=ctx.session_id,
            )
        )
    else:
        summary = _build_summary(desc.id, result.output)
        default_emitter.emit(
            engine_done(
                desc.id,
                confidence=result.confidence,
                result_summary=summary,
                session_id=ctx.session_id,
            )
        )

    # Emit updated session confidence after each engine
    default_emitter.emit(
        session_confidence(
            confidence=ctx.overall_confidence,
            risk_level=ctx.project_risk_level,
            session_id=ctx.session_id,
        )
    )


# ---------------------------------------------------------------------------
# Gate instrumentation
# ---------------------------------------------------------------------------

def _patch_gate_engine() -> None:
    """Wrap gde_gate_engine.evaluate_gates to emit gate events."""
    try:
        import genesis_architect.pro.gde_gate_engine as gate_module
    except ImportError:
        return

    original_evaluate = getattr(gate_module, "evaluate_gates", None)
    if original_evaluate is None or getattr(original_evaluate, "_genesis_patched", False):
        return

    def _patched_evaluate(ctx: SessionContext):  # type: ignore[no-untyped-def]
        report = original_evaluate(ctx)
        # Emit an event per fired gate
        for gate in report.blocks + report.warnings + report.hard_blocks:
            gate_type = "hard_block" if gate in report.hard_blocks else (
                "soft_block" if gate in report.blocks else "warning"
            )
            default_emitter.emit(
                gate_fired(
                    gate_name=gate.gate_id,
                    gate_type=gate_type,
                    overridable=gate.override_allowed,
                    session_id=ctx.session_id,
                )
            )
        return report

    _patched_evaluate._genesis_patched = True  # type: ignore[attr-defined]
    gate_module.evaluate_gates = _patched_evaluate


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------

def install() -> None:
    """Install streaming hooks into the GDE runner. Idempotent."""
    global _ORIGINAL_RUN_SINGLE, _INSTALLED
    if _INSTALLED:
        return

    _ORIGINAL_RUN_SINGLE = _runner_module._run_single
    _runner_module._run_single = _patched_run_single
    _patch_gate_engine()
    _INSTALLED = True


def uninstall() -> None:
    """Restore the original GDE runner functions."""
    global _ORIGINAL_RUN_SINGLE, _INSTALLED
    if not _INSTALLED or _ORIGINAL_RUN_SINGLE is None:
        return

    _runner_module._run_single = _ORIGINAL_RUN_SINGLE
    _ORIGINAL_RUN_SINGLE = None
    _INSTALLED = False


def is_installed() -> bool:
    return _INSTALLED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guess_phase(desc: EngineDescriptor, ctx: SessionContext) -> int:
    """Best-effort: count how many engines have already finished."""
    return len(ctx.engine_results)


def _guess_total_phases(ctx: SessionContext) -> int:
    """Not known at runtime without the plan — return 0 (unknown)."""
    return 0


def _build_summary(engine_id: str, output: dict) -> str:
    """One-line result summary per engine type."""
    if engine_id == "architecture_scorer":
        return f"Score {output.get('score', '?')}/100 ({output.get('score_label', '')})"
    if engine_id == "antipattern_detector":
        return f"{output.get('critical_count', 0)} critical, {output.get('high_count', 0)} high"
    if engine_id == "fragility_classifier":
        return (
            f"VOLATILE:{output.get('volatile_count', 0)} "
            f"FRAGILE:{output.get('fragile_count', 0)} "
            f"STABLE:{output.get('stable_count', 0)}"
        )
    if engine_id == "import_graph":
        cycles = output.get("cycles", [])
        return f"{len(output.get('graph', {}))} modules, {len(cycles)} cycles"
    if engine_id == "committee_analysis":
        verdict = output.get("committee_verdict", "")
        return verdict[:80] + ("…" if len(verdict) > 80 else "") if verdict else f"{output.get('perspective_count', 0)} perspectives"
    return ""
