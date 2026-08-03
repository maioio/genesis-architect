"""Tests for Step 3: gde_planner.py"""

from __future__ import annotations


from genesis_architect.pro.engine_registry import EngineRegistry
from genesis_architect.pro.gde_planner import _UNIVERSAL_GATES, build_plan
from genesis_architect.pro.gde_types import (
    EngineCategory,
    EngineDescriptor,
    ExecutionPlan,
    GDEMode,
    Intent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intent(mode: GDEMode, confidence: float = 0.9) -> Intent:
    return Intent(raw_text="test", mode=mode, confidence=confidence)


def _make_desc(
    engine_id: str,
    mode: GDEMode,
    requires: list[str] | None = None,
    write_ops: list[str] | None = None,
    timeout: int = 30,
) -> EngineDescriptor:
    return EngineDescriptor(
        id=engine_id,
        name=engine_id,
        module=f"mod.{engine_id}",
        entry_point="run",
        category=EngineCategory.ANALYSIS,
        input_keys=[],
        output_keys=[],
        requires=requires or [],
        write_operations=write_ops or [],
        timeout_seconds=timeout,
        modes=[mode],
    )


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_execution_plan(self):
        reg = EngineRegistry()
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert isinstance(plan, ExecutionPlan)

    def test_plan_mode_matches_intent(self):
        reg = EngineRegistry()
        for mode in GDEMode:
            plan = build_plan(_make_intent(mode), registry=reg)
            assert plan.mode is mode

    def test_empty_registry_empty_phases(self):
        reg = EngineRegistry()
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert plan.phases == []

    def test_phases_is_list_of_lists(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.RECOVERY))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert isinstance(plan.phases, list)
        for phase in plan.phases:
            assert isinstance(phase, list)


# ---------------------------------------------------------------------------
# Phase grouping
# ---------------------------------------------------------------------------


class TestPhaseGrouping:
    def test_single_engine_one_phase(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.RECOVERY))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert len(plan.phases) == 1
        assert len(plan.phases[0]) == 1

    def test_independent_engines_same_phase(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.RECOVERY))
        reg.register(_make_desc("b", GDEMode.RECOVERY))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert len(plan.phases) == 1
        assert len(plan.phases[0]) == 2

    def test_dependent_engines_sequential_phases(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.RECOVERY))
        reg.register(_make_desc("b", GDEMode.RECOVERY, requires=["a"]))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert len(plan.phases) == 2
        assert plan.phases[0][0].id == "a"
        assert plan.phases[1][0].id == "b"

    def test_diamond_dependency(self):
        reg = EngineRegistry()
        reg.register(_make_desc("root", GDEMode.BUILD))
        reg.register(_make_desc("left", GDEMode.BUILD, requires=["root"]))
        reg.register(_make_desc("right", GDEMode.BUILD, requires=["root"]))
        reg.register(_make_desc("tip", GDEMode.BUILD, requires=["left", "right"]))
        plan = build_plan(_make_intent(GDEMode.BUILD), registry=reg)
        assert len(plan.phases) == 3
        phase_ids = [[d.id for d in p] for p in plan.phases]
        assert phase_ids[0] == ["root"]
        assert sorted(phase_ids[1]) == ["left", "right"]
        assert phase_ids[2] == ["tip"]

    def test_mode_filter_applies(self):
        reg = EngineRegistry()
        reg.register(_make_desc("recovery_only", GDEMode.RECOVERY))
        reg.register(_make_desc("research_only", GDEMode.RESEARCH))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        ids = [d.id for phase in plan.phases for d in phase]
        assert "recovery_only" in ids
        assert "research_only" not in ids


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


class TestGates:
    def test_universal_gates_always_present(self):
        reg = EngineRegistry()
        for mode in GDEMode:
            plan = build_plan(_make_intent(mode), registry=reg)
            for gate in _UNIVERSAL_GATES:
                assert gate in plan.required_gate_ids, f"{gate} missing for {mode}"

    def test_recovery_has_drift_gate(self):
        reg = EngineRegistry()
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert "DRIFT_CRITICAL" in plan.required_gate_ids

    def test_build_has_security_gate(self):
        reg = EngineRegistry()
        plan = build_plan(_make_intent(GDEMode.BUILD), registry=reg)
        assert "SECURITY_RISK" in plan.required_gate_ids

    def test_no_duplicate_gates(self):
        reg = EngineRegistry()
        for mode in GDEMode:
            plan = build_plan(_make_intent(mode), registry=reg)
            assert len(plan.required_gate_ids) == len(set(plan.required_gate_ids))


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


class TestWriteOperations:
    def test_no_engines_no_write_ops(self):
        reg = EngineRegistry()
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert plan.write_operations_pending == []

    def test_engine_write_ops_collected(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.BUILD, write_ops=["write_file", "write_config"]))
        plan = build_plan(_make_intent(GDEMode.BUILD), registry=reg)
        assert "write_file" in plan.write_operations_pending
        assert "write_config" in plan.write_operations_pending

    def test_write_ops_deduplicated(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.BUILD, write_ops=["write_file"]))
        reg.register(_make_desc("b", GDEMode.BUILD, write_ops=["write_file", "write_config"]))
        plan = build_plan(_make_intent(GDEMode.BUILD), registry=reg)
        assert plan.write_operations_pending.count("write_file") == 1

    def test_write_ops_order_stable(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.BUILD, write_ops=["first", "second"]))
        plan = build_plan(_make_intent(GDEMode.BUILD), registry=reg)
        assert plan.write_operations_pending == ["first", "second"]


# ---------------------------------------------------------------------------
# Duration estimation
# ---------------------------------------------------------------------------


class TestDuration:
    def test_empty_registry_zero_duration(self):
        reg = EngineRegistry()
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert plan.estimated_duration_seconds == 0

    def test_single_engine_duration(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.RECOVERY, timeout=45))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        assert plan.estimated_duration_seconds == 45

    def test_parallel_engines_max_duration(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.RECOVERY, timeout=10))
        reg.register(_make_desc("b", GDEMode.RECOVERY, timeout=30))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        # Parallel: takes max(10, 30) = 30
        assert plan.estimated_duration_seconds == 30

    def test_sequential_phases_sum_duration(self):
        reg = EngineRegistry()
        reg.register(_make_desc("a", GDEMode.RECOVERY, timeout=20))
        reg.register(_make_desc("b", GDEMode.RECOVERY, requires=["a"], timeout=15))
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=reg)
        # Sequential: 20 + 15 = 35
        assert plan.estimated_duration_seconds == 35


# ---------------------------------------------------------------------------
# Default registry fallback
# ---------------------------------------------------------------------------


class TestDefaultRegistry:
    def test_uses_default_registry_when_none(self):
        # Should not raise even if default registry is empty
        plan = build_plan(_make_intent(GDEMode.RECOVERY), registry=None)
        assert isinstance(plan, ExecutionPlan)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_in_init(self):
        import genesis_architect.pro as pkg
        assert hasattr(pkg, "build_plan")

    def test_importable_directly(self):
        from genesis_architect.pro.gde_planner import build_plan as bp
        assert callable(bp)
