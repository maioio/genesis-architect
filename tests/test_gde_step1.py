"""Step 1 tests — GDE types, engine registry, and session persistence.

Coverage targets:
  - All enumerations are complete and str-compatible
  - EngineDescriptor validates its own invariants
  - EngineResult validates confidence range
  - GateReport.recompute_overall() correct for all combinations
  - SessionContext: record, apply_confidence_penalty, merge_engine_result
  - EngineRegistry: register, replace, unregister, get, require, all, for_mode
  - EngineRegistry: validate — missing dep, cycle detection
  - EngineRegistry: ordered_for_mode — topological order
  - EngineRegistry: parallel_groups_for_mode — level grouping
  - gde_session: save/load roundtrip, delete, decision log append/read
  - Backward compatibility: existing __init__ exports unchanged
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis_architect_pro.gde_types import (
    ApprovalChoice,
    DecisionEntry,
    EngineCategory,
    EngineDescriptor,
    EngineResult,
    EngineStatus,
    GateAction,
    GateOutcome,
    GateReport,
    GateResult,
    GDEMode,
    LifecycleStage,
    SessionContext,
    WriteOperation,
)
from genesis_architect_pro.engine_registry import (
    EngineRegistry,
    RegistryError,
    get_default_registry,
)
from genesis_architect_pro import gde_session as sess_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_descriptor(
    engine_id: str = "test-engine",
    requires: list[str] | None = None,
    modes: list[GDEMode] | None = None,
    is_optional: bool = True,
    write_ops: list[str] | None = None,
    handoffs: list[str] | None = None,
) -> EngineDescriptor:
    return EngineDescriptor(
        id=engine_id,
        name=f"Test Engine {engine_id}",
        module=f"genesis_architect_pro.{engine_id.replace('-', '_')}",
        entry_point="run",
        category=EngineCategory.ANALYSIS,
        input_keys=["import_graph"],
        output_keys=["result"],
        requires=requires or [],
        handoffs=handoffs or [],
        is_optional=is_optional,
        write_operations=write_ops or [],
        modes=modes or [GDEMode.RECOVERY],
    )


def _make_engine_result(engine_id: str = "test-engine", status: EngineStatus = EngineStatus.SUCCESS) -> EngineResult:
    return EngineResult(
        engine_id=engine_id,
        status=status,
        output={"result": 42},
        confidence=0.9,
    )


def _make_decision_entry(session_id: str = "sess-1") -> DecisionEntry:
    return DecisionEntry(
        session_id=session_id,
        timestamp="2026-06-28T12:00:00Z",
        stage=LifecycleStage.EXECUTE,
        decision_type="ENGINE_INVOKED",
        actor="gde",
        subject="test-engine",
        detail="Engine started",
        confidence_before=0.9,
        confidence_after=0.9,
        outcome="running",
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnumerations:
    def test_gde_mode_values(self) -> None:
        values = {m.value for m in GDEMode}
        assert values == {"recovery", "research", "refactor", "gate", "build", "document", "committee"}

    def test_lifecycle_stage_values(self) -> None:
        expected = {"idle", "intake", "plan", "execute", "gate", "report", "approve", "commit",
                    "degraded", "blocked", "suspended", "rollback"}
        assert {s.value for s in LifecycleStage} == expected

    def test_engine_category_values(self) -> None:
        expected = {"analysis", "persistence", "report", "research", "gate", "memory"}
        assert {c.value for c in EngineCategory} == expected

    def test_engine_status_values(self) -> None:
        assert {s.value for s in EngineStatus} == {"success", "degraded", "failed", "skipped"}

    def test_gate_action_values(self) -> None:
        assert {a.value for a in GateAction} == {"pass", "warn", "block_ask", "hard_block"}

    def test_gate_outcome_values(self) -> None:
        assert {o.value for o in GateOutcome} == {"pass", "warn", "block", "hard_block"}

    def test_approval_choice_values(self) -> None:
        assert {c.value for c in ApprovalChoice} == {"approve", "reject", "defer", "partial"}

    def test_modes_are_str_compatible(self) -> None:
        assert GDEMode.RECOVERY == "recovery"
        assert LifecycleStage.EXECUTE == "execute"


# ---------------------------------------------------------------------------
# EngineDescriptor tests
# ---------------------------------------------------------------------------


class TestEngineDescriptor:
    def test_valid_descriptor_creates(self) -> None:
        d = _make_descriptor()
        assert d.id == "test-engine"
        assert d.category == EngineCategory.ANALYSIS
        assert d.timeout_seconds == 60

    def test_empty_id_raises(self) -> None:
        with pytest.raises(ValueError, match="id must not be empty"):
            EngineDescriptor(
                id="", name="X", module="m", entry_point="run",
                category=EngineCategory.ANALYSIS,
                input_keys=[], output_keys=[],
            )

    def test_whitespace_id_raises(self) -> None:
        with pytest.raises(ValueError, match="id must not be empty"):
            EngineDescriptor(
                id="   ", name="X", module="m", entry_point="run",
                category=EngineCategory.ANALYSIS,
                input_keys=[], output_keys=[],
            )

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name must not be empty"):
            EngineDescriptor(
                id="x", name="", module="m", entry_point="run",
                category=EngineCategory.ANALYSIS,
                input_keys=[], output_keys=[],
            )

    def test_empty_module_raises(self) -> None:
        with pytest.raises(ValueError, match="module must not be empty"):
            EngineDescriptor(
                id="x", name="X", module="", entry_point="run",
                category=EngineCategory.ANALYSIS,
                input_keys=[], output_keys=[],
            )

    def test_empty_entry_point_raises(self) -> None:
        with pytest.raises(ValueError, match="entry_point must not be empty"):
            EngineDescriptor(
                id="x", name="X", module="m", entry_point="",
                category=EngineCategory.ANALYSIS,
                input_keys=[], output_keys=[],
            )

    def test_zero_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            EngineDescriptor(
                id="x", name="X", module="m", entry_point="run",
                category=EngineCategory.ANALYSIS,
                input_keys=[], output_keys=[],
                timeout_seconds=0,
            )

    def test_negative_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            EngineDescriptor(
                id="x", name="X", module="m", entry_point="run",
                category=EngineCategory.ANALYSIS,
                input_keys=[], output_keys=[],
                timeout_seconds=-5,
            )

    def test_invalid_category_type_raises(self) -> None:
        with pytest.raises(TypeError, match="category must be EngineCategory"):
            EngineDescriptor(
                id="x", name="X", module="m", entry_point="run",
                category="analysis",  # type: ignore[arg-type]
                input_keys=[], output_keys=[],
            )

    def test_default_fields(self) -> None:
        d = _make_descriptor()
        assert d.requires == []
        assert d.write_operations == []
        assert d.is_optional is True


# ---------------------------------------------------------------------------
# EngineResult tests
# ---------------------------------------------------------------------------


class TestEngineResult:
    def test_valid_result_creates(self) -> None:
        r = _make_engine_result()
        assert r.engine_id == "test-engine"
        assert r.status == EngineStatus.SUCCESS
        assert r.confidence == 0.9

    def test_confidence_above_1_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            EngineResult(engine_id="x", status=EngineStatus.SUCCESS, confidence=1.1)

    def test_confidence_below_0_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            EngineResult(engine_id="x", status=EngineStatus.SUCCESS, confidence=-0.1)

    def test_confidence_at_boundaries_ok(self) -> None:
        EngineResult(engine_id="x", status=EngineStatus.SUCCESS, confidence=0.0)
        EngineResult(engine_id="x", status=EngineStatus.SUCCESS, confidence=1.0)

    def test_error_field_on_failure(self) -> None:
        r = EngineResult(engine_id="x", status=EngineStatus.FAILED, error="boom", confidence=0.0)
        assert r.error == "boom"


# ---------------------------------------------------------------------------
# GateReport tests
# ---------------------------------------------------------------------------


class TestGateReport:
    def _gate(self, action: GateAction) -> GateResult:
        return GateResult(
            gate_id="g", action=action, override_allowed=True,
            title="T", reason="R",
        )

    def test_all_pass(self) -> None:
        r = GateReport(passed=[self._gate(GateAction.PASS)])
        r.recompute_overall()
        assert r.overall == GateOutcome.PASS

    def test_warn_beats_pass(self) -> None:
        r = GateReport(
            passed=[self._gate(GateAction.PASS)],
            warnings=[self._gate(GateAction.WARN)],
        )
        r.recompute_overall()
        assert r.overall == GateOutcome.WARN

    def test_block_beats_warn(self) -> None:
        r = GateReport(
            warnings=[self._gate(GateAction.WARN)],
            blocks=[self._gate(GateAction.BLOCK_AND_ASK)],
        )
        r.recompute_overall()
        assert r.overall == GateOutcome.BLOCK

    def test_hard_block_beats_block(self) -> None:
        r = GateReport(
            blocks=[self._gate(GateAction.BLOCK_AND_ASK)],
            hard_blocks=[self._gate(GateAction.HARD_BLOCK)],
        )
        r.recompute_overall()
        assert r.overall == GateOutcome.HARD_BLOCK

    def test_empty_report_is_pass(self) -> None:
        r = GateReport()
        r.recompute_overall()
        assert r.overall == GateOutcome.PASS


# ---------------------------------------------------------------------------
# SessionContext tests
# ---------------------------------------------------------------------------


class TestSessionContext:
    def test_default_creates(self) -> None:
        ctx = SessionContext()
        assert ctx.stage == LifecycleStage.IDLE
        assert ctx.overall_confidence == 1.0
        assert ctx.engine_results == {}
        assert ctx.decision_log == []

    def test_session_id_is_unique(self) -> None:
        a = SessionContext()
        b = SessionContext()
        assert a.session_id != b.session_id

    def test_record_appends_entry(self) -> None:
        ctx = SessionContext()
        entry = _make_decision_entry(ctx.session_id)
        ctx.record(entry)
        assert len(ctx.decision_log) == 1
        assert ctx.decision_log[0].subject == "test-engine"

    def test_apply_confidence_penalty_basic(self) -> None:
        ctx = SessionContext()
        ctx.apply_confidence_penalty(0.20)
        assert abs(ctx.overall_confidence - 0.80) < 1e-9

    def test_apply_confidence_penalty_floor(self) -> None:
        ctx = SessionContext()
        ctx.apply_confidence_penalty(0.99)
        assert ctx.overall_confidence == 0.10

    def test_apply_confidence_penalty_ceiling_does_not_exceed_1(self) -> None:
        ctx = SessionContext()
        ctx.apply_confidence_penalty(-0.50)  # negative penalty = boost, still capped
        assert ctx.overall_confidence == 1.00

    def test_merge_engine_result(self) -> None:
        ctx = SessionContext()
        result = _make_engine_result("arch-scorer")
        ctx.merge_engine_result(result)
        assert "arch-scorer" in ctx.engine_results
        assert ctx.engine_results["arch-scorer"].output == {"result": 42}

    def test_merge_overwrites_same_engine(self) -> None:
        ctx = SessionContext()
        ctx.merge_engine_result(_make_engine_result("x"))
        ctx.merge_engine_result(EngineResult(engine_id="x", status=EngineStatus.FAILED, confidence=0.0))
        assert ctx.engine_results["x"].status == EngineStatus.FAILED


# ---------------------------------------------------------------------------
# EngineRegistry tests
# ---------------------------------------------------------------------------


class TestEngineRegistry:
    def test_register_and_get(self) -> None:
        reg = EngineRegistry()
        d = _make_descriptor("e1")
        reg.register(d)
        assert reg.get("e1") is d

    def test_get_unknown_returns_none(self) -> None:
        reg = EngineRegistry()
        assert reg.get("nope") is None

    def test_require_unknown_raises(self) -> None:
        reg = EngineRegistry()
        with pytest.raises(RegistryError, match="not registered"):
            reg.require("nope")

    def test_duplicate_register_raises(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("e1"))
        with pytest.raises(RegistryError, match="already registered"):
            reg.register(_make_descriptor("e1"))

    def test_replace_overwrites(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("e1"))
        d2 = _make_descriptor("e1")
        d2.name = "Replaced"
        reg.replace(d2)
        assert reg.get("e1").name == "Replaced"

    def test_unregister_removes(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("e1"))
        reg.unregister("e1")
        assert reg.get("e1") is None

    def test_unregister_nonexistent_is_noop(self) -> None:
        reg = EngineRegistry()
        reg.unregister("ghost")  # no exception

    def test_len(self) -> None:
        reg = EngineRegistry()
        assert len(reg) == 0
        reg.register(_make_descriptor("e1"))
        assert len(reg) == 1

    def test_contains(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("e1"))
        assert "e1" in reg
        assert "e2" not in reg

    def test_all_returns_all(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a"))
        reg.register(_make_descriptor("b"))
        ids = [d.id for d in reg.all()]
        assert set(ids) == {"a", "b"}

    def test_ids(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("x"))
        reg.register(_make_descriptor("y"))
        assert "x" in reg.ids()
        assert "y" in reg.ids()

    def test_for_mode_filters_correctly(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("rec", modes=[GDEMode.RECOVERY]))
        reg.register(_make_descriptor("res", modes=[GDEMode.RESEARCH]))
        reg.register(_make_descriptor("both", modes=[GDEMode.RECOVERY, GDEMode.RESEARCH]))
        recovery_ids = {d.id for d in reg.for_mode(GDEMode.RECOVERY)}
        assert recovery_ids == {"rec", "both"}

    def test_for_mode_empty_when_none_match(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("e", modes=[GDEMode.RECOVERY]))
        assert reg.for_mode(GDEMode.BUILD) == []

    def test_non_descriptor_register_raises(self) -> None:
        reg = EngineRegistry()
        with pytest.raises(TypeError):
            reg.register("not-a-descriptor")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# EngineRegistry validation tests
# ---------------------------------------------------------------------------


class TestEngineRegistryValidation:
    def test_valid_registry_no_errors(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a"))
        reg.register(_make_descriptor("b", requires=["a"]))
        assert reg.validate() == []

    def test_missing_dependency_reported(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("b", requires=["ghost"]))
        errors = reg.validate()
        assert any("ghost" in e for e in errors)

    def test_simple_cycle_detected(self) -> None:
        reg = EngineRegistry()
        # a requires b, b requires a
        reg.register(_make_descriptor("a", requires=["b"]))
        reg.register(_make_descriptor("b", requires=["a"]))
        errors = reg.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_three_way_cycle_detected(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", requires=["c"]))
        reg.register(_make_descriptor("b", requires=["a"]))
        reg.register(_make_descriptor("c", requires=["b"]))
        errors = reg.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_validate_strict_raises_on_error(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("b", requires=["missing"]))
        with pytest.raises(RegistryError):
            reg.validate_strict()

    def test_validate_strict_passes_on_valid(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a"))
        reg.validate_strict()  # no exception

    def test_empty_registry_valid(self) -> None:
        reg = EngineRegistry()
        assert reg.validate() == []


# ---------------------------------------------------------------------------
# Handoffs — the forward edge
# ---------------------------------------------------------------------------


class TestEngineHandoffs:
    """`handoffs` is advisory: existence-checked, deliberately cycle-exempt."""

    def test_defaults_to_empty(self) -> None:
        assert _make_descriptor("a").handoffs == []

    def test_valid_handoff_passes(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", handoffs=["b"]))
        reg.register(_make_descriptor("b"))
        assert reg.validate() == []

    def test_dangling_handoff_reported(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", handoffs=["ghost"]))
        errors = reg.validate()
        assert any("ghost" in e and "hands off" in e for e in errors)

    def test_self_handoff_reported(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", handoffs=["a"]))
        errors = reg.validate()
        assert any("itself" in e for e in errors)

    def test_multiple_dangling_handoffs_all_reported(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", handoffs=["ghost1", "ghost2"]))
        errors = reg.validate()
        assert sum(1 for e in errors if "hands off" in e) == 2

    def test_handoff_cycle_is_allowed(self) -> None:
        """The load-bearing design test.

        analyse → decide → re-analyse is a legitimate iterative workflow, so a
        cycle in the FORWARD edge must not be an error — unlike the same shape
        in `requires`, which is an ordering constraint and must stay acyclic.
        """
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", handoffs=["b"]))
        reg.register(_make_descriptor("b", handoffs=["a"]))
        assert reg.validate() == []

    def test_requires_cycle_still_detected_alongside_handoffs(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", requires=["b"], handoffs=["b"]))
        reg.register(_make_descriptor("b", requires=["a"]))
        errors = reg.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_handoffs_do_not_affect_execution_order(self) -> None:
        reg = EngineRegistry()
        # b hands off to a, but requires nothing — ordering must ignore that.
        reg.register(_make_descriptor("a"))
        reg.register(_make_descriptor("b", handoffs=["a"]))
        ordered = [d.id for d in reg.ordered_for_mode(GDEMode.RECOVERY)]
        assert set(ordered) == {"a", "b"}

    def test_handoffs_do_not_affect_parallel_groups(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", handoffs=["b"]))
        reg.register(_make_descriptor("b", handoffs=["a"]))
        groups = reg.parallel_groups_for_mode(GDEMode.RECOVERY)
        # No `requires` between them, so they stay in one parallel phase.
        assert len(groups) == 1
        assert {d.id for d in groups[0]} == {"a", "b"}

    def test_validate_strict_raises_on_dangling_handoff(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", handoffs=["ghost"]))
        with pytest.raises(RegistryError):
            reg.validate_strict()

    def test_production_registry_handoffs_are_valid(self) -> None:
        """Whatever the real registry declares must actually resolve."""
        import genesis_architect_pro.gde_engine_registration  # noqa: F401
        from genesis_architect_pro.engine_registry import get_default_registry

        errors = [e for e in get_default_registry().validate() if "hands off" in e]
        assert errors == []


# ---------------------------------------------------------------------------
# EngineRegistry topological sort tests
# ---------------------------------------------------------------------------


class TestEngineRegistryTopologicalSort:
    def test_independent_engines_any_order(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a"))
        reg.register(_make_descriptor("b"))
        ordered = reg.ordered_for_mode(GDEMode.RECOVERY)
        assert {d.id for d in ordered} == {"a", "b"}

    def test_dependency_comes_first(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a"))
        reg.register(_make_descriptor("b", requires=["a"]))
        ordered = reg.ordered_for_mode(GDEMode.RECOVERY)
        ids = [d.id for d in ordered]
        assert ids.index("a") < ids.index("b")

    def test_chain_dependency_order(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("c", requires=["b"]))
        reg.register(_make_descriptor("b", requires=["a"]))
        reg.register(_make_descriptor("a"))
        ordered = reg.ordered_for_mode(GDEMode.RECOVERY)
        ids = [d.id for d in ordered]
        assert ids.index("a") < ids.index("b") < ids.index("c")

    def test_cycle_raises_on_ordered(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", requires=["b"]))
        reg.register(_make_descriptor("b", requires=["a"]))
        with pytest.raises(RegistryError, match="cycle"):
            reg.ordered_for_mode(GDEMode.RECOVERY)

    def test_empty_mode_returns_empty(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", modes=[GDEMode.RESEARCH]))
        assert reg.ordered_for_mode(GDEMode.BUILD) == []

    def test_only_mode_engines_included(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a", modes=[GDEMode.RECOVERY]))
        reg.register(_make_descriptor("b", modes=[GDEMode.RESEARCH]))
        ordered = reg.ordered_for_mode(GDEMode.RECOVERY)
        assert [d.id for d in ordered] == ["a"]


# ---------------------------------------------------------------------------
# EngineRegistry parallel groups tests
# ---------------------------------------------------------------------------


class TestEngineRegistryParallelGroups:
    def test_independent_engines_in_one_group(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a"))
        reg.register(_make_descriptor("b"))
        groups = reg.parallel_groups_for_mode(GDEMode.RECOVERY)
        assert len(groups) == 1
        assert {d.id for d in groups[0]} == {"a", "b"}

    def test_dependent_engine_in_next_group(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a"))
        reg.register(_make_descriptor("b"))
        reg.register(_make_descriptor("c", requires=["a", "b"]))
        groups = reg.parallel_groups_for_mode(GDEMode.RECOVERY)
        assert len(groups) == 2
        group0_ids = {d.id for d in groups[0]}
        group1_ids = {d.id for d in groups[1]}
        assert {"a", "b"} == group0_ids
        assert {"c"} == group1_ids

    def test_chain_is_three_groups(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("a"))
        reg.register(_make_descriptor("b", requires=["a"]))
        reg.register(_make_descriptor("c", requires=["b"]))
        groups = reg.parallel_groups_for_mode(GDEMode.RECOVERY)
        assert len(groups) == 3

    def test_empty_mode_returns_empty_list(self) -> None:
        reg = EngineRegistry()
        assert reg.parallel_groups_for_mode(GDEMode.BUILD) == []

    def test_single_engine_one_group(self) -> None:
        reg = EngineRegistry()
        reg.register(_make_descriptor("solo"))
        groups = reg.parallel_groups_for_mode(GDEMode.RECOVERY)
        assert len(groups) == 1
        assert groups[0][0].id == "solo"


# ---------------------------------------------------------------------------
# gde_session persistence tests
# ---------------------------------------------------------------------------


class TestGdeSessionPersistence:
    def _make_ctx(self) -> SessionContext:
        ctx = SessionContext()
        ctx.mode = GDEMode.RECOVERY
        ctx.stage = LifecycleStage.EXECUTE
        ctx.project_dir = Path("/fake/project")
        ctx.overall_confidence = 0.75
        ctx.project_risk_level = "medium"
        ctx.merge_engine_result(_make_engine_result("arch-scorer"))
        ctx.record(_make_decision_entry(ctx.session_id))
        return ctx

    def test_save_creates_file(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        sess_mod.save_session(ctx, tmp_path)
        assert (tmp_path / ".genesis" / "gde_session.json").exists()

    def test_load_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert sess_mod.load_session(tmp_path) is None

    def test_save_load_roundtrip_basic_fields(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        sess_mod.save_session(ctx, tmp_path)
        loaded = sess_mod.load_session(tmp_path)
        assert loaded is not None
        assert loaded.session_id == ctx.session_id
        assert loaded.mode == GDEMode.RECOVERY
        assert loaded.stage == LifecycleStage.EXECUTE
        assert abs(loaded.overall_confidence - 0.75) < 1e-9
        assert loaded.project_risk_level == "medium"

    def test_save_load_engine_results(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        sess_mod.save_session(ctx, tmp_path)
        loaded = sess_mod.load_session(tmp_path)
        assert "arch-scorer" in loaded.engine_results
        assert loaded.engine_results["arch-scorer"].status == EngineStatus.SUCCESS

    def test_save_load_decision_log(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        sess_mod.save_session(ctx, tmp_path)
        loaded = sess_mod.load_session(tmp_path)
        assert len(loaded.decision_log) == 1
        assert loaded.decision_log[0].decision_type == "ENGINE_INVOKED"

    def test_delete_removes_file(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        sess_mod.save_session(ctx, tmp_path)
        sess_mod.delete_session(tmp_path)
        assert not (tmp_path / ".genesis" / "gde_session.json").exists()

    def test_delete_nonexistent_is_noop(self, tmp_path: Path) -> None:
        sess_mod.delete_session(tmp_path)  # no exception

    def test_session_file_exists(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        assert not sess_mod.session_file_exists(tmp_path)
        sess_mod.save_session(ctx, tmp_path)
        assert sess_mod.session_file_exists(tmp_path)

    def test_load_corrupt_file_returns_none(self, tmp_path: Path) -> None:
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "gde_session.json").write_text("not json", encoding="utf-8")
        assert sess_mod.load_session(tmp_path) is None

    def test_save_is_atomic(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        sess_mod.save_session(ctx, tmp_path)
        # Overwrite with new data — old .tmp must not remain
        ctx.project_risk_level = "high"
        sess_mod.save_session(ctx, tmp_path)
        tmp = tmp_path / ".genesis" / "gde_session.tmp"
        assert not tmp.exists()
        loaded = sess_mod.load_session(tmp_path)
        assert loaded.project_risk_level == "high"

    def test_save_creates_genesis_dir(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        assert not (tmp_path / ".genesis").exists()
        sess_mod.save_session(ctx, tmp_path)
        assert (tmp_path / ".genesis").exists()

    def test_load_preserves_pending_write_operations(self, tmp_path: Path) -> None:
        ctx = self._make_ctx()
        ctx.pending_write_operations.append(
            WriteOperation(
                engine_id="model-store",
                operation_id="op-1",
                description="Write model.json",
                target_path=".genesis/model.json",
            )
        )
        sess_mod.save_session(ctx, tmp_path)
        loaded = sess_mod.load_session(tmp_path)
        assert len(loaded.pending_write_operations) == 1
        assert loaded.pending_write_operations[0].operation_id == "op-1"


# ---------------------------------------------------------------------------
# Decision log tests
# ---------------------------------------------------------------------------


class TestDecisionLog:
    def test_append_and_read(self, tmp_path: Path) -> None:
        entry = _make_decision_entry("sess-abc")
        sess_mod.append_decision_log(entry, tmp_path)
        entries = sess_mod.read_decision_log(tmp_path)
        assert len(entries) == 1
        assert entries[0].session_id == "sess-abc"

    def test_read_empty_when_no_file(self, tmp_path: Path) -> None:
        assert sess_mod.read_decision_log(tmp_path) == []

    def test_multiple_entries_appended(self, tmp_path: Path) -> None:
        for i in range(5):
            sess_mod.append_decision_log(_make_decision_entry(f"sess-{i}"), tmp_path)
        entries = sess_mod.read_decision_log(tmp_path)
        assert len(entries) == 5

    def test_corrupt_line_skipped(self, tmp_path: Path) -> None:
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        log = genesis / "gde_decision_log.jsonl"
        _make_decision_entry("sess-good")
        # Write one good + one bad line
        log.write_text(
            json.dumps({
                "session_id": "sess-good",
                "timestamp": "2026-06-28T12:00:00Z",
                "stage": "execute",
                "decision_type": "ENGINE_INVOKED",
                "actor": "gde",
                "subject": "x",
                "detail": "",
                "confidence_before": 0.9,
                "confidence_after": 0.9,
                "outcome": "ok",
            }) + "\n" + "CORRUPT LINE\n",
            encoding="utf-8",
        )
        entries = sess_mod.read_decision_log(tmp_path)
        assert len(entries) == 1
        assert entries[0].session_id == "sess-good"

    def test_append_creates_genesis_dir(self, tmp_path: Path) -> None:
        assert not (tmp_path / ".genesis").exists()
        sess_mod.append_decision_log(_make_decision_entry(), tmp_path)
        assert (tmp_path / ".genesis" / "gde_decision_log.jsonl").exists()

    def test_decision_log_is_append_only(self, tmp_path: Path) -> None:
        e1 = _make_decision_entry("s1")
        e2 = _make_decision_entry("s2")
        sess_mod.append_decision_log(e1, tmp_path)
        sess_mod.append_decision_log(e2, tmp_path)
        entries = sess_mod.read_decision_log(tmp_path)
        assert entries[0].session_id == "s1"
        assert entries[1].session_id == "s2"


# ---------------------------------------------------------------------------
# Default registry tests
# ---------------------------------------------------------------------------


class TestDefaultRegistry:
    def test_get_default_registry_returns_same_instance(self) -> None:
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2

    def test_default_registry_is_engine_registry(self) -> None:
        assert isinstance(get_default_registry(), EngineRegistry)


# ---------------------------------------------------------------------------
# Backward compatibility: existing __init__ exports unchanged
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_existing_exports_importable(self) -> None:
        from genesis_architect_pro import (
            compute_drift_score,
            generate_report,
            generate_report_for_project,
        )
        # Spot-check a few are callable
        assert callable(generate_report)
        assert callable(generate_report_for_project)
        assert callable(compute_drift_score)

    def test_gde_types_in_init(self) -> None:
        # Step 6 added GenesisDecisionEngine to __init__.
        import genesis_architect_pro as pkg
        assert hasattr(pkg, "GenesisDecisionEngine")

    def test_new_modules_importable_directly(self) -> None:
        from genesis_architect_pro import gde_types, engine_registry, gde_session
        assert hasattr(gde_types, "GDEMode")
        assert hasattr(engine_registry, "EngineRegistry")
        assert hasattr(gde_session, "save_session")
