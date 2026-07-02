"""Tests for knowledge_graph - cross-source connective intelligence.

Covers the planning-doc contract: additive/idempotent graph, confidence on every
edge, connective queries, persistence, and graceful build from partial inputs.
"""
from genesis_architect_pro.knowledge_graph import (
    KnowledgeGraph, NODE_TYPES, REL_TYPES,
    load_graph, save_graph, build_from_project,
    add_architecture, add_security, add_risks, add_decisions, add_field_findings,
)


class TestGraphBasics:
    def test_add_node_and_get(self):
        g = KnowledgeGraph()
        g.add_node("module:a", "module", "a")
        assert g.get_node("module:a").type == "module"
        assert g.stats()["nodes"] == 1

    def test_add_node_is_idempotent_and_merges_metadata(self):
        g = KnowledgeGraph()
        g.add_node("m", "module", "m", {"loc": 100})
        g.add_node("m", "module", "m", {"churn": 5})
        n = g.get_node("m")
        assert n.metadata == {"loc": 100, "churn": 5}
        assert g.stats()["nodes"] == 1

    def test_add_edge_autocreates_endpoints(self):
        g = KnowledgeGraph()
        g.add_edge("cve:1", "affects", "package:x", confidence=0.9)
        assert g.get_node("cve:1") is not None
        assert g.get_node("package:x") is not None
        assert g.edges[0].confidence == 0.9

    def test_edge_dedup_keeps_higher_confidence(self):
        g = KnowledgeGraph()
        g.add_edge("a", "affects", "b", confidence=0.4)
        g.add_edge("a", "affects", "b", confidence=0.8)
        assert len(g.edges) == 1 and g.edges[0].confidence == 0.8

    def test_confidence_clamped(self):
        g = KnowledgeGraph()
        g.add_edge("a", "affects", "b", confidence=5.0)
        assert g.edges[0].confidence == 1.0


class TestTraversal:
    def _sample(self):
        g = KnowledgeGraph()
        # cve -> package -> module ; risk -> located_in -> module
        g.add_edge("cve:1", "affects", "package:x", confidence=0.9)
        g.add_edge("package:x", "used_by", "module:m", confidence=0.7)
        g.add_node("module:m", "module", "m")
        g.add_node("package:x", "package", "x")
        g.add_node("cve:1", "cve", "CVE-1")
        g.add_node("risk:r", "risk", "do-not-touch")
        g.add_edge("risk:r", "located_in", "module:m", confidence=0.8)
        return g

    def test_neighbors_out(self):
        g = self._sample()
        nbrs = [n.id for n in g.neighbors("cve:1", direction="out")]
        assert nbrs == ["package:x"]

    def test_neighbors_in(self):
        g = self._sample()
        nbrs = {n.id for n in g.neighbors("module:m", direction="in")}
        assert nbrs == {"package:x", "risk:r"}

    def test_query_connective_path(self):
        g = self._sample()
        # which cve reaches a module through a package?
        paths = g.query(["cve", "affects", "package", "used_by", "module"])
        assert ["cve:1", "package:x", "module:m"] in paths

    def test_query_wildcard_type(self):
        g = self._sample()
        paths = g.query(["risk", "located_in", "*"])
        assert ["risk:r", "module:m"] in paths

    def test_query_no_match(self):
        g = self._sample()
        assert g.query(["cve", "warns_about", "module"]) == []

    def test_query_rejects_bad_pattern(self):
        g = self._sample()
        assert g.query([]) == []
        assert g.query(["cve", "affects"]) == []  # even length -> invalid


class TestPersistence:
    def test_roundtrip(self, tmp_path):
        g = KnowledgeGraph()
        g.add_node("module:a", "module", "a", {"loc": 10})
        g.add_edge("decision:d", "affects", "module:a", confidence=0.6,
                   evidence_ref="ev1")
        save_graph(g, tmp_path)
        g2 = load_graph(tmp_path)
        assert g2.get_node("module:a").metadata == {"loc": 10}
        e = g2.edges[0]
        assert e.rel == "affects" and e.evidence_ref == "ev1"

    def test_load_missing_returns_empty(self, tmp_path):
        assert load_graph(tmp_path).stats()["nodes"] == 0

    def test_load_corrupt_returns_empty(self, tmp_path):
        p = tmp_path / ".genesis" / "knowledge" / "graph.json"
        p.parent.mkdir(parents=True)
        p.write_text("{not json")
        assert load_graph(tmp_path).stats()["nodes"] == 0

    def test_malformed_edge_skipped_on_load(self, tmp_path):
        p = tmp_path / ".genesis" / "knowledge" / "graph.json"
        p.parent.mkdir(parents=True)
        p.write_text('{"nodes": {}, "edges": [{"src": "a"}]}')  # missing rel/dst
        assert load_graph(tmp_path).stats()["edges"] == 0


class TestBuildPipeline:
    def test_architecture_pass(self):
        g = KnowledgeGraph()
        add_architecture(g, modules=["a", "b"],
                         anti_patterns=[{"name": "god_class", "module": "a"}],
                         drift_modules=["b"])
        assert g.get_node("module:a") and g.get_node("module:b")
        # anti-pattern detected_in module:a
        ap = [n for n in g.nodes.values() if n.type == "anti_pattern"]
        assert ap and g.query(["anti_pattern", "detected_in", "module"])
        assert g.query(["drift", "detected_in", "module"])

    def test_security_pass_builds_cve_chain(self):
        g = KnowledgeGraph()
        add_security(g, cves=[{"id": "CVE-1", "package": "requests",
                               "modules": ["net"]}])
        assert g.query(["cve", "affects", "package", "used_by", "module"])

    def test_connective_do_not_touch_with_cve(self):
        # The flagship query: which do-not-touch zones have an open CVE?
        g = KnowledgeGraph()
        add_architecture(g, modules=["net"])
        add_security(g, cves=[{"id": "CVE-9", "package": "requests",
                               "modules": ["net"]}])
        add_risks(g, risks=[{"id": "r1", "label": "do-not-touch",
                             "module": "net"}])
        # cve -> package -> module  AND  risk -> module
        cve_paths = g.query(["cve", "affects", "package", "used_by", "module"])
        risk_paths = g.query(["risk", "located_in", "module"])
        cve_modules = {p[-1] for p in cve_paths}
        risk_modules = {p[-1] for p in risk_paths}
        assert cve_modules & risk_modules == {"module:net"}

    def test_decisions_and_field_findings(self):
        g = KnowledgeGraph()
        add_decisions(g, decisions=[{"id": "use_fastapi", "label": "use FastAPI",
                                     "evidence": ["ep1"], "modules": ["api"]}])
        add_field_findings(g, findings=[{"id": "f1", "label": "perf warning",
                                         "pattern": "sync_db", "source": "reddit"}])
        assert g.query(["evidence", "supports", "decision"])
        assert g.query(["decision", "affects", "module"])
        assert g.query(["field_finding", "warns_about", "pattern"])

    def test_build_from_project_is_additive(self, tmp_path):
        build_from_project(tmp_path, architecture={"modules": ["a"]})
        g = build_from_project(tmp_path, security={
            "cves": [{"id": "CVE-1", "package": "x", "modules": ["a"]}]})
        # both passes present in the persisted union
        assert g.get_node("module:a") and g.get_node("cve:CVE-1")
        reloaded = load_graph(tmp_path)
        assert reloaded.get_node("cve:CVE-1") is not None

    def test_build_with_nothing_does_not_fabricate(self, tmp_path):
        g = build_from_project(tmp_path)
        assert g.stats()["nodes"] == 0 and g.stats()["edges"] == 0


class TestTypes:
    def test_known_types_present(self):
        assert "cve" in NODE_TYPES and "module" in NODE_TYPES
        assert "affects" in REL_TYPES and "located_in" in REL_TYPES
