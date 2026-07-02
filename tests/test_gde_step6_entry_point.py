"""Tests for Step 6: decision_engine.py + __init__ exports."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from genesis_architect_pro.decision_engine import GenesisDecisionEngine, run_session
from genesis_architect_pro.engine_registry import EngineRegistry
from genesis_architect_pro.gde_types import (
    EngineCategory,
    EngineDescriptor,
    GDEMode,
    Intent,
    SessionReport,
)


# ---------------------------------------------------------------------------
# Fake engine helpers (same pattern as step 4 tests)
# ---------------------------------------------------------------------------


def _make_fake_module(name: str, fn) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.run = fn
    sys.modules[name] = mod
    return mod


def _success_fn(output: dict | None = None):
    def run(ctx):
        r = dict(output or {})
        r["_confidence"] = 1.0
        return r
    return run


def _make_desc(engine_id: str, mode: GDEMode, module_name: str) -> EngineDescriptor:
    return EngineDescriptor(
        id=engine_id,
        name=engine_id,
        module=module_name,
        entry_point="run",
        category=EngineCategory.ANALYSIS,
        input_keys=[],
        output_keys=[],
        modes=[mode],
    )


@pytest.fixture(autouse=True)
def cleanup_fake_modules():
    before = set(sys.modules.keys())
    yield
    for key in list(sys.modules.keys()):
        if key not in before:
            del sys.modules[key]


# ---------------------------------------------------------------------------
# GenesisDecisionEngine — basic construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_construction(self):
        gde = GenesisDecisionEngine()
        assert gde.project_dir == Path(".")

    def test_custom_project_dir(self, tmp_path):
        gde = GenesisDecisionEngine(project_dir=tmp_path)
        assert gde.project_dir == tmp_path

    def test_string_project_dir(self, tmp_path):
        gde = GenesisDecisionEngine(project_dir=str(tmp_path))
        assert gde.project_dir == tmp_path

    def test_custom_registry(self):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(registry=reg)
        assert gde.registry is reg


# ---------------------------------------------------------------------------
# classify_intent
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    def test_returns_intent(self):
        gde = GenesisDecisionEngine()
        intent = gde.classify_intent("scan the project for drift")
        assert isinstance(intent, Intent)
        assert intent.mode is GDEMode.RECOVERY

    def test_research_classified(self):
        gde = GenesisDecisionEngine()
        intent = gde.classify_intent("research FastAPI best practices")
        assert intent.mode is GDEMode.RESEARCH


# ---------------------------------------------------------------------------
# Full run — empty registry
# ---------------------------------------------------------------------------


class TestRunEmptyRegistry:
    def test_run_returns_session_report(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        report = gde.run("recover the project")
        assert isinstance(report, SessionReport)

    def test_report_mode_matches_input(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        report = gde.run("recover the project")
        assert report.mode is GDEMode.RECOVERY

    def test_report_has_session_id(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        report = gde.run("recover the project")
        assert report.session_id
        assert len(report.session_id) > 0

    def test_report_has_gate_report(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        report = gde.run("recover the project")
        assert report.gate_report is not None

    def test_report_has_decision_log(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        report = gde.run("recover the project")
        assert isinstance(report.decision_log, list)
        assert len(report.decision_log) > 0


# ---------------------------------------------------------------------------
# Full run — with engine
# ---------------------------------------------------------------------------


class TestRunWithEngine:
    def test_engine_result_in_report(self, tmp_path):
        _make_fake_module("fake.gde_eng", _success_fn({"result": "ok"}))
        reg = EngineRegistry()
        reg.register(_make_desc("gde_eng", GDEMode.RECOVERY, "fake.gde_eng"))
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg, parallel=False)
        report = gde.run("recover the project")
        assert "gde_eng" in report.engine_results

    def test_confidence_reported(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        report = gde.run("recover the project")
        assert 0.0 <= report.overall_confidence <= 1.0


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    def test_session_file_created(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        gde.run("recover the project")
        session_file = tmp_path / ".genesis" / "gde_session.json"
        assert session_file.exists()

    def test_decision_log_file_created(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        gde.run("recover the project")
        log_file = tmp_path / ".genesis" / "gde_decision_log.jsonl"
        assert log_file.exists()

    def test_resume_loads_saved_session(self, tmp_path):
        reg = EngineRegistry()
        gde = GenesisDecisionEngine(project_dir=tmp_path, registry=reg)
        report1 = gde.run("recover the project")
        report2 = gde.run("recover the project", resume=True)
        # Resumed session gets a new report but same session_id
        assert report2.session_id == report1.session_id


# ---------------------------------------------------------------------------
# run_session convenience function
# ---------------------------------------------------------------------------


class TestRunSession:
    def test_run_session_returns_report(self, tmp_path):
        reg = EngineRegistry()
        report = run_session("recover the project", project_dir=tmp_path, registry=reg)
        assert isinstance(report, SessionReport)

    def test_run_session_parallel_false(self, tmp_path):
        reg = EngineRegistry()
        report = run_session(
            "recover the project",
            project_dir=tmp_path,
            registry=reg,
            parallel=False,
        )
        assert isinstance(report, SessionReport)


# ---------------------------------------------------------------------------
# __init__ exports (Step 6 adds these)
# ---------------------------------------------------------------------------


class TestInitExports:
    def test_gde_in_init(self):
        import genesis_architect_pro as pkg
        assert hasattr(pkg, "GenesisDecisionEngine")

    def test_run_session_in_init(self):
        import genesis_architect_pro as pkg
        assert hasattr(pkg, "run_session")

    def test_classify_in_init(self):
        import genesis_architect_pro as pkg
        assert hasattr(pkg, "classify")

    def test_gde_types_in_init(self):
        import genesis_architect_pro as pkg
        for name in [
            "GDEMode", "LifecycleStage", "EngineCategory", "EngineStatus",
            "GateAction", "GateOutcome", "ApprovalChoice",
            "EngineDescriptor", "EngineResult", "WriteOperation",
            "GateResult", "GateReport", "ApprovalRequest", "ApprovalDecision",
            "CommitResult", "DecisionEntry", "Intent", "ExecutionPlan",
            "SessionContext", "SessionReport",
        ]:
            assert hasattr(pkg, name), f"Missing from __init__: {name}"

    def test_registry_in_init(self):
        import genesis_architect_pro as pkg
        assert hasattr(pkg, "EngineRegistry")
        assert hasattr(pkg, "RegistryError")
        assert hasattr(pkg, "get_default_registry")
        assert hasattr(pkg, "register")

    def test_session_fns_in_init(self):
        import genesis_architect_pro as pkg
        for name in ["save_session", "load_session", "delete_session",
                     "append_decision_log", "read_decision_log", "session_file_exists"]:
            assert hasattr(pkg, name), f"Missing from __init__: {name}"

    def test_planner_runner_gates_in_init(self):
        import genesis_architect_pro as pkg
        assert hasattr(pkg, "build_plan")
        assert hasattr(pkg, "run_plan")
        assert hasattr(pkg, "evaluate_gates")

    def test_existing_exports_still_present(self):
        import genesis_architect_pro as pkg
        for name in [
            "require_license", "LicenseError",
            "build_graph", "load_or_build",
            "score_project", "score_label",
            "detect_all", "classify_all",
        ]:
            assert hasattr(pkg, name), f"Regression: {name} missing from __init__"

    def test_gde_class_is_instantiable(self):
        from genesis_architect_pro import GenesisDecisionEngine
        gde = GenesisDecisionEngine()
        assert gde is not None
