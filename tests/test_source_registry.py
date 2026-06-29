"""Tests for source_registry - the runtime research source catalog.

Covers: loading the packaged catalog, ranking by tier priority x evidence
weight, engine profiles, the market=signal-only rule, and per-project overrides
that add/replace sources without code changes.
"""
import json

from genesis_architect_pro.source_registry import (
    Source, SourceRegistry, load_registry, add_project_source,
)


class TestLoad:
    def test_loads_packaged_catalog(self):
        reg = load_registry(".")
        assert reg.version >= 2
        assert reg.get("github_rest") is not None
        assert reg.get("official_docs").tier == "official"

    def test_tier_priorities(self):
        reg = load_registry(".")
        assert reg.tier_priority("official") == 100
        assert reg.tier_priority("market") == 40
        assert reg.tier_priority("nonexistent") == 0


class TestRanking:
    def test_official_outranks_field(self):
        reg = load_registry(".")
        ranked = reg.ranked()
        ids = [s.id for s in ranked]
        assert ids.index("official_docs") < ids.index("reddit")

    def test_rank_score_combines_priority_and_weight(self):
        reg = load_registry(".")
        official = reg.get("official_docs")
        instagram = reg.get("instagram")
        assert reg.rank_score(official) > reg.rank_score(instagram)

    def test_free_only_filter(self):
        reg = load_registry(".")
        free = reg.ranked(free_only=True)
        assert all(s.free for s in free)
        assert reg.get("github_rest") in free
        assert reg.get("reddit") not in free  # reddit is pro-only

    def test_exclude_market(self):
        reg = load_registry(".")
        truth = reg.ranked(include_market=False)
        assert reg.get("instagram") not in truth


class TestEngineProfiles:
    def test_developer_field_profile(self):
        reg = load_registry(".")
        srcs = {s.id for s in reg.for_engine("developer_field")}
        assert "reddit" in srcs and "youtube" in srcs
        assert "official_docs" not in srcs  # not in the field profile's tiers

    def test_research_intelligence_excludes_field(self):
        reg = load_registry(".")
        tiers = {s.tier for s in reg.for_engine("research_intelligence")}
        assert "official" in tiers and "field" not in tiers

    def test_unknown_engine_returns_all(self):
        reg = load_registry(".")
        assert len(reg.for_engine("nope")) == len(reg.ranked())


class TestMarketRule:
    def test_instagram_is_not_engineering_truth(self):
        reg = load_registry(".")
        assert reg.is_engineering_truth("instagram") is False
        assert reg.is_engineering_truth("github_rest") is True

    def test_engineering_truth_sources_exclude_market(self):
        reg = load_registry(".")
        truth = reg.engineering_truth_sources()
        assert all(s.tier != "market" for s in truth)


class TestOverrides:
    def test_add_project_source_then_load(self, tmp_path):
        ok = add_project_source(
            {"id": "internal_wiki", "name": "Internal Wiki", "tier": "official",
             "evidence_weight": 0.95, "free": True},
            project_root=tmp_path)
        assert ok
        reg = load_registry(tmp_path)
        s = reg.get("internal_wiki")
        assert s is not None and s.tier == "official"

    def test_override_replaces_existing_by_id(self, tmp_path):
        add_project_source(
            {"id": "reddit", "name": "Reddit (tuned)", "tier": "field",
             "evidence_weight": 0.5},
            project_root=tmp_path)
        reg = load_registry(tmp_path)
        assert reg.get("reddit").evidence_weight == 0.5  # overridden weight

    def test_add_rejects_invalid(self, tmp_path):
        assert add_project_source({"name": "no id"}, project_root=tmp_path) is False

    def test_corrupt_override_ignored(self, tmp_path):
        p = tmp_path / ".genesis" / "knowledge" / "research_sources.json"
        p.parent.mkdir(parents=True)
        p.write_text("{not json")
        reg = load_registry(tmp_path)        # falls back to packaged catalog
        assert reg.get("github_rest") is not None
