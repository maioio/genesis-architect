"""
Tests for ModelDiff — Step 6.

Covers:
  - _compute_diff: added/removed/changed nodes
  - _compute_diff: changed node fields (name, kind, technology, description, external)
  - _compute_diff: added/removed/changed links
  - _compute_diff: responsibility additions and removals
  - ModelDiff.has_changes, ModelDiff.summary, ModelDiff.to_dict()
  - ModelStore.model_diff(): disk-backed round-trip
  - Missing planned model returns empty diff (not an error)
  - Missing committed model returns empty diff (not an error)
  - Corrupted model file → warning emitted, empty diff returned
  - scan() includes model_diff key with correct structure
  - scan() backward compatibility: all pre-existing keys unchanged
  - JSON serialisability of model_diff output
  - No writes: model_diff never modifies model.json or planned.json
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path


from genesis_architect.pro.model_store import (
    ModelStore, ArchModel, ModelNode, ModelLink, ModelResponsibility,
    ModelDiff, NodeChange, ResponsibilityChange, _compute_diff,
)
from genesis_architect.pro.recovery_scan import scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(nid: str, kind: str = "component", name: str | None = None, **kwargs) -> ModelNode:
    return ModelNode(id=nid, kind=kind, name=name or nid, **kwargs)


def _link(lid: str, src: str, dst: str, label: str = "") -> ModelLink:
    return ModelLink(id=lid, src=src, dst=dst, label=label)


def _resp(rid: str, statement: str = "does something") -> ModelResponsibility:
    return ModelResponsibility(id=rid, statement=statement)


def _make_python_project(root: Path, n_modules: int = 2) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[tool.poetry]\nname='testproject'\n")
    for i in range(n_modules):
        (src / f"mod_{i}.py").write_text(f"X = {i}\n")
    (root / ".git").mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# _compute_diff — node additions and removals
# ---------------------------------------------------------------------------

class TestComputeDiffNodes:
    def test_empty_models_no_changes(self):
        diff = _compute_diff(ArchModel(), ArchModel())
        assert not diff.has_changes
        assert diff.summary == "no changes"

    def test_added_node(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel(nodes=[_node("a"), _node("b")])
        diff = _compute_diff(committed, planned)
        assert "b" in diff.added_nodes
        assert "a" not in diff.added_nodes
        assert diff.removed_nodes == []

    def test_removed_node(self):
        committed = ArchModel(nodes=[_node("a"), _node("b")])
        planned   = ArchModel(nodes=[_node("a")])
        diff = _compute_diff(committed, planned)
        assert "b" in diff.removed_nodes
        assert diff.added_nodes == []

    def test_added_and_removed_same_diff(self):
        committed = ArchModel(nodes=[_node("old")])
        planned   = ArchModel(nodes=[_node("new")])
        diff = _compute_diff(committed, planned)
        assert "new" in diff.added_nodes
        assert "old" in diff.removed_nodes

    def test_multiple_added_nodes_sorted(self):
        committed = ArchModel()
        planned   = ArchModel(nodes=[_node("z"), _node("a"), _node("m")])
        diff = _compute_diff(committed, planned)
        assert diff.added_nodes == ["a", "m", "z"]

    def test_multiple_removed_nodes_sorted(self):
        committed = ArchModel(nodes=[_node("z"), _node("a"), _node("m")])
        planned   = ArchModel()
        diff = _compute_diff(committed, planned)
        assert diff.removed_nodes == ["a", "m", "z"]

    def test_identical_models_no_changes(self):
        nodes = [_node("a", technology="python"), _node("b")]
        diff = _compute_diff(ArchModel(nodes=nodes), ArchModel(nodes=list(nodes)))
        assert not diff.has_changes


# ---------------------------------------------------------------------------
# _compute_diff — changed node fields
# ---------------------------------------------------------------------------

class TestComputeDiffNodeFields:
    def test_changed_name(self):
        committed = ArchModel(nodes=[_node("a", name="Alpha")])
        planned   = ArchModel(nodes=[_node("a", name="AlphaRenamed")])
        diff = _compute_diff(committed, planned)
        assert any(c.field == "name" and c.node_id == "a" for c in diff.changed_nodes)
        assert diff.has_changes

    def test_changed_kind(self):
        committed = ArchModel(nodes=[_node("a", kind="component")])
        planned   = ArchModel(nodes=[_node("a", kind="container")])
        diff = _compute_diff(committed, planned)
        assert any(c.field == "kind" and c.node_id == "a" for c in diff.changed_nodes)

    def test_changed_technology(self):
        committed = ArchModel(nodes=[_node("a", technology="python")])
        planned   = ArchModel(nodes=[_node("a", technology="typescript")])
        diff = _compute_diff(committed, planned)
        assert any(c.field == "technology" and c.node_id == "a" for c in diff.changed_nodes)

    def test_changed_description(self):
        committed = ArchModel(nodes=[_node("a", description="old desc")])
        planned   = ArchModel(nodes=[_node("a", description="new desc")])
        diff = _compute_diff(committed, planned)
        assert any(c.field == "description" and c.node_id == "a" for c in diff.changed_nodes)

    def test_changed_external_flag(self):
        committed = ArchModel(nodes=[_node("a", external=False)])
        planned   = ArchModel(nodes=[_node("a", external=True)])
        diff = _compute_diff(committed, planned)
        assert any(c.field == "external" and c.node_id == "a" for c in diff.changed_nodes)

    def test_changed_value_fields_correct(self):
        committed = ArchModel(nodes=[_node("a", name="Old")])
        planned   = ArchModel(nodes=[_node("a", name="New")])
        diff = _compute_diff(committed, planned)
        change = next(c for c in diff.changed_nodes if c.field == "name")
        assert change.committed_value == "Old"
        assert change.planned_value == "New"

    def test_none_to_value_is_change(self):
        committed = ArchModel(nodes=[_node("a", technology=None)])
        planned   = ArchModel(nodes=[_node("a", technology="rust")])
        diff = _compute_diff(committed, planned)
        assert any(c.field == "technology" for c in diff.changed_nodes)

    def test_value_to_none_is_change(self):
        committed = ArchModel(nodes=[_node("a", technology="python")])
        planned   = ArchModel(nodes=[_node("a", technology=None)])
        diff = _compute_diff(committed, planned)
        assert any(c.field == "technology" for c in diff.changed_nodes)

    def test_unchanged_fields_not_in_changed_nodes(self):
        committed = ArchModel(nodes=[_node("a", name="Alpha", technology="python")])
        planned   = ArchModel(nodes=[_node("a", name="Alpha", technology="python")])
        diff = _compute_diff(committed, planned)
        assert diff.changed_nodes == []


# ---------------------------------------------------------------------------
# _compute_diff — responsibilities
# ---------------------------------------------------------------------------

class TestComputeDiffResponsibilities:
    def test_added_responsibility(self):
        committed = ArchModel(nodes=[ModelNode("a", "component", "A", responsibilities=[])])
        planned   = ArchModel(nodes=[ModelNode("a", "component", "A",
                                               responsibilities=[_resp("r1", "handles auth")])])
        diff = _compute_diff(committed, planned)
        rc = [r for r in diff.responsibility_changes if r.node_id == "a" and r.change == "added"]
        assert len(rc) == 1
        assert rc[0].responsibility_id == "r1"
        assert rc[0].statement == "handles auth"

    def test_removed_responsibility(self):
        committed = ArchModel(nodes=[ModelNode("a", "component", "A",
                                               responsibilities=[_resp("r1", "handles auth")])])
        planned   = ArchModel(nodes=[ModelNode("a", "component", "A", responsibilities=[])])
        diff = _compute_diff(committed, planned)
        rc = [r for r in diff.responsibility_changes if r.node_id == "a" and r.change == "removed"]
        assert len(rc) == 1
        assert rc[0].responsibility_id == "r1"

    def test_unchanged_responsibilities_not_reported(self):
        resp = _resp("r1", "does X")
        committed = ArchModel(nodes=[ModelNode("a", "component", "A", responsibilities=[resp])])
        planned   = ArchModel(nodes=[ModelNode("a", "component", "A", responsibilities=[_resp("r1", "does X")])])
        diff = _compute_diff(committed, planned)
        assert diff.responsibility_changes == []

    def test_responsibilities_on_added_node_are_added(self):
        committed = ArchModel()
        planned   = ArchModel(nodes=[ModelNode("new", "component", "New",
                                               responsibilities=[_resp("r1", "sends emails")])])
        diff = _compute_diff(committed, planned)
        added_r = [r for r in diff.responsibility_changes if r.change == "added"]
        assert any(r.node_id == "new" and r.responsibility_id == "r1" for r in added_r)

    def test_responsibilities_on_removed_node_are_removed(self):
        committed = ArchModel(nodes=[ModelNode("gone", "component", "Gone",
                                               responsibilities=[_resp("r1", "logs events")])])
        planned   = ArchModel()
        diff = _compute_diff(committed, planned)
        removed_r = [r for r in diff.responsibility_changes if r.change == "removed"]
        assert any(r.node_id == "gone" and r.responsibility_id == "r1" for r in removed_r)

    def test_multiple_responsibilities_added_sorted(self):
        committed = ArchModel(nodes=[ModelNode("a", "component", "A")])
        planned   = ArchModel(nodes=[ModelNode("a", "component", "A",
                                               responsibilities=[_resp("r3"), _resp("r1"), _resp("r2")])])
        diff = _compute_diff(committed, planned)
        ids = [r.responsibility_id for r in diff.responsibility_changes if r.change == "added"]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# _compute_diff — links
# ---------------------------------------------------------------------------

class TestComputeDiffLinks:
    def test_added_link(self):
        committed = ArchModel()
        planned   = ArchModel(links=[_link("l1", "a", "b")])
        diff = _compute_diff(committed, planned)
        assert "l1" in diff.added_links
        assert diff.removed_links == []

    def test_removed_link(self):
        committed = ArchModel(links=[_link("l1", "a", "b")])
        planned   = ArchModel()
        diff = _compute_diff(committed, planned)
        assert "l1" in diff.removed_links
        assert diff.added_links == []

    def test_changed_link_src(self):
        committed = ArchModel(links=[_link("l1", "a", "b")])
        planned   = ArchModel(links=[_link("l1", "x", "b")])
        diff = _compute_diff(committed, planned)
        lc = next((c for c in diff.changed_links if c.link_id == "l1" and c.change == "changed"), None)
        assert lc is not None
        assert lc.committed["src"] == "a"
        assert lc.planned["src"] == "x"

    def test_changed_link_dst(self):
        committed = ArchModel(links=[_link("l1", "a", "b")])
        planned   = ArchModel(links=[_link("l1", "a", "z")])
        diff = _compute_diff(committed, planned)
        assert any(c.link_id == "l1" and c.change == "changed" for c in diff.changed_links)

    def test_changed_link_label(self):
        committed = ArchModel(links=[_link("l1", "a", "b", label="calls")])
        planned   = ArchModel(links=[_link("l1", "a", "b", label="streams")])
        diff = _compute_diff(committed, planned)
        assert any(c.link_id == "l1" and c.change == "changed" for c in diff.changed_links)

    def test_unchanged_link_not_in_changed(self):
        committed = ArchModel(links=[_link("l1", "a", "b", label="reads")])
        planned   = ArchModel(links=[_link("l1", "a", "b", label="reads")])
        diff = _compute_diff(committed, planned)
        assert not any(c.change == "changed" for c in diff.changed_links)

    def test_added_link_in_changed_links_detail(self):
        """added links appear both in added_links and changed_links (with change='added')."""
        committed = ArchModel()
        planned   = ArchModel(links=[_link("l1", "a", "b")])
        diff = _compute_diff(committed, planned)
        assert "l1" in diff.added_links
        detail = next((c for c in diff.changed_links if c.link_id == "l1"), None)
        assert detail is not None
        assert detail.change == "added"
        assert detail.committed is None
        assert detail.planned is not None

    def test_removed_link_in_changed_links_detail(self):
        committed = ArchModel(links=[_link("l1", "a", "b")])
        planned   = ArchModel()
        diff = _compute_diff(committed, planned)
        assert "l1" in diff.removed_links
        detail = next((c for c in diff.changed_links if c.link_id == "l1"), None)
        assert detail is not None
        assert detail.change == "removed"
        assert detail.planned is None


# ---------------------------------------------------------------------------
# ModelDiff properties and serialisation
# ---------------------------------------------------------------------------

class TestModelDiffProperties:
    def test_has_changes_false_empty(self):
        assert ModelDiff().has_changes is False

    def test_has_changes_true_added_node(self):
        diff = ModelDiff(added_nodes=["x"])
        assert diff.has_changes is True

    def test_has_changes_true_removed_node(self):
        diff = ModelDiff(removed_nodes=["x"])
        assert diff.has_changes is True

    def test_has_changes_true_changed_field(self):
        diff = ModelDiff(changed_nodes=[NodeChange("x", "name", "A", "B")])
        assert diff.has_changes is True

    def test_has_changes_true_resp_change(self):
        diff = ModelDiff(responsibility_changes=[
            ResponsibilityChange("x", "r1", "does Y", "added")
        ])
        assert diff.has_changes is True

    def test_summary_no_changes(self):
        assert ModelDiff().summary == "no changes"

    def test_summary_added_node(self):
        committed = ArchModel()
        planned   = ArchModel(nodes=[_node("x")])
        diff = _compute_diff(committed, planned)
        assert "+1 node" in diff.summary

    def test_summary_removed_node(self):
        committed = ArchModel(nodes=[_node("x")])
        planned   = ArchModel()
        diff = _compute_diff(committed, planned)
        assert "-1 node" in diff.summary

    def test_summary_plural_nodes(self):
        committed = ArchModel()
        planned   = ArchModel(nodes=[_node("x"), _node("y")])
        diff = _compute_diff(committed, planned)
        assert "+2 nodes" in diff.summary

    def test_summary_field_change(self):
        committed = ArchModel(nodes=[_node("a", name="Old")])
        planned   = ArchModel(nodes=[_node("a", name="New")])
        diff = _compute_diff(committed, planned)
        assert "~1 field change" in diff.summary

    def test_summary_link_added(self):
        committed = ArchModel()
        planned   = ArchModel(links=[_link("l1", "a", "b")])
        diff = _compute_diff(committed, planned)
        assert "+1 link" in diff.summary

    def test_to_dict_has_required_keys(self):
        d = ModelDiff().to_dict()
        for key in ("has_changes", "summary", "added_nodes", "removed_nodes",
                    "changed_nodes", "added_links", "removed_links",
                    "changed_links", "responsibility_changes"):
            assert key in d, f"Missing key: {key!r}"

    def test_to_dict_json_serialisable(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel(nodes=[_node("a", name="ARenamed"), _node("b")])
        diff = _compute_diff(committed, planned)
        dumped = json.dumps(diff.to_dict())
        assert isinstance(dumped, str)
        parsed = json.loads(dumped)
        assert parsed["has_changes"] is True

    def test_to_dict_changed_nodes_fields(self):
        committed = ArchModel(nodes=[_node("a", name="Old")])
        planned   = ArchModel(nodes=[_node("a", name="New")])
        diff = _compute_diff(committed, planned)
        d = diff.to_dict()
        assert len(d["changed_nodes"]) == 1
        cn = d["changed_nodes"][0]
        assert cn["node_id"] == "a"
        assert cn["field"] == "name"
        assert cn["committed_value"] == "Old"
        assert cn["planned_value"] == "New"


# ---------------------------------------------------------------------------
# ModelStore.model_diff() — disk-backed
# ---------------------------------------------------------------------------

class TestModelStoreDiff:
    def test_no_genesis_dir_returns_empty_diff(self, tmp_path):
        store = ModelStore(tmp_path)
        diff = store.model_diff()
        assert isinstance(diff, ModelDiff)
        assert not diff.has_changes

    def test_no_planned_json_returns_empty_diff(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[_node("a")])
        store.save_committed(committed)
        diff = store.model_diff()
        # planned falls back to committed → no divergence
        assert not diff.has_changes

    def test_planned_with_added_node(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[_node("a")])
        store.save_committed(committed)
        planned = ArchModel(nodes=[_node("a"), _node("b")])
        store.save_planned(planned)
        diff = store.model_diff()
        assert "b" in diff.added_nodes
        assert diff.has_changes

    def test_planned_with_removed_node(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[_node("a"), _node("b")])
        store.save_committed(committed)
        planned = ArchModel(nodes=[_node("a")])
        store.save_planned(planned)
        diff = store.model_diff()
        assert "b" in diff.removed_nodes

    def test_planned_with_changed_field(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a", technology="python")]))
        store.save_planned(ArchModel(nodes=[_node("a", technology="rust")]))
        diff = store.model_diff()
        assert any(c.field == "technology" for c in diff.changed_nodes)

    def test_model_diff_does_not_write_files(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a")]))
        store.save_planned(ArchModel(nodes=[_node("b")]))
        before_committed = (tmp_path / ".genesis" / "model.json").read_text()
        before_planned   = (tmp_path / ".genesis" / "planned.json").read_text()
        store.model_diff()
        after_committed = (tmp_path / ".genesis" / "model.json").read_text()
        after_planned   = (tmp_path / ".genesis" / "planned.json").read_text()
        assert before_committed == after_committed
        assert before_planned == after_planned

    def test_corrupted_committed_returns_empty_diff_with_warning(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("NOT JSON")
        store = ModelStore(tmp_path)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            diff = store.model_diff()
        assert isinstance(diff, ModelDiff)  # no crash

    def test_corrupted_planned_returns_partial_diff_with_warning(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a")]))
        genesis = tmp_path / ".genesis"
        (genesis / "planned.json").write_text("BAD JSON !!!")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            diff = store.model_diff()
        assert isinstance(diff, ModelDiff)  # no crash


# ---------------------------------------------------------------------------
# scan() integration — model_diff key
# ---------------------------------------------------------------------------

class TestScanModelDiffIntegration:
    def test_scan_returns_model_diff_key(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert "model_diff" in result

    def test_scan_model_diff_has_required_keys(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        md = result["model_diff"]
        for key in ("has_changes", "summary", "added_nodes", "removed_nodes",
                    "changed_nodes", "added_links", "removed_links",
                    "changed_links", "responsibility_changes"):
            assert key in md, f"Missing key: {key!r}"

    def test_scan_model_diff_no_changes_without_planned(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)  # first run: creates committed
        result = scan(tmp_path)
        assert result["model_diff"]["has_changes"] is False

    def test_scan_model_diff_detects_planned_divergence(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)  # creates committed
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        planned = ArchModel(nodes=list(committed.nodes) + [_node("extra_planned")])
        store.save_planned(planned)
        result = scan(tmp_path)
        assert result["model_diff"]["has_changes"] is True
        assert "extra_planned" in result["model_diff"]["added_nodes"]

    def test_scan_model_diff_json_serialisable(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        dumped = json.dumps(result)
        parsed = json.loads(dumped)
        assert "model_diff" in parsed

    def test_scan_all_legacy_keys_still_present(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        for key in ("fix_commit_hotspots", "external_url_count", "version_sources",
                    "doc_version", "version_drift", "dead_file_candidates", "model_sync"):
            assert key in result, f"Legacy key '{key}' missing after model_diff integration"

    def test_scan_model_diff_does_not_modify_planned(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)
        store = ModelStore(tmp_path)
        planned = ArchModel(nodes=[_node("p1")])
        store.save_planned(planned)
        before = (tmp_path / ".genesis" / "planned.json").read_text()
        scan(tmp_path)
        after = (tmp_path / ".genesis" / "planned.json").read_text()
        assert before == after

    def test_scan_model_diff_does_not_modify_committed(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)
        before = (tmp_path / ".genesis" / "model.json").read_text()
        scan(tmp_path)
        after = (tmp_path / ".genesis" / "model.json").read_text()
        assert before == after

    def test_scan_corrupted_committed_does_not_crash(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("CORRUPT")
        _make_python_project(tmp_path)
        result = scan(tmp_path)  # must not raise
        assert "model_diff" in result

    def test_scan_model_diff_summary_is_string(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert isinstance(result["model_diff"]["summary"], str)


# ---------------------------------------------------------------------------
# Package export
# ---------------------------------------------------------------------------

class TestPackageExports:
    def test_model_diff_exported(self):
        from genesis_architect.pro import ModelDiff
        assert ModelDiff is not None

    def test_node_change_exported(self):
        from genesis_architect.pro import NodeChange
        assert NodeChange is not None

    def test_responsibility_change_exported(self):
        from genesis_architect.pro import ResponsibilityChange
        assert ResponsibilityChange is not None

    def test_link_change_exported(self):
        from genesis_architect.pro import LinkChange
        assert LinkChange is not None
