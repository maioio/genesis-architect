"""Tests for the Knowledge Graph GDE adapter (additive production wiring).

Verifies the KG adapter honors the GDE contract, builds the graph from session
results, degrades gracefully, and registers into the default registry depending
on antipattern_detector — keeping the registry valid.
"""
from pathlib import Path

import pytest

from genesis_architect_pro.gde_knowledge_graph_adapter import (
    KNOWLEDGE_GRAPH_DESCRIPTOR, gde_run_knowledge_graph, register_knowledge_graph,
)
from genesis_architect_pro.engine_registry import EngineRegistry
from genesis_architect_pro.gde_types import (
    GDEMode, SessionContext, EngineResult, EngineStatus, LifecycleStage,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "core.py").write_text("import os\n\ndef pid():\n    return os.getpid()\n")
    return tmp_path


def _ctx(project: Path) -> SessionContext:
    return SessionContext(session_id="t", mode=GDEMode.RECOVERY,
                          stage=LifecycleStage.EXECUTE, project_dir=project)


class TestAdapter:
    def test_returns_dict_contract(self, project):
        out = gde_run_knowledge_graph(_ctx(project))
        assert isinstance(out, dict)
        assert isinstance(out.get("_confidence"), float)

    def test_builds_graph_file(self, project):
        out = gde_run_knowledge_graph(_ctx(project))
        assert "knowledge_graph_stats" in out
        # with no analysis inputs the graph may be empty but the call succeeds
        assert "graph_path" in out

    def test_consumes_antipattern_results(self, project):
        ctx = _ctx(project)
        ctx.engine_results["antipattern_detector"] = EngineResult(
            engine_id="antipattern_detector", status=EngineStatus.SUCCESS,
            output={"patterns": [{"name": "god_class", "module": "core",
                                  "confidence": 0.9}]})
        out = gde_run_knowledge_graph(ctx)
        assert out["knowledge_graph_stats"]["nodes"] >= 1
        assert (project / ".genesis" / "knowledge" / "graph.json").exists()

    def test_empty_inputs_do_not_fabricate(self, project):
        out = gde_run_knowledge_graph(_ctx(project))
        # no antipattern result in ctx -> graph has no fabricated nodes
        assert out["knowledge_graph_stats"]["nodes"] == 0
        assert out["_warnings"]


class TestRegistration:
    def test_descriptor_depends_on_antipattern(self):
        assert KNOWLEDGE_GRAPH_DESCRIPTOR.requires == ["antipattern_detector"]
        assert KNOWLEDGE_GRAPH_DESCRIPTOR.is_optional is True

    def test_register_requires_dependency(self):
        reg = EngineRegistry()
        # without antipattern in a *custom* registry the global helper still
        # targets the default registry; here we assert the descriptor is valid
        reg.register(KNOWLEDGE_GRAPH_DESCRIPTOR)
        # dependency missing in this isolated registry -> validate reports it
        errors = reg.validate()
        assert any("antipattern_detector" in e for e in errors)

    def test_explicit_registration_into_default_registry(self):
        # KG is opt-in: it registers only when explicitly requested, and then
        # the default registry still validates clean (its dependency is present).
        from genesis_architect_pro.engine_registry import get_default_registry
        reg = get_default_registry()
        had_it = "knowledge_graph" in reg
        try:
            register_knowledge_graph()  # idempotent; pulls in core deps
            assert "knowledge_graph" in reg
            assert reg.validate() == []
        finally:
            # leave the shared default registry as we found it
            if not had_it:
                reg.unregister("knowledge_graph")
