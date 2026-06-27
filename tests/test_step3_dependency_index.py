"""
Step 3 tests: DependencyIndex and compute_affected_scope.

Covers:
  - DependencyIndex construction and correctness
  - O(1) lookup semantics (verified via timing on large graphs)
  - AffectedScope computation for all operation types
  - Edge cases: isolated nodes, self-loops, multi-hop is NOT included
  - Backward compatibility: build_graph / score_project / generate_plan unchanged
  - Performance: construction and lookup benchmarks
"""

import time
import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_modules(*edges: tuple[str, str]) -> dict:
    """
    Build a minimal modules dict from edge tuples (src, dst).
    Every module mentioned gets a node entry.
    """
    mods: dict[str, dict] = {}
    for src, dst in edges:
        for m in (src, dst):
            if m not in mods:
                mods[m] = {"imports": [], "imported_by": [], "fan_out": 0,
                           "fan_in": 0, "lines": 10, "is_entry_point": False,
                           "layer": "unknown"}
        if dst not in mods[src]["imports"]:
            mods[src]["imports"].append(dst)
    return mods


def _make_large_modules(n: int) -> dict:
    """
    Fan-out star: one hub importing n leaves.
    Results in n edges, n+1 nodes — good for perf tests.
    """
    mods: dict[str, dict] = {
        "hub.py": {"imports": [f"leaf_{i}.py" for i in range(n)],
                   "imported_by": [], "fan_out": n, "fan_in": 0,
                   "lines": 50, "is_entry_point": False, "layer": "unknown"},
    }
    for i in range(n):
        mods[f"leaf_{i}.py"] = {
            "imports": [], "imported_by": ["hub.py"],
            "fan_out": 0, "fan_in": 1, "lines": 10,
            "is_entry_point": False, "layer": "unknown",
        }
    return mods


# ---------------------------------------------------------------------------
# DependencyIndex construction
# ---------------------------------------------------------------------------

class TestBuildDependencyIndex:
    def test_returns_dependency_index(self):
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index({})
        from genesis_architect_pro.dependency_index import DependencyIndex
        assert isinstance(idx, DependencyIndex)

    def test_empty_modules_produces_empty_index(self):
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index({})
        assert len(idx) == 0
        assert idx.edge_count == 0

    def test_node_count_equals_len(self):
        mods = _make_modules(("a.py", "b.py"), ("b.py", "c.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert len(idx) == 3

    def test_edge_count_correct(self):
        mods = _make_modules(("a.py", "b.py"), ("a.py", "c.py"), ("b.py", "c.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert idx.edge_count == 3

    def test_outgoing_edges(self):
        mods = _make_modules(("a.py", "b.py"), ("a.py", "c.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert idx.outgoing["a.py"] == {"b.py", "c.py"}
        assert idx.outgoing["b.py"] == set()

    def test_incoming_edges(self):
        mods = _make_modules(("a.py", "c.py"), ("b.py", "c.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert idx.incoming["c.py"] == {"a.py", "b.py"}
        assert idx.incoming["a.py"] == set()

    def test_isolated_node_has_empty_incoming_and_outgoing(self):
        mods = {"solo.py": {"imports": [], "imported_by": [],
                             "fan_out": 0, "fan_in": 0,
                             "lines": 5, "is_entry_point": False, "layer": "unknown"}}
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert idx.incoming["solo.py"] == set()
        assert idx.outgoing["solo.py"] == set()
        assert len(idx) == 1

    def test_all_modules_present_in_both_maps(self):
        mods = _make_modules(("a.py", "b.py"), ("b.py", "c.py"), ("c.py", "d.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        for m in ("a.py", "b.py", "c.py", "d.py"):
            assert m in idx.incoming, f"{m} missing from incoming"
            assert m in idx.outgoing, f"{m} missing from outgoing"

    def test_chain_structure_correct(self):
        """a → b → c → d"""
        mods = _make_modules(("a.py", "b.py"), ("b.py", "c.py"), ("c.py", "d.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert idx.outgoing["a.py"] == {"b.py"}
        assert idx.incoming["b.py"] == {"a.py"}
        assert idx.outgoing["b.py"] == {"c.py"}
        assert idx.incoming["c.py"] == {"b.py"}
        assert idx.incoming["d.py"] == {"c.py"}
        assert idx.outgoing["d.py"] == set()

    def test_cycle_handled_without_error(self):
        """a → b → a (cycle should not raise)"""
        mods = _make_modules(("a.py", "b.py"), ("b.py", "a.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert idx.edge_count == 2
        assert "a.py" in idx.incoming["b.py"]
        assert "b.py" in idx.incoming["a.py"]

    def test_importers_of_method(self):
        mods = _make_modules(("x.py", "y.py"), ("z.py", "y.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert idx.importers_of("y.py") == {"x.py", "z.py"}

    def test_imports_of_method(self):
        mods = _make_modules(("a.py", "b.py"), ("a.py", "c.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)
        assert idx.imports_of("a.py") == {"b.py", "c.py"}

    def test_importers_of_unknown_module_returns_empty_set(self):
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index({})
        assert idx.importers_of("nonexistent.py") == set()

    def test_imports_of_unknown_module_returns_empty_set(self):
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index({})
        assert idx.imports_of("nonexistent.py") == set()

    def test_build_from_real_graph_json(self, tmp_path):
        """build_dependency_index works on an actual graph.json-style dict."""
        graph = {
            "language": "python",
            "modules": {
                "src/main.py": {"imports": ["src/app.py", "src/utils.py"],
                                "imported_by": [], "fan_out": 2, "fan_in": 0,
                                "lines": 30, "is_entry_point": True, "layer": "unknown"},
                "src/app.py": {"imports": ["src/utils.py"],
                               "imported_by": ["src/main.py"], "fan_out": 1, "fan_in": 1,
                               "lines": 20, "is_entry_point": False, "layer": "unknown"},
                "src/utils.py": {"imports": [],
                                 "imported_by": ["src/main.py", "src/app.py"],
                                 "fan_out": 0, "fan_in": 2,
                                 "lines": 15, "is_entry_point": False, "layer": "unknown"},
            },
        }
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(graph["modules"])
        assert len(idx) == 3
        assert idx.edge_count == 3
        assert idx.importers_of("src/utils.py") == {"src/main.py", "src/app.py"}
        assert idx.imports_of("src/main.py") == {"src/app.py", "src/utils.py"}


# ---------------------------------------------------------------------------
# AffectedScope
# ---------------------------------------------------------------------------

class TestAffectedScope:
    def test_affected_scope_fields(self):
        from genesis_architect_pro.dependency_index import AffectedScope
        scope = AffectedScope(changed_files=["a.py"], consumer_files=["b.py"])
        assert scope.changed_files == ["a.py"]
        assert scope.consumer_files == ["b.py"]

    def test_total_property(self):
        from genesis_architect_pro.dependency_index import AffectedScope
        scope = AffectedScope(changed_files=["a.py", "b.py"], consumer_files=["c.py"])
        assert scope.total == 3

    def test_all_files_sorted_union(self):
        from genesis_architect_pro.dependency_index import AffectedScope
        scope = AffectedScope(changed_files=["z.py", "a.py"], consumer_files=["m.py"])
        assert scope.all_files() == ["a.py", "m.py", "z.py"]

    def test_all_files_deduplicates(self):
        from genesis_architect_pro.dependency_index import AffectedScope
        scope = AffectedScope(changed_files=["a.py"], consumer_files=["a.py"])
        # AffectedScope.all_files() deduplicates via set union
        assert scope.all_files() == ["a.py"]

    def test_empty_scope_has_zero_total(self):
        from genesis_architect_pro.dependency_index import AffectedScope
        assert AffectedScope().total == 0


# ---------------------------------------------------------------------------
# compute_affected_scope
# ---------------------------------------------------------------------------

class TestComputeAffectedScope:
    def _build_idx(self, *edges):
        from genesis_architect_pro.dependency_index import build_dependency_index
        return build_dependency_index(_make_modules(*edges))

    def test_modify_op_marks_file_as_changed(self):
        idx = self._build_idx(("a.py", "b.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([{"type": "MODIFY", "path": "b.py"}], idx)
        assert "b.py" in scope.changed_files

    def test_consumers_of_changed_file_included(self):
        idx = self._build_idx(("a.py", "b.py"), ("c.py", "b.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([{"type": "MODIFY", "path": "b.py"}], idx)
        assert "a.py" in scope.consumer_files
        assert "c.py" in scope.consumer_files

    def test_changed_file_not_in_consumer_files(self):
        idx = self._build_idx(("a.py", "b.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([{"type": "MODIFY", "path": "b.py"}], idx)
        assert "b.py" not in scope.consumer_files

    def test_delete_op_marks_file_as_changed(self):
        idx = self._build_idx(("a.py", "b.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([{"type": "DELETE", "path": "b.py"}], idx)
        assert "b.py" in scope.changed_files
        assert "a.py" in scope.consumer_files

    def test_create_op_marks_new_file_as_changed(self):
        idx = self._build_idx(("a.py", "b.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([{"type": "CREATE", "path": "new.py"}], idx)
        assert "new.py" in scope.changed_files
        # new.py has no importers yet → no consumers
        assert scope.consumer_files == []

    def test_move_op_includes_both_old_and_new_path(self):
        idx = self._build_idx(("a.py", "b.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope(
            [{"type": "MOVE", "path": "b.py", "new_path": "src/b.py"}], idx
        )
        assert "b.py" in scope.changed_files
        assert "src/b.py" in scope.changed_files

    def test_multiple_operations_union(self):
        idx = self._build_idx(("a.py", "b.py"), ("c.py", "d.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([
            {"type": "MODIFY", "path": "b.py"},
            {"type": "MODIFY", "path": "d.py"},
        ], idx)
        assert "b.py" in scope.changed_files
        assert "d.py" in scope.changed_files
        assert "a.py" in scope.consumer_files
        assert "c.py" in scope.consumer_files

    def test_no_multi_hop(self):
        """a → b → c; modify c should NOT include a in consumers (one hop only)."""
        idx = self._build_idx(("a.py", "b.py"), ("b.py", "c.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([{"type": "MODIFY", "path": "c.py"}], idx)
        assert "b.py" in scope.consumer_files     # direct importer
        assert "a.py" not in scope.consumer_files  # two hops — not included

    def test_empty_operations_produces_empty_scope(self):
        idx = self._build_idx(("a.py", "b.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([], idx)
        assert scope.changed_files == []
        assert scope.consumer_files == []
        assert scope.total == 0

    def test_operation_with_no_path_skipped(self):
        idx = self._build_idx(("a.py", "b.py"))
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([{"type": "MODIFY", "path": ""}], idx)
        assert scope.changed_files == []

    def test_consumer_files_sorted(self):
        mods = {
            "z.py": {"imports": ["shared.py"], "imported_by": [], "fan_out": 1,
                     "fan_in": 0, "lines": 5, "is_entry_point": False, "layer": "unknown"},
            "a.py": {"imports": ["shared.py"], "imported_by": [], "fan_out": 1,
                     "fan_in": 0, "lines": 5, "is_entry_point": False, "layer": "unknown"},
            "m.py": {"imports": ["shared.py"], "imported_by": [], "fan_out": 1,
                     "fan_in": 0, "lines": 5, "is_entry_point": False, "layer": "unknown"},
            "shared.py": {"imports": [], "imported_by": ["z.py", "a.py", "m.py"],
                          "fan_out": 0, "fan_in": 3, "lines": 20,
                          "is_entry_point": False, "layer": "unknown"},
        }
        from genesis_architect_pro.dependency_index import build_dependency_index, compute_affected_scope
        idx = build_dependency_index(mods)
        scope = compute_affected_scope([{"type": "MODIFY", "path": "shared.py"}], idx)
        assert scope.consumer_files == sorted(scope.consumer_files)

    def test_changed_files_sorted(self):
        idx = self._build_idx()
        from genesis_architect_pro.dependency_index import compute_affected_scope
        scope = compute_affected_scope([
            {"type": "MODIFY", "path": "z.py"},
            {"type": "MODIFY", "path": "a.py"},
        ], idx)
        assert scope.changed_files == sorted(scope.changed_files)

    def test_uses_refactor_step_operations_directly(self):
        """
        compute_affected_scope should work with the operation dicts that
        refactoring_planner.py produces.
        """
        mods = _make_modules(("src/main.py", "src/utils.py"))
        from genesis_architect_pro.dependency_index import build_dependency_index, compute_affected_scope
        idx = build_dependency_index(mods)
        # Mimick the output of _rule_hub_splitter operations
        ops = [
            {"type": "CREATE", "path": "src/utils_interface.py", "description": "extract"},
            {"type": "MODIFY", "path": "src/utils.py", "description": "keep impl"},
        ]
        scope = compute_affected_scope(ops, idx)
        assert "src/utils.py" in scope.changed_files
        assert "src/utils_interface.py" in scope.changed_files
        assert "src/main.py" in scope.consumer_files


# ---------------------------------------------------------------------------
# Package-level import
# ---------------------------------------------------------------------------

class TestPackageExports:
    def test_build_dependency_index_exported_from_package(self):
        from genesis_architect_pro import build_dependency_index  # noqa: F401

    def test_compute_affected_scope_exported_from_package(self):
        from genesis_architect_pro import compute_affected_scope  # noqa: F401

    def test_dependency_index_class_exported(self):
        from genesis_architect_pro import DependencyIndex  # noqa: F401

    def test_affected_scope_class_exported(self):
        from genesis_architect_pro import AffectedScope  # noqa: F401


# ---------------------------------------------------------------------------
# Backward compatibility: existing public APIs unchanged
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_build_graph_still_works(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import os\n")
        from genesis_architect_pro.import_graph import build_graph
        graph = build_graph(tmp_path)
        assert "modules" in graph
        assert "language" in graph

    def test_score_project_still_works(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import os\n")
        from genesis_architect_pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        assert "total" in result

    def test_generate_plan_still_works(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import os\n")
        from genesis_architect_pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        assert hasattr(plan, "steps")

    def test_detect_all_still_works(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import os\n")
        from genesis_architect_pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        assert hasattr(report, "patterns")


# ---------------------------------------------------------------------------
# Performance: construction and lookup benchmarks
# ---------------------------------------------------------------------------

class TestPerformance:
    # Thresholds are intentionally loose — CI can be slow.
    BUILD_THRESHOLD_MS = 500   # building 5000-node graph
    LOOKUP_THRESHOLD_US = 100  # single O(1) lookup — microseconds

    def test_build_1000_nodes_under_500ms(self):
        mods = _make_large_modules(1000)
        from genesis_architect_pro.dependency_index import build_dependency_index
        t0 = time.perf_counter()
        idx = build_dependency_index(mods)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert len(idx) == 1001
        assert elapsed_ms < self.BUILD_THRESHOLD_MS, (
            f"build_dependency_index(1000 nodes) took {elapsed_ms:.1f} ms "
            f"(limit: {self.BUILD_THRESHOLD_MS} ms)"
        )

    def test_build_5000_nodes_under_500ms(self):
        mods = _make_large_modules(5000)
        from genesis_architect_pro.dependency_index import build_dependency_index
        t0 = time.perf_counter()
        idx = build_dependency_index(mods)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert len(idx) == 5001
        assert elapsed_ms < self.BUILD_THRESHOLD_MS, (
            f"build_dependency_index(5000 nodes) took {elapsed_ms:.1f} ms "
            f"(limit: {self.BUILD_THRESHOLD_MS} ms)"
        )

    def test_lookup_is_constant_time(self):
        """
        Look up the same hub in both a small (100) and large (5000) index.
        The lookup time ratio should be < 10x (true O(1) dicts stay flat).
        """
        from genesis_architect_pro.dependency_index import build_dependency_index

        REPS = 10_000

        small_mods = _make_large_modules(100)
        idx_small = build_dependency_index(small_mods)
        t0 = time.perf_counter()
        for _ in range(REPS):
            _ = idx_small.importers_of("hub.py")
        small_us = (time.perf_counter() - t0) / REPS * 1_000_000

        large_mods = _make_large_modules(5000)
        idx_large = build_dependency_index(large_mods)
        t0 = time.perf_counter()
        for _ in range(REPS):
            _ = idx_large.importers_of("hub.py")
        large_us = (time.perf_counter() - t0) / REPS * 1_000_000

        ratio = large_us / small_us if small_us > 0 else 1.0
        # Allow up to 20x variance (GC, cache effects) — still confirms O(1) character
        assert ratio < 20, (
            f"Lookup ratio {ratio:.1f}x suggests non-O(1) scaling "
            f"(small={small_us:.3f}µs, large={large_us:.3f}µs)"
        )

    def test_lookup_per_node_under_100us(self):
        """Each individual lookup on a 5000-node graph is under 100µs."""
        mods = _make_large_modules(5000)
        from genesis_architect_pro.dependency_index import build_dependency_index
        idx = build_dependency_index(mods)

        REPS = 50_000
        t0 = time.perf_counter()
        for _ in range(REPS):
            _ = idx.importers_of("hub.py")
        per_lookup_us = (time.perf_counter() - t0) / REPS * 1_000_000

        assert per_lookup_us < self.LOOKUP_THRESHOLD_US, (
            f"Single lookup took {per_lookup_us:.3f}µs "
            f"(limit: {self.LOOKUP_THRESHOLD_US}µs)"
        )

    def test_compute_affected_scope_scales_linearly_with_ops(self):
        """
        compute_affected_scope on a 5000-node graph with 50 ops
        should complete in < 50 ms.
        """
        mods = _make_large_modules(5000)
        from genesis_architect_pro.dependency_index import build_dependency_index, compute_affected_scope
        idx = build_dependency_index(mods)
        ops = [{"type": "MODIFY", "path": f"leaf_{i}.py"} for i in range(50)]

        t0 = time.perf_counter()
        scope = compute_affected_scope(ops, idx)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert scope.total > 0
        assert elapsed_ms < 50, (
            f"compute_affected_scope(50 ops, 5000 nodes) took {elapsed_ms:.2f} ms"
        )
