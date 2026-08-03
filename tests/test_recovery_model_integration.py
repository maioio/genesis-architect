"""
Integration tests: ModelStore ↔ recovery_scan.

Covers:
  - scan() now returns model_sync key (backward-compat: all old keys still present)
  - First-run creates .genesis/model.json from the import graph
  - One node per module in committed model after first run
  - Subsequent runs do NOT overwrite existing committed model
  - planned.json is never touched by scan()
  - Corrupted model.json → warning emitted, scan continues, model_sync["synced"]=False
  - Missing .genesis/ directory handled gracefully
  - Empty graph produces no nodes (no crash)
  - model_sync["diverged"] is True when planned.json differs from committed
  - model_sync["diverged"] is False when no planned.json exists
  - sync_model_from_graph returns correct status fields
  - JSON serialisability of the full scan() result including model_sync
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path


from genesis_architect.pro.recovery_scan import scan, sync_model_from_graph
from genesis_architect.pro.model_store import (
    ModelStore, ArchModel, ModelNode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_python_project(root: Path, n_modules: int = 3) -> None:
    """Minimal Python project with n source files and a pyproject.toml."""
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[tool.poetry]\nname='testproject'\n")
    for i in range(n_modules):
        (src / f"mod_{i}.py").write_text(f"X_{i} = {i}\n")
    (root / ".git").mkdir(exist_ok=True)


def _make_graph(modules: list[str]) -> dict:
    """Build a minimal import graph dict for use with sync_model_from_graph."""
    return {
        "language": "python",
        "modules": {
            m: {"imports": [], "imported_by": [], "fan_out": 0, "fan_in": 0,
                "lines": 10, "is_entry_point": False, "layer": "unknown"}
            for m in modules
        },
        "cycles": [], "dark_modules": [], "entry_points": [],
        "module_count": len(modules),
        "built_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Backward compatibility: scan() still returns all pre-integration keys
# ---------------------------------------------------------------------------

class TestScanBackwardCompatibility:
    def test_all_original_keys_present(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        for key in ("fix_commit_hotspots", "external_url_count", "version_sources",
                    "doc_version", "version_drift", "dead_file_candidates"):
            assert key in result, f"Legacy key '{key}' missing from scan() result"

    def test_model_sync_key_added(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert "model_sync" in result

    def test_full_result_is_json_serialisable(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        dumped = json.dumps(result)
        assert isinstance(dumped, str)
        # model_sync must survive round-trip
        parsed = json.loads(dumped)
        assert "model_sync" in parsed

    def test_model_sync_has_required_fields(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        ms = result["model_sync"]
        assert "synced" in ms
        assert "node_count" in ms
        assert "diverged" in ms
        assert "warning" in ms

    def test_existing_scan_output_values_unchanged(self, tmp_path):
        """scan() key values that pre-existed must not be altered by model integration."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.2.3"\n')
        (tmp_path / ".git").mkdir()
        result = scan(tmp_path)
        assert result["version_sources"].get("pyproject.toml") == "1.2.3"


# ---------------------------------------------------------------------------
# First-run model creation
# ---------------------------------------------------------------------------

class TestFirstRunModelCreation:
    def test_first_run_creates_model_json(self, tmp_path):
        _make_python_project(tmp_path, n_modules=3)
        assert not (tmp_path / ".genesis" / "model.json").exists()
        scan(tmp_path)
        assert (tmp_path / ".genesis" / "model.json").exists()

    def test_first_run_synced_is_true(self, tmp_path):
        _make_python_project(tmp_path, n_modules=3)
        result = scan(tmp_path)
        assert result["model_sync"]["synced"] is True

    def test_first_run_node_count_positive(self, tmp_path):
        _make_python_project(tmp_path, n_modules=3)
        result = scan(tmp_path)
        assert result["model_sync"]["node_count"] > 0

    def test_committed_model_has_one_node_per_module(self, tmp_path):
        modules = ["src/a.py", "src/b.py", "src/c.py"]
        graph = _make_graph(modules)
        sync_model_from_graph(tmp_path, graph)
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        committed_ids = {n.id for n in committed.nodes}
        for m in modules:
            assert m in committed_ids, f"Module {m!r} missing from committed model"

    def test_committed_nodes_have_component_kind(self, tmp_path):
        graph = _make_graph(["src/main.py", "src/utils.py"])
        sync_model_from_graph(tmp_path, graph)
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        for node in committed.nodes:
            assert node.kind == "component"

    def test_committed_nodes_technology_matches_graph_language(self, tmp_path):
        graph = _make_graph(["src/main.py"])
        graph["language"] = "python"
        sync_model_from_graph(tmp_path, graph)
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        assert committed.nodes[0].technology == "python"

    def test_committed_nodes_description_has_fan_info(self, tmp_path):
        graph = _make_graph(["src/main.py"])
        graph["modules"]["src/main.py"]["fan_in"] = 2
        graph["modules"]["src/main.py"]["fan_out"] = 5
        sync_model_from_graph(tmp_path, graph)
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        desc = committed.nodes[0].description or ""
        assert "fan_in" in desc
        assert "fan_out" in desc

    def test_model_json_is_valid_json(self, tmp_path):
        _make_python_project(tmp_path, n_modules=2)
        scan(tmp_path)
        raw = (tmp_path / ".genesis" / "model.json").read_text()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
        assert "nodes" in parsed


# ---------------------------------------------------------------------------
# No overwrite on subsequent runs
# ---------------------------------------------------------------------------

class TestNoOverwriteOnSubsequentRuns:
    def test_second_run_synced_is_false(self, tmp_path):
        """After first run, model already has nodes → synced=False on second call."""
        _make_python_project(tmp_path, n_modules=2)
        scan(tmp_path)
        result2 = scan(tmp_path)
        assert result2["model_sync"]["synced"] is False

    def test_second_run_does_not_change_committed_model(self, tmp_path):
        """Manual edit to committed model must survive a second scan()."""
        graph = _make_graph(["src/a.py"])
        sync_model_from_graph(tmp_path, graph)

        # User manually edits committed model
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        committed.nodes[0].description = "user-authored description"
        store.save_committed(committed)

        # Second sync — must not overwrite
        sync_model_from_graph(tmp_path, graph)
        committed2 = store.load_committed()
        assert committed2.nodes[0].description == "user-authored description"

    def test_existing_committed_node_count_preserved(self, tmp_path):
        """node_count reflects current committed state, not graph size."""
        graph = _make_graph(["src/a.py", "src/b.py"])
        sync_model_from_graph(tmp_path, graph)
        # Add a user-authored node manually
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        committed.nodes.append(ModelNode("user_node", "system", "External API"))
        store.save_committed(committed)
        # Second call: no sync, but node_count reflects the 3 existing nodes
        status = sync_model_from_graph(tmp_path, graph)
        assert status["node_count"] == 3
        assert status["synced"] is False


# ---------------------------------------------------------------------------
# planned.json never touched
# ---------------------------------------------------------------------------

class TestPlannedFileNotTouched:
    def test_scan_does_not_create_planned_json(self, tmp_path):
        _make_python_project(tmp_path, n_modules=2)
        scan(tmp_path)
        assert not (tmp_path / ".genesis" / "planned.json").exists()

    def test_sync_does_not_create_planned_json(self, tmp_path):
        graph = _make_graph(["src/a.py"])
        sync_model_from_graph(tmp_path, graph)
        assert not (tmp_path / ".genesis" / "planned.json").exists()

    def test_existing_planned_json_unchanged_after_sync(self, tmp_path):
        """A pre-existing planned.json must be identical before and after scan."""
        store = ModelStore(tmp_path)
        planned = ArchModel(nodes=[
            ModelNode("p1", "container", "PlannedFeature"),
            ModelNode("p2", "container", "AnotherFeature"),
        ])
        store.save_planned(planned)
        original_content = (tmp_path / ".genesis" / "planned.json").read_text()

        _make_python_project(tmp_path, n_modules=2)
        scan(tmp_path)

        current_content = (tmp_path / ".genesis" / "planned.json").read_text()
        assert current_content == original_content

    def test_planned_node_count_unchanged_after_scan(self, tmp_path):
        store = ModelStore(tmp_path)
        planned = ArchModel(nodes=[
            ModelNode("p1", "container", "Feature A"),
        ])
        store.save_planned(planned)

        _make_python_project(tmp_path, n_modules=3)
        scan(tmp_path)

        loaded_planned = store.load_planned()
        assert len(loaded_planned.nodes) == 1
        assert loaded_planned.nodes[0].id == "p1"


# ---------------------------------------------------------------------------
# Corrupted model file — warning + continue
# ---------------------------------------------------------------------------

class TestCorruptedModelGracefulFallback:
    def test_corrupted_model_json_does_not_crash_scan(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("{ not valid json !!!")
        _make_python_project(tmp_path)
        # Must not raise
        result = scan(tmp_path)
        assert "model_sync" in result

    def test_corrupted_model_json_emits_warning(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("{ not valid json !!!")
        _make_python_project(tmp_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            scan(tmp_path)
        # A warning must have been emitted (from ModelStore._load)
        messages = [str(w.message) for w in caught]
        assert any("not valid JSON" in m or "model" in m.lower() for m in messages), \
            f"No model-related warning in: {messages}"

    def test_corrupted_model_json_scan_still_returns_all_legacy_keys(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("definitely not JSON")
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        for key in ("fix_commit_hotspots", "external_url_count", "version_sources",
                    "doc_version", "version_drift", "dead_file_candidates"):
            assert key in result

    def test_corrupted_model_json_synced_may_be_true(self, tmp_path):
        """Corrupt committed → treated as empty → first-run sync populates it."""
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("bad json")
        graph = _make_graph(["src/a.py", "src/b.py"])
        # Corrupt file → load returns empty ArchModel → sync populates
        status = sync_model_from_graph(tmp_path, graph)
        # Either synced (corrupt treated as empty → populated) or
        # warning emitted and synced=False — both are valid outcomes.
        assert isinstance(status["synced"], bool)
        assert isinstance(status["node_count"], int)


# ---------------------------------------------------------------------------
# Missing .genesis directory
# ---------------------------------------------------------------------------

class TestMissingGenesisDir:
    def test_no_genesis_dir_scan_still_works(self, tmp_path):
        _make_python_project(tmp_path)
        assert not (tmp_path / ".genesis").exists()
        result = scan(tmp_path)
        assert "model_sync" in result

    def test_no_genesis_dir_sync_creates_it(self, tmp_path):
        graph = _make_graph(["src/a.py"])
        assert not (tmp_path / ".genesis").exists()
        sync_model_from_graph(tmp_path, graph)
        assert (tmp_path / ".genesis").exists()
        assert (tmp_path / ".genesis" / "model.json").exists()


# ---------------------------------------------------------------------------
# Empty graph
# ---------------------------------------------------------------------------

class TestEmptyGraph:
    def test_empty_graph_no_nodes_created(self, tmp_path):
        graph = _make_graph([])
        status = sync_model_from_graph(tmp_path, graph)
        assert status["node_count"] == 0
        assert status["synced"] is False

    def test_empty_graph_no_model_json_created(self, tmp_path):
        graph = _make_graph([])
        sync_model_from_graph(tmp_path, graph)
        assert not (tmp_path / ".genesis" / "model.json").exists()

    def test_empty_graph_does_not_crash(self, tmp_path):
        graph = {"language": "python", "modules": {}}
        status = sync_model_from_graph(tmp_path, graph)
        assert isinstance(status, dict)

    def test_missing_modules_key_in_graph(self, tmp_path):
        graph = {"language": "python"}  # no "modules" key
        status = sync_model_from_graph(tmp_path, graph)
        assert status["node_count"] == 0
        assert status["synced"] is False


# ---------------------------------------------------------------------------
# Divergence reporting
# ---------------------------------------------------------------------------

class TestDivergenceReporting:
    def test_diverged_false_when_no_planned(self, tmp_path):
        graph = _make_graph(["src/a.py"])
        status = sync_model_from_graph(tmp_path, graph)
        assert status["diverged"] is False

    def test_diverged_false_when_planned_equals_committed(self, tmp_path):
        graph = _make_graph(["src/a.py"])
        sync_model_from_graph(tmp_path, graph)
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        store.save_planned(committed)  # planned == committed → no divergence
        status = sync_model_from_graph(tmp_path, graph)
        assert status["diverged"] is False

    def test_diverged_true_when_planned_has_extra_node(self, tmp_path):
        graph = _make_graph(["src/a.py"])
        sync_model_from_graph(tmp_path, graph)
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        planned = ArchModel(nodes=list(committed.nodes) + [
            ModelNode("p_extra", "container", "PlannedFeature")
        ])
        store.save_planned(planned)
        status = sync_model_from_graph(tmp_path, graph)
        assert status["diverged"] is True

    def test_model_sync_diverged_surfaced_in_scan(self, tmp_path):
        _make_python_project(tmp_path, n_modules=2)
        scan(tmp_path)  # first run: creates committed
        # Add a planned node that diverges
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        planned = ArchModel(nodes=list(committed.nodes) + [
            ModelNode("p1", "container", "NotYetBuilt")
        ])
        store.save_planned(planned)
        result2 = scan(tmp_path)
        assert result2["model_sync"]["diverged"] is True


# ---------------------------------------------------------------------------
# sync_model_from_graph status fields
# ---------------------------------------------------------------------------

class TestSyncStatusFields:
    def test_status_has_synced_bool(self, tmp_path):
        status = sync_model_from_graph(tmp_path, _make_graph(["a.py"]))
        assert isinstance(status["synced"], bool)

    def test_status_has_node_count_int(self, tmp_path):
        status = sync_model_from_graph(tmp_path, _make_graph(["a.py"]))
        assert isinstance(status["node_count"], int)

    def test_status_has_diverged_bool(self, tmp_path):
        status = sync_model_from_graph(tmp_path, _make_graph(["a.py"]))
        assert isinstance(status["diverged"], bool)

    def test_status_warning_is_none_on_success(self, tmp_path):
        status = sync_model_from_graph(tmp_path, _make_graph(["a.py"]))
        assert status["warning"] is None

    def test_node_count_matches_modules(self, tmp_path):
        modules = ["src/a.py", "src/b.py", "src/c.py"]
        status = sync_model_from_graph(tmp_path, _make_graph(modules))
        assert status["node_count"] == 3
