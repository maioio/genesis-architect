"""Tests for engine_adapters - wiring real engines into the GDE.

Verifies adapters honor the GDE contract (fn(ctx)->dict), degrade gracefully,
register cleanly into the real EngineRegistry, and run end-to-end through the
real gde_runner without raising.
"""
from pathlib import Path

import pytest

from genesis_architect_pro.engine_adapters import (
    ADAPTERS, BUILTIN_DESCRIPTORS, register_builtin_engines,
    architecture_adapter, antipattern_adapter, recovery_adapter,
    security_adapter, knowledge_graph_adapter,
)
from genesis_architect_pro.engine_registry import EngineRegistry
from genesis_architect_pro.gde_types import (
    EngineDescriptor, GDEMode, SessionContext, EngineStatus, LifecycleStage,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "core.py").write_text(
        "import os\n\ndef pid():\n    return os.getpid()\n")
    (src / "util.py").write_text(
        "from demo.core import pid\n\ndef wrap():\n    return pid()\n")
    return tmp_path


def _ctx(project: Path, mode: GDEMode = GDEMode.RECOVERY) -> SessionContext:
    return SessionContext(session_id="t", mode=mode,
                          stage=LifecycleStage.EXECUTE, project_dir=project)


class TestAdapterContract:
    def test_all_adapters_return_dict(self, project):
        ctx = _ctx(project)
        for name, fn in ADAPTERS.items():
            out = fn(ctx)
            assert isinstance(out, dict), name
            # contract: confidence is a float when present
            if "_confidence" in out:
                assert isinstance(out["_confidence"], float)

    def test_architecture_adapter_scores(self, project):
        out = architecture_adapter(_ctx(project))
        assert "architecture_score" in out
        assert 0.0 <= out["architecture_score"] <= 100.0
        assert "architecture_label" in out

    def test_antipattern_adapter_counts(self, project):
        out = antipattern_adapter(_ctx(project))
        assert "anti_pattern_count" in out
        assert out["anti_pattern_count"] >= 0

    def test_security_adapter_returns_docs(self, project):
        out = security_adapter(_ctx(project))
        assert "security_docs" in out or out.get("available") is False

    def test_recovery_adapter_runs(self, project):
        out = recovery_adapter(_ctx(project))
        assert "recovery_report" in out or out.get("available") is False


class TestGracefulDegradation:
    def test_adapter_degrades_on_empty_project(self, tmp_path):
        # empty dir: adapters must not raise; they degrade or return a result
        ctx = _ctx(tmp_path)
        for name, fn in ADAPTERS.items():
            out = fn(ctx)
            assert isinstance(out, dict), name

    def test_degraded_payload_shape(self, tmp_path):
        # architecture on a dir with no analyzable code still returns a dict
        out = architecture_adapter(_ctx(tmp_path))
        assert isinstance(out, dict)
        if out.get("available") is False:
            assert out["_confidence"] <= 0.3
            assert out["_warnings"]


class TestKnowledgeGraphAdapter:
    def test_builds_graph_from_session_results(self, project):
        ctx = _ctx(project)
        # seed an antipattern result into the context, as the runner would
        ap_out = antipattern_adapter(ctx)
        from genesis_architect_pro.gde_types import EngineResult
        ctx.engine_results["antipattern"] = EngineResult(
            engine_id="antipattern", status=EngineStatus.SUCCESS, output=ap_out)
        out = knowledge_graph_adapter(ctx)
        assert "knowledge_graph_stats" in out or out.get("available") is False
        # the graph file should exist after a successful build
        if "knowledge_graph_stats" in out:
            assert (project / ".genesis" / "knowledge" / "graph.json").exists()


class TestRegistration:
    def test_register_builtin_into_real_registry(self):
        reg = EngineRegistry()
        ids = register_builtin_engines(reg)
        assert set(ids) == {d.id for d in BUILTIN_DESCRIPTORS}
        assert "architecture" in reg and "knowledge_graph" in reg

    def test_register_is_idempotent(self):
        reg = EngineRegistry()
        register_builtin_engines(reg)
        # second call without replace does not raise and registers nothing new
        again = register_builtin_engines(reg)
        assert again == []

    def test_register_replace(self):
        reg = EngineRegistry()
        register_builtin_engines(reg)
        ids = register_builtin_engines(reg, replace=True)
        assert "architecture" in ids

    def test_registry_validates_clean(self):
        reg = EngineRegistry()
        register_builtin_engines(reg)
        assert reg.validate() == []  # deps satisfied, no cycles

    def test_recovery_mode_ordering_respects_deps(self):
        reg = EngineRegistry()
        register_builtin_engines(reg)
        ordered = [d.id for d in reg.ordered_for_mode(GDEMode.RECOVERY)]
        # recovery requires architecture -> architecture comes first
        assert ordered.index("architecture") < ordered.index("recovery")
        # knowledge_graph requires antipattern
        assert ordered.index("antipattern") < ordered.index("knowledge_graph")


class TestEndToEnd:
    def test_full_run_through_real_runner(self, project):
        from genesis_architect_pro.gde_planner import build_plan
        from genesis_architect_pro.gde_runner import run_plan
        from genesis_architect_pro.gde_types import Intent

        reg = EngineRegistry()
        register_builtin_engines(reg)
        intent = Intent(raw_text="recover this project", mode=GDEMode.RECOVERY,
                        confidence=0.9, signals=[], clarifying_questions=[],
                        params={})
        ctx = _ctx(project, GDEMode.RECOVERY)
        ctx.intent = intent
        plan = build_plan(intent, reg)
        result_ctx = run_plan(plan, ctx, parallel=False)

        # every engine in the plan produced a result; nothing raised
        assert "architecture" in result_ctx.engine_results
        arch = result_ctx.engine_results["architecture"]
        assert arch.status in (EngineStatus.SUCCESS, EngineStatus.DEGRADED)
