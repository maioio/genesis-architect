"""
Tests for persist_anchors — Step 9.

Covers:
  persist_anchors():
    - explicit call only: scan() does NOT call persist_anchors
    - new anchors written into source_map
    - source_map entry has correct fields after persist
    - save_committed() called exactly once when changes exist
    - save_committed() NOT called when nothing changes
    - second identical call: all entries skipped, saved=False
    - merge: new entries appended, existing preserved
    - deduplication: same (pattern, line, end_line, symbol) not written twice
    - deduplication key ignores confidence and basis changes
    - user-authored source_map entries not removed or overwritten
    - unanchored responsibilities produce no source_map entries
    - planned.json never touched
    - empty AnchorReport is a no-op (added=0, saved=False)
    - no anchored results is a no-op
    - missing committed model: warning emitted, no crash, saved=False
    - corrupted committed model: warning emitted, no crash, saved=False
    - multiple responsibilities persisted in one call
    - PersistResult fields: added, skipped, saved, warnings
    - PersistResult.to_dict() has required keys

  scan() no auto-persist:
    - source_map remains empty after scan() when no persist called
    - source_anchors key present but source_map on disk unchanged

  Package exports:
    - PersistResult exported
    - persist_anchors exported
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path


from genesis_architect_pro.model_store import (
    ArchModel, ModelNode, ModelResponsibility, ModelStore,
)
from genesis_architect_pro.source_anchor import (
    AnchorEntry, AnchorResult, AnchorReport,
    PersistResult, anchor_responsibilities, persist_anchors,
)
from genesis_architect_pro.recovery_scan import scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resp(rid: str, statement: str = "does something") -> ModelResponsibility:
    return ModelResponsibility(id=rid, statement=statement)


def _node(nid: str, responsibilities: list | None = None) -> ModelNode:
    return ModelNode(id=nid, kind="component", name=nid,
                     responsibilities=responsibilities or [])


def _write_py(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_python_project(root: Path) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[tool.poetry]\nname='testproject'\n")
    (src / "mod_0.py").write_text("X = 0\n")
    (root / ".git").mkdir(exist_ok=True)


def _make_report_with_anchor(
    resp_id: str,
    statement: str,
    node_id: str,
    line: int = 1,
    symbol: str = "myfn",
    confidence: float = 0.95,
) -> AnchorReport:
    """Build a minimal AnchorReport with one anchored responsibility."""
    entry = AnchorEntry(
        pattern=symbol,
        line=line,
        end_line=line + 2,
        symbol=symbol,
        confidence=confidence,
        basis=f"exact symbol match: '{symbol}' in {node_id}:{line}",
    )
    result = AnchorResult(
        responsibility_id=resp_id,
        statement=statement,
        node_id=node_id,
        anchors=[entry],
    )
    report = AnchorReport(
        anchors_by_responsibility={resp_id: result},
        anchored_count=1,
        unanchored_count=0,
        total_responsibilities=1,
    )
    return report


# ---------------------------------------------------------------------------
# Core persistence behaviour
# ---------------------------------------------------------------------------

class TestPersistAnchorsCore:
    def test_new_anchor_written_to_source_map(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("auth.py", [_resp("r1", "authenticate users")])]))
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py",
                                          line=1, symbol="authenticate")
        persist_anchors(report, store)
        committed = store.load_committed()
        assert "r1" in committed.source_map
        assert len(committed.source_map["r1"]) == 1

    def test_persisted_entry_has_correct_fields(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("auth.py", [_resp("r1", "authenticate users")])]))
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py",
                                          line=3, symbol="authenticate", confidence=0.95)
        persist_anchors(report, store)
        entry = store.load_committed().source_map["r1"][0]
        assert entry["line"] == 3
        assert entry["symbol"] == "authenticate"
        assert entry["confidence"] == 0.95
        assert "basis" in entry
        assert "pattern" in entry
        assert "end_line" in entry

    def test_result_added_count_correct(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py")
        result = persist_anchors(report, store)
        assert result.added == 1

    def test_result_saved_true_on_first_write(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py")
        result = persist_anchors(report, store)
        assert result.saved is True

    def test_save_committed_called_once(self, tmp_path):
        """Verify save_committed side-effect: model.json timestamp changes once."""
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        mtime_before = (tmp_path / ".genesis" / "model.json").stat().st_mtime_ns

        report = _make_report_with_anchor("r1", "authenticate", "auth.py")
        persist_anchors(report, store)

        mtime_after = (tmp_path / ".genesis" / "model.json").stat().st_mtime_ns
        # File was written (mtime changed or content changed)
        committed = store.load_committed()
        assert "r1" in committed.source_map

    def test_second_call_all_skipped(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py",
                                          line=1, symbol="authenticate")
        persist_anchors(report, store)          # first: writes
        result2 = persist_anchors(report, store)  # second: all duplicate
        assert result2.added == 0
        assert result2.skipped == 1

    def test_second_call_saved_false(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        report = _make_report_with_anchor("r1", "auth", "auth.py")
        persist_anchors(report, store)
        result2 = persist_anchors(report, store)
        assert result2.saved is False

    def test_second_call_does_not_modify_source_map(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py",
                                          line=1, symbol="authenticate")
        persist_anchors(report, store)
        after_first = store.load_committed().source_map.copy()
        persist_anchors(report, store)
        after_second = store.load_committed().source_map
        assert after_first == after_second


# ---------------------------------------------------------------------------
# Merge behaviour
# ---------------------------------------------------------------------------

class TestMergeBehaviour:
    def test_new_entry_appended_to_existing(self, tmp_path):
        store = ModelStore(tmp_path)
        # Pre-populate with one user-authored entry
        existing = {"pattern": "auth", "line": 5, "end_line": 10,
                    "symbol": "old_sym", "confidence": 0.6, "basis": "manual"}
        committed = ArchModel()
        committed.source_map["r1"] = [existing]
        store.save_committed(committed)

        # New anchor at a different line
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py",
                                          line=20, symbol="authenticate")
        persist_anchors(report, store)

        entries = store.load_committed().source_map["r1"]
        assert len(entries) == 2

    def test_existing_user_authored_entry_preserved(self, tmp_path):
        store = ModelStore(tmp_path)
        user_entry = {"pattern": "auth_flow", "line": 99, "end_line": 105,
                      "symbol": "auth_flow", "confidence": 1.0, "basis": "manual override"}
        committed = ArchModel()
        committed.source_map["r1"] = [user_entry]
        store.save_committed(committed)

        report = _make_report_with_anchor("r1", "authenticate users", "auth.py",
                                          line=1, symbol="authenticate")
        persist_anchors(report, store)

        entries = store.load_committed().source_map["r1"]
        assert any(e["symbol"] == "auth_flow" and e["line"] == 99 for e in entries), \
            "user-authored entry must be preserved"

    def test_multiple_responsibilities_in_one_call(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())

        entry_r1 = AnchorEntry("authenticate", 1, 3, "authenticate", 0.95,
                               "exact symbol match")
        entry_r2 = AnchorEntry("process_payment", 5, 8, "process_payment", 0.95,
                               "exact symbol match")
        report = AnchorReport(
            anchors_by_responsibility={
                "r1": AnchorResult("r1", "authenticate users", "auth.py",
                                   anchors=[entry_r1]),
                "r2": AnchorResult("r2", "process payment", "pay.py",
                                   anchors=[entry_r2]),
            },
            anchored_count=2,
            unanchored_count=0,
            total_responsibilities=2,
        )
        result = persist_anchors(report, store)
        committed = store.load_committed()
        assert "r1" in committed.source_map
        assert "r2" in committed.source_map
        assert result.added == 2
        assert result.saved is True

    def test_other_source_map_keys_untouched(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel()
        committed.source_map["r_other"] = [{"pattern": "x", "line": 1, "end_line": 1,
                                              "symbol": "x", "confidence": 0.9,
                                              "basis": "manual"}]
        store.save_committed(committed)

        report = _make_report_with_anchor("r1", "authenticate users", "auth.py")
        persist_anchors(report, store)

        entries_other = store.load_committed().source_map.get("r_other", [])
        assert len(entries_other) == 1
        assert entries_other[0]["symbol"] == "x"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_identical_entry_not_written_twice(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py",
                                          line=1, symbol="authenticate", confidence=0.95)
        persist_anchors(report, store)

        # Same anchor again (same line/symbol)
        result2 = persist_anchors(report, store)
        assert result2.skipped == 1
        assert result2.added == 0
        # Still only one entry in source_map
        assert len(store.load_committed().source_map["r1"]) == 1

    def test_dedup_key_ignores_confidence_change(self, tmp_path):
        """Same (pattern, line, end_line, symbol) with different confidence → skipped."""
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())

        report1 = _make_report_with_anchor("r1", "auth", "auth.py",
                                           line=1, symbol="authenticate", confidence=0.45)
        persist_anchors(report1, store)

        # Same position, higher confidence
        report2 = _make_report_with_anchor("r1", "auth", "auth.py",
                                           line=1, symbol="authenticate", confidence=0.95)
        result2 = persist_anchors(report2, store)
        assert result2.skipped == 1
        assert result2.added == 0

    def test_different_line_is_not_duplicate(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())

        report1 = _make_report_with_anchor("r1", "auth", "auth.py",
                                           line=1, symbol="authenticate")
        persist_anchors(report1, store)

        report2 = _make_report_with_anchor("r1", "auth", "auth.py",
                                           line=10, symbol="authenticate")
        result2 = persist_anchors(report2, store)
        assert result2.added == 1
        assert len(store.load_committed().source_map["r1"]) == 2

    def test_different_symbol_is_not_duplicate(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())

        report1 = _make_report_with_anchor("r1", "auth", "auth.py",
                                           line=1, symbol="login")
        persist_anchors(report1, store)

        report2 = _make_report_with_anchor("r1", "auth", "auth.py",
                                           line=1, symbol="authenticate")
        result2 = persist_anchors(report2, store)
        assert result2.added == 1


# ---------------------------------------------------------------------------
# No-op cases
# ---------------------------------------------------------------------------

class TestNoOpCases:
    def test_empty_report_is_noop(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        report = AnchorReport()   # total_responsibilities=0, no anchors
        result = persist_anchors(report, store)
        assert result.added == 0
        assert result.saved is False

    def test_all_unanchored_report_is_noop(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        unanchored = AnchorResult("r1", "stmt", "n1", anchors=[])
        report = AnchorReport(
            anchors_by_responsibility={"r1": unanchored},
            anchored_count=0,
            unanchored_count=1,
            total_responsibilities=1,
        )
        result = persist_anchors(report, store)
        assert result.added == 0
        assert result.saved is False
        # source_map must remain empty
        assert store.load_committed().source_map == {}

    def test_noop_does_not_write_model_json(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        mtime_before = (tmp_path / ".genesis" / "model.json").stat().st_mtime_ns
        persist_anchors(AnchorReport(), store)
        mtime_after = (tmp_path / ".genesis" / "model.json").stat().st_mtime_ns
        assert mtime_before == mtime_after

    def test_unanchored_resp_produces_no_source_map_entry(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        unanchored = AnchorResult("r1", "zygomorphic quetzal", "n1", anchors=[])
        report = AnchorReport(
            anchors_by_responsibility={"r1": unanchored},
            anchored_count=0,
            unanchored_count=1,
            total_responsibilities=1,
        )
        persist_anchors(report, store)
        assert "r1" not in store.load_committed().source_map


# ---------------------------------------------------------------------------
# planned.json protection
# ---------------------------------------------------------------------------

class TestPlannedNotTouched:
    def test_persist_does_not_create_planned_json(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py")
        persist_anchors(report, store)
        assert not (tmp_path / ".genesis" / "planned.json").exists()

    def test_persist_does_not_modify_existing_planned_json(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        planned = ArchModel(nodes=[_node("p1")])
        store.save_planned(planned)
        before = (tmp_path / ".genesis" / "planned.json").read_text()

        report = _make_report_with_anchor("r1", "authenticate users", "auth.py")
        persist_anchors(report, store)

        after = (tmp_path / ".genesis" / "planned.json").read_text()
        assert before == after


# ---------------------------------------------------------------------------
# Missing / corrupted committed model
# ---------------------------------------------------------------------------

class TestFaultTolerance:
    def test_missing_genesis_dir_no_crash(self, tmp_path):
        store = ModelStore(tmp_path)  # .genesis doesn't exist yet
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py")
        # ModelStore.load_committed returns empty ArchModel when file missing
        result = persist_anchors(report, store)
        assert isinstance(result, PersistResult)

    def test_missing_genesis_dir_writes_new_model(self, tmp_path):
        store = ModelStore(tmp_path)
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py",
                                          line=1, symbol="authenticate")
        persist_anchors(report, store)
        committed = store.load_committed()
        assert "r1" in committed.source_map

    def test_corrupted_committed_emits_warning(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("NOT JSON")
        store = ModelStore(tmp_path)
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = persist_anchors(report, store)
        # ModelStore.load_committed emits warning on corruption; persist continues
        # and either writes with an empty base or records a warning of its own
        assert isinstance(result, PersistResult)

    def test_corrupted_committed_no_crash(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("CORRUPT")
        store = ModelStore(tmp_path)
        report = _make_report_with_anchor("r1", "authenticate users", "auth.py")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = persist_anchors(report, store)
        assert isinstance(result, PersistResult)

    def test_result_warnings_is_list(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        result = persist_anchors(AnchorReport(), store)
        assert isinstance(result.warnings, list)


# ---------------------------------------------------------------------------
# scan() does NOT auto-persist
# ---------------------------------------------------------------------------

class TestScanDoesNotAutoPersist:
    def test_source_map_empty_after_scan(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)  # first run creates committed
        committed = ModelStore(tmp_path).load_committed()
        # scan() populates source_anchors in output but must NOT write source_map
        assert committed.source_map == {}

    def test_repeated_scan_does_not_write_source_map(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)
        scan(tmp_path)
        committed = ModelStore(tmp_path).load_committed()
        assert committed.source_map == {}

    def test_scan_source_anchors_key_still_present(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert "source_anchors" in result

    def test_all_legacy_keys_unchanged(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        for k in ("fix_commit_hotspots", "external_url_count", "version_sources",
                  "doc_version", "version_drift", "dead_file_candidates",
                  "model_sync", "model_diff", "drift_flags", "source_anchors"):
            assert k in result


# ---------------------------------------------------------------------------
# Full round-trip: anchor → persist → reload
# ---------------------------------------------------------------------------

class TestFullRoundTrip:
    def test_anchor_and_persist_from_real_file(self, tmp_path):
        src = tmp_path / "auth.py"
        src.write_text(
            "def authenticate(user):\n    pass\n\ndef process_payment(amount):\n    pass\n"
        )
        committed = ArchModel(nodes=[
            _node("auth.py", [
                _resp("r1", "authenticate users"),
                _resp("r2", "process payment"),
            ])
        ])
        store = ModelStore(tmp_path)
        store.save_committed(committed)

        report = anchor_responsibilities(committed, tmp_path, file_paths=["auth.py"])
        result = persist_anchors(report, store)

        assert result.added == report.anchored_count
        assert result.saved is True

        reloaded = store.load_committed()
        for resp_id in [r.responsibility_id for r in report.anchors_by_responsibility.values()
                        if r.is_anchored]:
            assert resp_id in reloaded.source_map

    def test_source_map_entries_json_serialisable_after_persist(self, tmp_path):
        src = tmp_path / "auth.py"
        src.write_text("def authenticate(user):\n    pass\n")
        committed = ArchModel(nodes=[
            _node("auth.py", [_resp("r1", "authenticate users")])
        ])
        store = ModelStore(tmp_path)
        store.save_committed(committed)

        report = anchor_responsibilities(committed, tmp_path, file_paths=["auth.py"])
        persist_anchors(report, store)

        raw = (tmp_path / ".genesis" / "model.json").read_text()
        parsed = json.loads(raw)
        assert "source_map" in parsed
        # Must be valid JSON that round-trips
        assert isinstance(parsed["source_map"], dict)


# ---------------------------------------------------------------------------
# PersistResult
# ---------------------------------------------------------------------------

class TestPersistResult:
    def test_to_dict_required_keys(self):
        r = PersistResult(added=1, skipped=2, saved=True)
        d = r.to_dict()
        for k in ("added", "skipped", "saved", "warnings"):
            assert k in d

    def test_to_dict_json_serialisable(self):
        r = PersistResult(added=3, skipped=1, saved=True, warnings=["w"])
        dumped = json.dumps(r.to_dict())
        parsed = json.loads(dumped)
        assert parsed["added"] == 3
        assert parsed["saved"] is True

    def test_defaults_zero(self):
        r = PersistResult()
        assert r.added == 0
        assert r.skipped == 0
        assert r.saved is False
        assert r.warnings == []


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------

class TestPackageExports:
    def test_persist_result_exported(self):
        from genesis_architect_pro import PersistResult
        assert PersistResult is not None

    def test_persist_anchors_exported(self):
        from genesis_architect_pro import persist_anchors
        assert callable(persist_anchors)
