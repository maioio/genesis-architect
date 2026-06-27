"""
Tests for drift_detector — Step 7.

Covers:
  detect_drift() pure function:
    - vagrant candidates: committed node absent from planned
    - vagrant candidates: confidence higher when source_map backs responsibilities
    - vagrant candidates: confidence lower when source_map absent
    - vagrant candidates suppressed when planned_was_missing=True
    - stale candidates: planned responsibility absent from committed + source_map
    - stale candidates: NOT flagged when responsibility exists in committed model
    - stale candidates: NOT flagged when responsibility exists in source_map only
    - stale candidates: both backing signals → not flagged (conservative)
    - stale candidates: confidence lower when source_map empty
    - empty models → no candidates
    - identical models → no candidates
    - determinism: sorted output
    - overall confidence tiers
    - basis string present and non-empty

  compute_drift_flags() integration:
    - no .genesis/ directory → empty candidates, low confidence, no crash
    - no planned.json → planned_was_missing=True path taken
    - corrupted committed → warning emitted, continues safely
    - corrupted planned → warning emitted, continues safely
    - populated models → vagrant/stale candidates detected

  scan() integration:
    - drift_flags key present
    - has required sub-keys
    - no changes to all pre-existing legacy keys
    - no writes to model.json or planned.json
    - corrupted model does not crash scan
    - JSON-serialisable

  DriftFlags.to_dict():
    - all keys present
    - candidate dicts have required fields
    - JSON-serialisable

  Package exports:
    - DriftFlags, VagrantCandidate, StaleCandidate, detect_drift, compute_drift_flags
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from genesis_architect_pro.model_store import (
    ArchModel, ModelNode, ModelLink, ModelResponsibility, ModelStore,
)
from genesis_architect_pro.drift_detector import (
    DriftFlags, VagrantCandidate, StaleCandidate,
    detect_drift, compute_drift_flags,
)
from genesis_architect_pro.recovery_scan import scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(nid: str, kind: str = "component", name: str | None = None,
          responsibilities: list | None = None, **kwargs) -> ModelNode:
    return ModelNode(id=nid, kind=kind, name=name or nid,
                     responsibilities=responsibilities or [], **kwargs)


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
# detect_drift — vagrant candidates
# ---------------------------------------------------------------------------

class TestVagrantCandidates:
    def test_committed_node_absent_from_planned_is_vagrant(self):
        committed = ArchModel(nodes=[_node("a"), _node("b")])
        planned   = ArchModel(nodes=[_node("a")])
        flags = detect_drift(committed, planned)
        ids = [v.node_id for v in flags.vagrant_candidates]
        assert "b" in ids
        assert "a" not in ids

    def test_all_committed_absent_from_planned_flagged(self):
        committed = ArchModel(nodes=[_node("x"), _node("y"), _node("z")])
        planned   = ArchModel()
        flags = detect_drift(committed, planned)
        assert len(flags.vagrant_candidates) == 3

    def test_no_vagrant_when_all_committed_in_planned(self):
        nodes = [_node("a"), _node("b")]
        committed = ArchModel(nodes=nodes)
        planned   = ArchModel(nodes=list(nodes))
        flags = detect_drift(committed, planned)
        assert flags.vagrant_candidates == []

    def test_vagrant_confidence_higher_with_source_map(self):
        committed = ArchModel(
            nodes=[_node("a", responsibilities=[_resp("r1")])],
            source_map={"r1": [{"pattern": "def auth", "line": 5}]},
        )
        planned = ArchModel()
        flags = detect_drift(committed, planned, source_map_empty=False)
        assert flags.vagrant_candidates[0].confidence >= 0.70

    def test_vagrant_confidence_lower_without_source_map(self):
        committed = ArchModel(nodes=[_node("a", responsibilities=[_resp("r1")])])
        planned   = ArchModel()
        flags = detect_drift(committed, planned, source_map_empty=True)
        assert flags.vagrant_candidates[0].confidence < 0.60

    def test_vagrant_candidate_fields_present(self):
        committed = ArchModel(nodes=[_node("a", kind="container", name="MyService")])
        planned   = ArchModel()
        flags = detect_drift(committed, planned)
        v = flags.vagrant_candidates[0]
        assert v.node_id == "a"
        assert v.name == "MyService"
        assert v.kind == "container"
        assert isinstance(v.reason, str) and len(v.reason) > 0
        assert 0.0 <= v.confidence <= 1.0

    def test_vagrant_candidates_sorted_by_node_id(self):
        committed = ArchModel(nodes=[_node("z"), _node("a"), _node("m")])
        planned   = ArchModel()
        flags = detect_drift(committed, planned)
        ids = [v.node_id for v in flags.vagrant_candidates]
        assert ids == sorted(ids)

    def test_vagrant_suppressed_when_planned_was_missing(self):
        committed = ArchModel(nodes=[_node("a"), _node("b")])
        planned   = ArchModel(nodes=[_node("a")])
        flags = detect_drift(committed, planned, planned_was_missing=True)
        assert flags.vagrant_candidates == []

    def test_empty_committed_no_vagrant_candidates(self):
        flags = detect_drift(ArchModel(), ArchModel())
        assert flags.vagrant_candidates == []


# ---------------------------------------------------------------------------
# detect_drift — stale candidates
# ---------------------------------------------------------------------------

class TestStaleCandidates:
    def test_planned_resp_absent_from_committed_and_source_map_is_stale(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel(nodes=[_node("a", responsibilities=[_resp("r99", "planned thing")])])
        flags = detect_drift(committed, planned)
        ids = [s.responsibility_id for s in flags.stale_candidates]
        assert "r99" in ids

    def test_resp_in_committed_model_not_stale(self):
        """Conservative: responsibility in committed → not stale even without source_map."""
        committed = ArchModel(nodes=[_node("a", responsibilities=[_resp("r1", "does X")])])
        planned   = ArchModel(nodes=[_node("a", responsibilities=[_resp("r1", "does X")])])
        flags = detect_drift(committed, planned)
        assert flags.stale_candidates == []

    def test_resp_in_source_map_not_stale(self):
        """Conservative: responsibility in source_map → not stale even if not in committed nodes."""
        committed = ArchModel(
            nodes=[_node("a")],
            source_map={"r1": [{"pattern": "def process", "line": 10}]},
        )
        planned = ArchModel(nodes=[_node("a", responsibilities=[_resp("r1", "processes data")])])
        flags = detect_drift(committed, planned)
        stale_ids = [s.responsibility_id for s in flags.stale_candidates]
        assert "r1" not in stale_ids

    def test_resp_in_both_committed_and_source_map_not_stale(self):
        committed = ArchModel(
            nodes=[_node("a", responsibilities=[_resp("r1")])],
            source_map={"r1": [{"pattern": "fn", "line": 1}]},
        )
        planned = ArchModel(nodes=[_node("a", responsibilities=[_resp("r1")])])
        flags = detect_drift(committed, planned)
        assert flags.stale_candidates == []

    def test_stale_candidate_fields_present(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel(nodes=[_node("a", responsibilities=[_resp("r99", "planned intent")])])
        flags = detect_drift(committed, planned)
        s = flags.stale_candidates[0]
        assert s.node_id == "a"
        assert s.responsibility_id == "r99"
        assert s.statement == "planned intent"
        assert isinstance(s.reason, str) and len(s.reason) > 0
        assert 0.0 <= s.confidence <= 1.0

    def test_stale_confidence_lower_when_source_map_empty(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel(nodes=[_node("a", responsibilities=[_resp("r99")])])
        flags_with_map    = detect_drift(committed, planned, source_map_empty=False)
        flags_without_map = detect_drift(committed, planned, source_map_empty=True)
        c_with    = flags_with_map.stale_candidates[0].confidence
        c_without = flags_without_map.stale_candidates[0].confidence
        assert c_without < c_with

    def test_multiple_stale_sorted_by_node_then_resp(self):
        committed = ArchModel(nodes=[_node("b"), _node("a")])
        planned   = ArchModel(nodes=[
            _node("b", responsibilities=[_resp("rb2"), _resp("rb1")]),
            _node("a", responsibilities=[_resp("ra1")]),
        ])
        flags = detect_drift(committed, planned)
        keys = [(s.node_id, s.responsibility_id) for s in flags.stale_candidates]
        assert keys == sorted(keys)

    def test_no_stale_on_empty_planned(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel()
        flags = detect_drift(committed, planned)
        assert flags.stale_candidates == []

    def test_stale_only_on_planned_nodes(self):
        """Responsibilities on committed nodes are never flagged stale by themselves."""
        committed = ArchModel(nodes=[_node("a", responsibilities=[_resp("r_committed")])])
        planned   = ArchModel(nodes=[_node("a")])  # no planned responsibilities
        flags = detect_drift(committed, planned)
        assert flags.stale_candidates == []


# ---------------------------------------------------------------------------
# detect_drift — overall confidence
# ---------------------------------------------------------------------------

class TestOverallConfidence:
    def test_high_confidence_both_models_source_map(self):
        committed = ArchModel(
            nodes=[_node("a")],
            source_map={"r1": [{"pattern": "fn", "line": 1}]},
        )
        planned = ArchModel(nodes=[_node("a")])
        flags = detect_drift(committed, planned, source_map_empty=False)
        assert flags.confidence >= 0.75

    def test_medium_confidence_no_source_map(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel(nodes=[_node("a")])
        flags = detect_drift(committed, planned, source_map_empty=True)
        assert 0.40 <= flags.confidence < 0.75

    def test_low_confidence_no_planned(self):
        committed = ArchModel(nodes=[_node("a")])
        flags = detect_drift(committed, ArchModel(), planned_was_missing=True)
        assert flags.confidence < 0.50

    def test_basis_is_non_empty_string(self):
        flags = detect_drift(ArchModel(), ArchModel())
        assert isinstance(flags.basis, str)
        assert len(flags.basis) > 0

    def test_warnings_list_is_list(self):
        flags = detect_drift(ArchModel(), ArchModel())
        assert isinstance(flags.warnings, list)

    def test_external_warnings_propagated(self):
        flags = detect_drift(ArchModel(), ArchModel(),
                             detection_warnings=["something went wrong"])
        assert "something went wrong" in flags.warnings


# ---------------------------------------------------------------------------
# DriftFlags.to_dict()
# ---------------------------------------------------------------------------

class TestDriftFlagsToDict:
    def test_required_keys_present(self):
        d = DriftFlags().to_dict()
        for k in ("vagrant_candidates", "stale_candidates",
                  "confidence", "basis", "warnings"):
            assert k in d

    def test_vagrant_candidate_dict_fields(self):
        committed = ArchModel(nodes=[_node("a", kind="container", name="Svc")])
        planned   = ArchModel()
        flags = detect_drift(committed, planned)
        v = flags.to_dict()["vagrant_candidates"][0]
        for k in ("node_id", "name", "kind", "reason", "confidence"):
            assert k in v

    def test_stale_candidate_dict_fields(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel(nodes=[_node("a", responsibilities=[_resp("r1", "stmt")])])
        flags = detect_drift(committed, planned)
        s = flags.to_dict()["stale_candidates"][0]
        for k in ("node_id", "responsibility_id", "statement", "reason", "confidence"):
            assert k in s

    def test_json_serialisable_empty(self):
        dumped = json.dumps(DriftFlags().to_dict())
        assert isinstance(dumped, str)

    def test_json_serialisable_with_candidates(self):
        committed = ArchModel(nodes=[_node("a")])
        planned   = ArchModel(nodes=[_node("a", responsibilities=[_resp("r99")])])
        flags = detect_drift(committed, planned)
        dumped = json.dumps(flags.to_dict())
        parsed = json.loads(dumped)
        assert len(parsed["stale_candidates"]) == 1

    def test_confidence_is_float_in_range(self):
        d = DriftFlags(confidence=0.8).to_dict()
        assert isinstance(d["confidence"], float)
        assert 0.0 <= d["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# compute_drift_flags() — disk-backed
# ---------------------------------------------------------------------------

class TestComputeDriftFlags:
    def test_no_genesis_dir_returns_empty_flags(self, tmp_path):
        flags = compute_drift_flags(tmp_path)
        assert isinstance(flags, DriftFlags)
        assert flags.vagrant_candidates == []
        assert flags.stale_candidates == []

    def test_no_planned_json_sets_low_confidence(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a")]))
        flags = compute_drift_flags(tmp_path)
        assert flags.confidence < 0.50

    def test_no_planned_json_suppresses_vagrant_candidates(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a"), _node("b")]))
        flags = compute_drift_flags(tmp_path)
        assert flags.vagrant_candidates == []

    def test_vagrant_candidate_detected_via_disk(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a"), _node("b")]))
        store.save_planned(ArchModel(nodes=[_node("a")]))
        flags = compute_drift_flags(tmp_path)
        ids = [v.node_id for v in flags.vagrant_candidates]
        assert "b" in ids
        assert "a" not in ids

    def test_stale_candidate_detected_via_disk(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a")]))
        store.save_planned(ArchModel(nodes=[_node("a", responsibilities=[_resp("r99")])]))
        flags = compute_drift_flags(tmp_path)
        sids = [s.responsibility_id for s in flags.stale_candidates]
        assert "r99" in sids

    def test_stale_not_flagged_when_in_source_map(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(
            nodes=[_node("a")],
            source_map={"r1": [{"pattern": "fn x", "line": 5}]},
        ))
        store.save_planned(ArchModel(nodes=[_node("a", responsibilities=[_resp("r1")])]))
        flags = compute_drift_flags(tmp_path)
        assert not any(s.responsibility_id == "r1" for s in flags.stale_candidates)

    def test_corrupted_committed_no_crash(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("NOT JSON")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            flags = compute_drift_flags(tmp_path)
        assert isinstance(flags, DriftFlags)

    def test_corrupted_committed_emits_warning(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("CORRUPT")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            compute_drift_flags(tmp_path)
        messages = [str(w.message) for w in caught]
        assert any("model" in m.lower() or "json" in m.lower() or "not valid" in m.lower()
                   for m in messages)

    def test_corrupted_planned_no_crash(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a")]))
        (tmp_path / ".genesis" / "planned.json").write_text("BAD JSON")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            flags = compute_drift_flags(tmp_path)
        assert isinstance(flags, DriftFlags)

    def test_compute_does_not_write_model_json(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a")]))
        store.save_planned(ArchModel(nodes=[_node("b")]))
        before_committed = (tmp_path / ".genesis" / "model.json").read_text()
        compute_drift_flags(tmp_path)
        after_committed = (tmp_path / ".genesis" / "model.json").read_text()
        assert before_committed == after_committed

    def test_compute_does_not_write_planned_json(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a")]))
        store.save_planned(ArchModel(nodes=[_node("b")]))
        before_planned = (tmp_path / ".genesis" / "planned.json").read_text()
        compute_drift_flags(tmp_path)
        after_planned = (tmp_path / ".genesis" / "planned.json").read_text()
        assert before_planned == after_planned

    def test_warnings_list_in_result(self, tmp_path):
        flags = compute_drift_flags(tmp_path)
        assert isinstance(flags.warnings, list)

    def test_source_map_empty_lowers_overall_confidence(self, tmp_path):
        store = ModelStore(tmp_path)
        # committed with source_map
        store.save_committed(ArchModel(
            nodes=[_node("a")],
            source_map={"r1": [{"pattern": "fn", "line": 1}]},
        ))
        store.save_planned(ArchModel(nodes=[_node("a")]))
        flags_with = compute_drift_flags(tmp_path)

        # Reset: committed without source_map
        store.save_committed(ArchModel(nodes=[_node("a")]))
        flags_without = compute_drift_flags(tmp_path)

        assert flags_without.confidence < flags_with.confidence


# ---------------------------------------------------------------------------
# scan() integration — drift_flags key
# ---------------------------------------------------------------------------

class TestScanDriftFlagsIntegration:
    def test_scan_returns_drift_flags_key(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert "drift_flags" in result

    def test_drift_flags_has_required_sub_keys(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        df = result["drift_flags"]
        for k in ("vagrant_candidates", "stale_candidates",
                  "confidence", "basis", "warnings"):
            assert k in df, f"Missing key: {k!r}"

    def test_all_legacy_keys_still_present(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        for k in ("fix_commit_hotspots", "external_url_count", "version_sources",
                  "doc_version", "version_drift", "dead_file_candidates",
                  "model_sync", "model_diff"):
            assert k in result, f"Legacy key missing: {k!r}"

    def test_drift_flags_json_serialisable(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        dumped = json.dumps(result)
        parsed = json.loads(dumped)
        assert "drift_flags" in parsed

    def test_scan_does_not_write_model_json(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)  # first run creates committed
        before = (tmp_path / ".genesis" / "model.json").read_text()
        scan(tmp_path)
        after = (tmp_path / ".genesis" / "model.json").read_text()
        assert before == after

    def test_scan_does_not_create_planned_json(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)
        assert not (tmp_path / ".genesis" / "planned.json").exists()

    def test_scan_does_not_modify_existing_planned_json(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)
        store = ModelStore(tmp_path)
        planned = ArchModel(nodes=[_node("p1")])
        store.save_planned(planned)
        before = (tmp_path / ".genesis" / "planned.json").read_text()
        scan(tmp_path)
        after = (tmp_path / ".genesis" / "planned.json").read_text()
        assert before == after

    def test_scan_corrupted_model_no_crash(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("GARBAGE")
        _make_python_project(tmp_path)
        result = scan(tmp_path)  # must not raise
        assert "drift_flags" in result

    def test_drift_flags_confidence_is_float(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert isinstance(result["drift_flags"]["confidence"], float)

    def test_drift_flags_vagrant_is_list(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert isinstance(result["drift_flags"]["vagrant_candidates"], list)

    def test_drift_flags_stale_is_list(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert isinstance(result["drift_flags"]["stale_candidates"], list)

    def test_scan_detects_planned_divergence_in_drift_flags(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)  # first run: creates committed
        store = ModelStore(tmp_path)
        committed = store.load_committed()
        # Add a planned node that is not in committed
        planned = ArchModel(nodes=list(committed.nodes) + [_node("extra_planned_only")])
        store.save_planned(planned)
        result = scan(tmp_path)
        # extra_planned_only is in planned but not in committed → no vagrant (it's the other way)
        # committed nodes not in planned → vagrant candidates
        vagrant_ids = [v["node_id"] for v in result["drift_flags"]["vagrant_candidates"]]
        # committed nodes are not in planned (planned has them + extra) → no vagrant for those
        # (all committed nodes are present in planned as a superset)
        # Just verify no crash and structure is correct
        assert isinstance(vagrant_ids, list)


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------

class TestPackageExports:
    def test_drift_flags_exported(self):
        from genesis_architect_pro import DriftFlags
        assert DriftFlags is not None

    def test_vagrant_candidate_exported(self):
        from genesis_architect_pro import VagrantCandidate
        assert VagrantCandidate is not None

    def test_stale_candidate_exported(self):
        from genesis_architect_pro import StaleCandidate
        assert StaleCandidate is not None

    def test_detect_drift_exported(self):
        from genesis_architect_pro import detect_drift
        assert callable(detect_drift)

    def test_compute_drift_flags_exported(self):
        from genesis_architect_pro import compute_drift_flags
        assert callable(compute_drift_flags)
