"""Tests for research_outline.py — R1: the items x fields grid.

This module's one structural promise is that it stays L0 (no internal
Genesis dependencies, so it can never join a requires/handoffs cycle). Its
one behavioral promise is that reading a missing or corrupt outline returns
None rather than raising. Both get a test that would fail loudly if broken.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from genesis_architect_pro.research_outline import (
    FIELDS_FILENAME,
    OUTLINE_FILENAME,
    Outline,
    load_outline,
    save_outline,
)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestOutlineConstruction:
    def test_requires_only_topic(self):
        outline = Outline(topic="best async web frameworks")
        assert outline.topic == "best async web frameworks"
        assert outline.items == []
        assert outline.fields == []

    def test_items_and_fields_are_independent_defaults(self):
        """Mutable defaults must not be shared across instances."""
        a = Outline(topic="a")
        b = Outline(topic="b")
        a.items.append("fastapi")
        a.fields.append("license")
        assert b.items == []
        assert b.fields == []

    def test_created_at_auto_populates_as_iso_string(self):
        outline = Outline(topic="test")
        assert isinstance(outline.created_at, str)
        assert outline.created_at  # non-empty

    def test_explicit_items_and_fields(self):
        outline = Outline(
            topic="library shortlist",
            items=["fastapi", "django", "flask"],
            fields=["license", "maintenance", "bundle_size"],
        )
        assert outline.items == ["fastapi", "django", "flask"]
        assert outline.fields == ["license", "maintenance", "bundle_size"]


# ---------------------------------------------------------------------------
# save/load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoadRoundTrip:
    def test_round_trip_preserves_all_fields(self, tmp_path):
        original = Outline(
            topic="observability vendors",
            items=["datadog", "honeycomb", "grafana"],
            fields=["pricing_model", "otel_support", "on_call_paging"],
            created_at="2026-08-18T12:00:00+00:00",
        )
        save_outline(original, tmp_path)
        loaded = load_outline(tmp_path)

        assert loaded is not None
        assert loaded.topic == original.topic
        assert loaded.items == original.items
        assert loaded.fields == original.fields
        assert loaded.created_at == original.created_at

    def test_round_trip_with_empty_items_and_fields(self, tmp_path):
        """A freshly-started outline (topic confirmed, grid not filled yet)
        must still round-trip, since Phase 1's confirm step happens before
        the grid is complete."""
        original = Outline(topic="just started")
        save_outline(original, tmp_path)
        loaded = load_outline(tmp_path)

        assert loaded is not None
        assert loaded.items == []
        assert loaded.fields == []

    def test_round_trip_preserves_unicode_topic(self, tmp_path):
        original = Outline(topic="מסגרת ספריות מחקר")
        save_outline(original, tmp_path)
        loaded = load_outline(tmp_path)

        assert loaded is not None
        assert loaded.topic == original.topic

    def test_save_creates_research_dir(self, tmp_path):
        assert not (tmp_path / ".genesis").exists()
        save_outline(Outline(topic="test"), tmp_path)
        assert (tmp_path / ".genesis" / "research").is_dir()

    def test_save_writes_two_separate_files(self, tmp_path):
        save_outline(Outline(topic="test", items=["a"], fields=["b"]), tmp_path)
        research_dir = tmp_path / ".genesis" / "research"
        assert (research_dir / OUTLINE_FILENAME).is_file()
        assert (research_dir / FIELDS_FILENAME).is_file()

    def test_items_live_in_outline_file_fields_live_in_fields_file(self, tmp_path):
        """The two-file split is a real separation of concerns, not
        cosmetic: items must not leak into fields.json or vice versa."""
        save_outline(
            Outline(topic="test", items=["itemA"], fields=["fieldB"]), tmp_path
        )
        research_dir = tmp_path / ".genesis" / "research"
        outline_raw = json.loads((research_dir / OUTLINE_FILENAME).read_text(encoding="utf-8"))
        fields_raw = json.loads((research_dir / FIELDS_FILENAME).read_text(encoding="utf-8"))

        assert outline_raw["items"] == ["itemA"]
        assert "fields" not in outline_raw
        assert fields_raw["fields"] == ["fieldB"]
        assert "items" not in fields_raw

    def test_save_overwrites_previous_outline(self, tmp_path):
        save_outline(Outline(topic="first draft", items=["a"]), tmp_path)
        save_outline(Outline(topic="revised", items=["a", "b"]), tmp_path)
        loaded = load_outline(tmp_path)

        assert loaded is not None
        assert loaded.topic == "revised"
        assert loaded.items == ["a", "b"]


# ---------------------------------------------------------------------------
# Fail-safe loading
# ---------------------------------------------------------------------------

class TestLoadFailSafe:
    def test_missing_directory_returns_none(self, tmp_path):
        assert load_outline(tmp_path) is None

    def test_missing_outline_file_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / FIELDS_FILENAME).write_text('{"fields": []}', encoding="utf-8")
        assert load_outline(tmp_path) is None

    def test_missing_fields_file_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text(
            '{"topic": "t", "items": []}', encoding="utf-8"
        )
        assert load_outline(tmp_path) is None

    def test_corrupt_outline_json_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text("{not valid json", encoding="utf-8")
        (research_dir / FIELDS_FILENAME).write_text('{"fields": []}', encoding="utf-8")
        assert load_outline(tmp_path) is None

    def test_corrupt_fields_json_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text(
            '{"topic": "t", "items": []}', encoding="utf-8"
        )
        (research_dir / FIELDS_FILENAME).write_text("[not an object", encoding="utf-8")
        assert load_outline(tmp_path) is None

    def test_outline_json_not_an_object_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
        (research_dir / FIELDS_FILENAME).write_text('{"fields": []}', encoding="utf-8")
        assert load_outline(tmp_path) is None

    def test_missing_topic_key_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text('{"items": []}', encoding="utf-8")
        (research_dir / FIELDS_FILENAME).write_text('{"fields": []}', encoding="utf-8")
        assert load_outline(tmp_path) is None

    def test_blank_topic_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text('{"topic": ""}', encoding="utf-8")
        (research_dir / FIELDS_FILENAME).write_text('{"fields": []}', encoding="utf-8")
        assert load_outline(tmp_path) is None

    def test_items_with_non_string_entry_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text(
            '{"topic": "t", "items": ["ok", 42]}', encoding="utf-8"
        )
        (research_dir / FIELDS_FILENAME).write_text('{"fields": []}', encoding="utf-8")
        assert load_outline(tmp_path) is None

    def test_fields_with_non_string_entry_returns_none(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text('{"topic": "t", "items": []}', encoding="utf-8")
        (research_dir / FIELDS_FILENAME).write_text(
            '{"fields": [null]}', encoding="utf-8"
        )
        assert load_outline(tmp_path) is None

    def test_missing_created_at_falls_back_instead_of_failing(self, tmp_path):
        """A hand-edited outline.json (the Phase-1 confirm step invites this)
        won't include created_at — that must not make the whole file unusable."""
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text(
            '{"topic": "hand-edited", "items": ["x"]}', encoding="utf-8"
        )
        (research_dir / FIELDS_FILENAME).write_text('{"fields": []}', encoding="utf-8")

        loaded = load_outline(tmp_path)
        assert loaded is not None
        assert loaded.topic == "hand-edited"
        assert isinstance(loaded.created_at, str) and loaded.created_at

    def test_missing_items_key_defaults_to_empty(self, tmp_path):
        research_dir = tmp_path / ".genesis" / "research"
        research_dir.mkdir(parents=True)
        (research_dir / OUTLINE_FILENAME).write_text('{"topic": "t"}', encoding="utf-8")
        (research_dir / FIELDS_FILENAME).write_text("{}", encoding="utf-8")

        loaded = load_outline(tmp_path)
        assert loaded is not None
        assert loaded.items == []
        assert loaded.fields == []


# ---------------------------------------------------------------------------
# L0 purity — the structural guarantee the blueprint calls out
# ---------------------------------------------------------------------------

class TestNoInternalDependencies:
    def test_module_imports_nothing_from_genesis_architect_pro(self):
        """R1's entire value as an L0 module rests on this: it cannot be
        part of a requires/handoffs cycle if it never imports a sibling
        engine module in the first place."""
        import genesis_architect_pro.research_outline as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)

        offending: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("genesis_architect_pro"):
                    offending.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("genesis_architect_pro"):
                        offending.append(alias.name)

        assert offending == []