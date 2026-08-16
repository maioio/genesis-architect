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
from genesis_architect_pro.knowledge_graph import load_graph as kg_load
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


class TestTestCoverageWiring:
    def test_fragility_classifier_results_produce_test_nodes(self, project):
        ctx = _ctx(project)
        ctx.engine_results["fragility_classifier"] = EngineResult(
            engine_id="fragility_classifier", status=EngineStatus.SUCCESS,
            output={"fragility_map": [
                {"module": "src/demo/core.py", "has_test": True, "status": "STABLE"},
            ]})
        gde_run_knowledge_graph(ctx)
        assert (project / ".genesis" / "knowledge" / "graph.json").exists()
        graph = kg_load(project)
        assert graph.query(["test", "covers", "module"])

    def test_no_fragility_result_adds_no_test_nodes(self, project):
        gde_run_knowledge_graph(_ctx(project))
        graph = kg_load(project)
        assert graph.query(["test", "covers", "module"]) == []


class TestSecurityRiskWiring:
    """CVE data needs a network call per dependency (OSV.dev) — only worth
    the latency under GATE mode; risk data (fragility_classifier) is local
    and fast, so it's wired in on every mode."""

    def test_recovery_mode_never_calls_cve_scan(self, project, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "genesis_architect_pro.dependency_scanner.scan_dependency_cves",
            lambda *a, **k: calls.append(a) or [],
        )
        ctx = _ctx(project)  # RECOVERY mode
        gde_run_knowledge_graph(ctx)
        assert calls == []

    def test_gate_mode_calls_cve_scan(self, project, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "genesis_architect_pro.dependency_scanner.scan_dependency_cves",
            lambda *a, **k: calls.append(a) or [],
        )
        ctx = SessionContext(session_id="t", mode=GDEMode.GATE,
                             stage=LifecycleStage.EXECUTE, project_dir=project)
        gde_run_knowledge_graph(ctx)
        assert len(calls) == 1

    def test_cve_scan_failure_degrades_gracefully(self, project, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("OSV unreachable")
        monkeypatch.setattr(
            "genesis_architect_pro.dependency_scanner.scan_dependency_cves", boom)
        ctx = SessionContext(session_id="t", mode=GDEMode.GATE,
                             stage=LifecycleStage.EXECUTE, project_dir=project)
        out = gde_run_knowledge_graph(ctx)  # must not raise
        assert isinstance(out, dict)

    def test_do_not_touch_hits_surfaced_as_warnings(self, project, monkeypatch):
        monkeypatch.setattr(
            "genesis_architect_pro.dependency_scanner.scan_dependency_cves",
            lambda *a, **k: [{"id": "CVE-1", "package": "pyyaml",
                              "modules": ["src/demo/core.py"], "confidence": 0.9}],
        )
        monkeypatch.setattr(
            "genesis_architect_pro.dependency_scanner.scan_do_not_touch_risks",
            lambda *a, **k: [{"id": "do-not-touch:src/demo/core.py",
                              "label": "VOLATILE", "module": "src/demo/core.py",
                              "confidence": 0.8}],
        )
        ctx = SessionContext(session_id="t", mode=GDEMode.GATE,
                             stage=LifecycleStage.EXECUTE, project_dir=project)
        out = gde_run_knowledge_graph(ctx)
        assert out["do_not_touch_with_cve"]
        assert any("do-not-touch zone with an open CVE" in w for w in out["_warnings"])


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
