"""Tests for the engine-layer evidence_pack (genesis_architect.pro).

Distinct from test_evidence_pack.py, which covers the unrelated
genesis_architect.core.evidence_pack module of the same name.
"""
"""Tests for evidence_pack - the proof behind recommendations + honesty clause."""
from genesis_architect.pro.evidence_pack import (
    build_evidence_pack, save_evidence_pack,
)


class TestBuild:
    def test_enriches_from_registry(self):
        pack = build_evidence_pack("use fastapi?", [
            {"source_id": "official_docs", "claim": "supports async"},
        ])
        item = pack.items[0]
        assert item.tier == "official" and item.reliability == 100
        assert item.weight == 1.0

    def test_no_evidence_is_none_confidence(self):
        pack = build_evidence_pack("q", [])
        assert pack.confidence == "none"

    def test_two_strong_truth_sources_high(self):
        pack = build_evidence_pack("q", [
            {"source_id": "official_docs", "claim": "a"},   # reliability 100
            {"source_id": "osv", "claim": "b"},             # reliability 98
        ])
        assert pack.confidence == "high"

    def test_field_only_never_high(self):
        # only field/market signal -> cannot be high (honesty clause)
        pack = build_evidence_pack("q", [
            {"source_id": "reddit", "claim": "people say it's fine"},
            {"source_id": "instagram", "claim": "trending"},
        ])
        assert pack.confidence in ("low", "medium")
        assert pack.confidence != "high"

    def test_contradiction_caps_confidence(self):
        strong = build_evidence_pack("q", [
            {"source_id": "official_docs", "claim": "a"},
            {"source_id": "osv", "claim": "b"},
        ])
        contested = build_evidence_pack("q", [
            {"source_id": "official_docs", "claim": "a"},
            {"source_id": "osv", "claim": "b"},
        ], contradictions=["docs say X, source says not-X"])
        assert strong.confidence == "high"
        assert contested.confidence == "medium"  # capped down one notch


class TestHonesty:
    def test_unavailable_kept_not_dropped(self):
        pack = build_evidence_pack("q", [
            {"source_id": "snyk_db", "claim": "", "status": "unavailable"},
            {"source_id": "official_docs", "claim": "a"},
        ])
        assert len(pack.items) == 2
        assert len(pack.unavailable()) == 1
        # unavailable source is not counted as engineering truth
        assert pack.unavailable()[0].is_truth() is False

    def test_markdown_lists_unavailable(self):
        pack = build_evidence_pack("q", [
            {"source_id": "snyk_db", "claim": "", "status": "unavailable"},
        ])
        md = pack.to_markdown()
        assert "Unavailable sources" in md and "honesty clause" in md


class TestPersistence:
    def test_save_roundtrip(self, tmp_path):
        pack = build_evidence_pack("use fastapi?", [
            {"source_id": "official_docs", "claim": "async"},
        ], recommendation="yes", project_root=tmp_path)
        path = save_evidence_pack(pack, "fastapi decision!!", project_root=tmp_path)
        assert path is not None and path.exists()
        assert path.suffix == ".json"

    def test_to_dict_shape(self):
        pack = build_evidence_pack("q", [{"source_id": "official_docs", "claim": "a"}],
                                   recommendation="r", what_would_change_it="w")
        d = pack.to_dict()
        assert d["recommendation"] == "r" and d["what_would_change_it"] == "w"
        assert d["items"][0]["source_id"] == "official_docs"
