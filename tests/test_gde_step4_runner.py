"""Tests for Step 4: gde_runner.py"""

from __future__ import annotations

import pytest

from genesis_architect.pro.engine_registry import EngineRegistry
from genesis_architect.pro.gde_planner import build_plan
from genesis_architect.pro.gde_runner import (
    _PENALTY_OPTIONAL_FAIL,
    _PENALTY_REQUIRED_FAIL,
    run_plan,
)
from genesis_architect.pro.gde_types import (
    EngineCategory,
    EngineDescriptor,
    EngineStatus,
    ExecutionPlan,
    GDEMode,
    Intent,
    LifecycleStage,
    SessionContext,
)


# ---------------------------------------------------------------------------
# Fake engine modules for testing
# ---------------------------------------------------------------------------
# We register fake engines that reference a module path we control via
# monkeypatching importlib.


import sys
import types


def _make_fake_module(name: str, fn) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.run = fn
    sys.modules[name] = mod
    return mod


def _make_success_fn(output: dict | None = None, confidence: float = 1.0, warnings=None):
    def run(ctx):
        result = dict(output or {})
        result["_confidence"] = confidence
        if warnings:
            result["_warnings"] = warnings
        return result
    return run


def _make_failure_fn():
    def run(ctx):
        raise RuntimeError("engine exploded")
    return run


def _make_desc(
    engine_id: str,
    mode: GDEMode,
    module_name: str,
    requires: list[str] | None = None,
    is_optional: bool = True,
    write_ops: list[str] | None = None,
    timeout: int = 10,
) -> EngineDescriptor:
    return EngineDescriptor(
        id=engine_id,
        name=engine_id,
        module=module_name,
        entry_point="run",
        category=EngineCategory.ANALYSIS,
        input_keys=[],
        output_keys=[],
        requires=requires or [],
        is_optional=is_optional,
        write_operations=write_ops or [],
        timeout_seconds=timeout,
        modes=[mode],
    )


def _make_intent(mode: GDEMode = GDEMode.RECOVERY) -> Intent:
    return Intent(raw_text="test", mode=mode, confidence=0.9)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def cleanup_fake_modules():
    """Remove any fake test modules from sys.modules after each test."""
    before = set(sys.modules.keys())
    yield
    for key in list(sys.modules.keys()):
        if key not in before:
            del sys.modules[key]


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------


class TestBasicExecution:
    def test_empty_plan_returns_ctx(self):
        ctx = SessionContext()
        plan = ExecutionPlan(mode=GDEMode.RECOVERY, phases=[])
        result_ctx = run_plan(plan, ctx, parallel=False)
        assert result_ctx is ctx

    def test_stage_set_to_execute(self):
        ctx = SessionContext()
        plan = ExecutionPlan(mode=GDEMode.RECOVERY, phases=[])
        run_plan(plan, ctx, parallel=False)
        assert ctx.stage is LifecycleStage.EXECUTE

    def test_successful_engine_recorded(self):
        _make_fake_module("fake.engine_a", _make_success_fn({"key": "value"}))
        reg = EngineRegistry()
        desc = _make_desc("engine_a", GDEMode.RECOVERY, "fake.engine_a")
        reg.register(desc)
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert "engine_a" in ctx.engine_results
        assert ctx.engine_results["engine_a"].status is EngineStatus.SUCCESS

    def test_output_stored_in_result(self):
        _make_fake_module("fake.engine_b", _make_success_fn({"answer": 42}))
        reg = EngineRegistry()
        reg.register(_make_desc("engine_b", GDEMode.RECOVERY, "fake.engine_b"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.engine_results["engine_b"].output["answer"] == 42

    def test_multiple_engines_all_recorded(self):
        _make_fake_module("fake.eng1", _make_success_fn())
        _make_fake_module("fake.eng2", _make_success_fn())
        reg = EngineRegistry()
        reg.register(_make_desc("eng1", GDEMode.RECOVERY, "fake.eng1"))
        reg.register(_make_desc("eng2", GDEMode.RECOVERY, "fake.eng2"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert "eng1" in ctx.engine_results
        assert "eng2" in ctx.engine_results


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    def test_optional_engine_failure_does_not_raise(self):
        _make_fake_module("fake.failing", _make_failure_fn())
        reg = EngineRegistry()
        reg.register(_make_desc("failing", GDEMode.RECOVERY, "fake.failing", is_optional=True))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        # Must not raise
        run_plan(plan, ctx, parallel=False)
        assert ctx.engine_results["failing"].status is EngineStatus.FAILED

    def test_required_engine_failure_does_not_raise(self):
        _make_fake_module("fake.req_fail", _make_failure_fn())
        reg = EngineRegistry()
        reg.register(
            _make_desc("req_fail", GDEMode.RECOVERY, "fake.req_fail", is_optional=False)
        )
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.engine_results["req_fail"].status is EngineStatus.FAILED

    def test_optional_failure_penalty(self):
        _make_fake_module("fake.opt_fail", _make_failure_fn())
        reg = EngineRegistry()
        reg.register(
            _make_desc("opt_fail", GDEMode.RECOVERY, "fake.opt_fail", is_optional=True)
        )
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.overall_confidence == pytest.approx(1.0 - _PENALTY_OPTIONAL_FAIL)

    def test_required_failure_larger_penalty(self):
        _make_fake_module("fake.req_fail2", _make_failure_fn())
        reg = EngineRegistry()
        reg.register(
            _make_desc("req_fail2", GDEMode.RECOVERY, "fake.req_fail2", is_optional=False)
        )
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.overall_confidence == pytest.approx(1.0 - _PENALTY_REQUIRED_FAIL)

    def test_confidence_floor_never_below_0_10(self):
        # Many required failures should floor at 0.10
        for i in range(10):
            mod_name = f"fake.many_fail_{i}"
            _make_fake_module(mod_name, _make_failure_fn())
        reg = EngineRegistry()
        for i in range(10):
            reg.register(
                _make_desc(f"many_fail_{i}", GDEMode.RECOVERY, f"fake.many_fail_{i}", is_optional=False)
            )
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.overall_confidence >= 0.10

    def test_failed_engine_has_error_string(self):
        _make_fake_module("fake.err_eng", _make_failure_fn())
        reg = EngineRegistry()
        reg.register(_make_desc("err_eng", GDEMode.RECOVERY, "fake.err_eng"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.engine_results["err_eng"].error is not None
        assert len(ctx.engine_results["err_eng"].error) > 0


# ---------------------------------------------------------------------------
# Dependency / skip propagation
# ---------------------------------------------------------------------------


class TestDependencySkip:
    def test_dependent_skipped_when_dep_failed(self):
        _make_fake_module("fake.dep_base", _make_failure_fn())
        _make_fake_module("fake.dep_child", _make_success_fn())
        reg = EngineRegistry()
        reg.register(_make_desc("dep_base", GDEMode.RECOVERY, "fake.dep_base"))
        reg.register(
            _make_desc("dep_child", GDEMode.RECOVERY, "fake.dep_child", requires=["dep_base"])
        )
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.engine_results["dep_base"].status is EngineStatus.FAILED
        assert ctx.engine_results["dep_child"].status is EngineStatus.SKIPPED

    def test_independent_engine_runs_despite_sibling_failure(self):
        _make_fake_module("fake.sib_fail", _make_failure_fn())
        _make_fake_module("fake.sib_ok", _make_success_fn())
        reg = EngineRegistry()
        reg.register(_make_desc("sib_fail", GDEMode.RECOVERY, "fake.sib_fail"))
        reg.register(_make_desc("sib_ok", GDEMode.RECOVERY, "fake.sib_ok"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.engine_results["sib_ok"].status is EngineStatus.SUCCESS


# ---------------------------------------------------------------------------
# Degraded engine (warnings)
# ---------------------------------------------------------------------------


class TestDegradedEngine:
    def test_engine_with_warnings_is_degraded(self):
        _make_fake_module(
            "fake.warn_eng",
            _make_success_fn(warnings=["something smells"]),
        )
        reg = EngineRegistry()
        reg.register(_make_desc("warn_eng", GDEMode.RECOVERY, "fake.warn_eng"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.engine_results["warn_eng"].status is EngineStatus.DEGRADED

    def test_degraded_reduces_confidence(self):
        _make_fake_module(
            "fake.warn_eng2",
            _make_success_fn(warnings=["watch out"]),
        )
        reg = EngineRegistry()
        reg.register(_make_desc("warn_eng2", GDEMode.RECOVERY, "fake.warn_eng2"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert ctx.overall_confidence < 1.0


# ---------------------------------------------------------------------------
# Decision log
# ---------------------------------------------------------------------------


class TestDecisionLog:
    def test_decision_log_populated(self):
        _make_fake_module("fake.log_eng", _make_success_fn())
        reg = EngineRegistry()
        reg.register(_make_desc("log_eng", GDEMode.RECOVERY, "fake.log_eng"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        assert len(ctx.decision_log) > 0

    def test_decision_log_has_engine_id(self):
        _make_fake_module("fake.log_eng2", _make_success_fn())
        reg = EngineRegistry()
        reg.register(_make_desc("log_eng2", GDEMode.RECOVERY, "fake.log_eng2"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=False)
        subjects = [e.subject for e in ctx.decision_log]
        assert "log_eng2" in subjects


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


class TestParallelExecution:
    def test_parallel_runs_all_engines(self):
        _make_fake_module("fake.par1", _make_success_fn({"x": 1}))
        _make_fake_module("fake.par2", _make_success_fn({"y": 2}))
        reg = EngineRegistry()
        reg.register(_make_desc("par1", GDEMode.RECOVERY, "fake.par1"))
        reg.register(_make_desc("par2", GDEMode.RECOVERY, "fake.par2"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=True)
        assert "par1" in ctx.engine_results
        assert "par2" in ctx.engine_results

    def test_parallel_failure_does_not_crash(self):
        _make_fake_module("fake.par_fail", _make_failure_fn())
        _make_fake_module("fake.par_ok", _make_success_fn())
        reg = EngineRegistry()
        reg.register(_make_desc("par_fail", GDEMode.RECOVERY, "fake.par_fail"))
        reg.register(_make_desc("par_ok", GDEMode.RECOVERY, "fake.par_ok"))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        run_plan(plan, ctx, parallel=True)
        assert ctx.engine_results["par_ok"].status is EngineStatus.SUCCESS


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_in_init(self):
        import genesis_architect.pro as pkg
        assert hasattr(pkg, "run_plan")

    def test_importable_directly(self):
        from genesis_architect.pro.gde_runner import run_plan as rp
        assert callable(rp)
