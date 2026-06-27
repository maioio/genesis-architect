"""
Step 5 tests: ModelStore dual-layer architecture model.

Covers every test listed in FIRST_5_STEPS.md §Step 5, plus required edge cases:
  - missing .genesis directory
  - missing committed / planned files
  - corrupted JSON
  - empty model
  - schema version mismatch
  - save/load roundtrip (all field types)
  - deterministic serialization ordering
  - safe write (temp-then-rename)
  - planned/committed independence
  - mark_implemented merge logic
  - source_map propagation
  - is_planned_diverged structural detection
  - package-level imports
  - no production code touched
"""

import json
import os
import warnings
from pathlib import Path

import pytest

from genesis_architect_pro.model_store import (
    ModelStore,
    ArchModel,
    ModelNode,
    ModelLink,
    ModelGroup,
    ModelResponsibility,
    CURRENT_VERSION,
)


# ---------------------------------------------------------------------------
# Spec tests (from FIRST_5_STEPS.md)
# ---------------------------------------------------------------------------

class TestSpecTests:
    def test_load_committed_empty_if_missing(self, tmp_path):
        store = ModelStore(tmp_path)
        model = store.load_committed()
        assert isinstance(model, ArchModel)
        assert model.nodes == []
        assert model.links == []

    def test_load_planned_returns_committed_when_no_planned(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
        store.save_committed(committed)
        planned = store.load_planned()
        assert len(planned.nodes) == 1
        assert planned.nodes[0].id == "n1"

    def test_save_and_load_roundtrip(self, tmp_path):
        store = ModelStore(tmp_path)
        model = ArchModel(
            nodes=[ModelNode("n1", "container", "Auth", responsibilities=[
                ModelResponsibility("r1", "validates JWT tokens")
            ])],
            links=[ModelLink("l1", "n1", "n2", "calls")],
        )
        store.save_committed(model)
        loaded = store.load_committed()
        assert loaded.nodes[0].id == "n1"
        assert loaded.nodes[0].name == "Auth"
        assert loaded.nodes[0].responsibilities[0].statement == "validates JWT tokens"
        assert loaded.links[0].id == "l1"

    def test_committed_and_planned_are_independent(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
        planned = ArchModel(nodes=[
            ModelNode("n1", "container", "Auth"),
            ModelNode("n2", "container", "Billing"),
        ])
        store.save_committed(committed)
        store.save_planned(planned)
        loaded_committed = store.load_committed()
        loaded_planned = store.load_planned()
        assert len(loaded_committed.nodes) == 1
        assert len(loaded_planned.nodes) == 2

    def test_mark_implemented_folds_node_into_committed(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
        planned = ArchModel(nodes=[
            ModelNode("n1", "container", "Auth"),
            ModelNode("n2", "container", "Billing"),
        ])
        store.save_committed(committed)
        store.save_planned(planned)
        store.mark_implemented(["n2"])
        loaded = store.load_committed()
        ids = [n.id for n in loaded.nodes]
        assert "n2" in ids

    def test_mark_implemented_removes_from_planned(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel()
        planned = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
        store.save_committed(committed)
        store.save_planned(planned)
        store.mark_implemented(["n1"])
        loaded_planned = store.load_planned()
        planned_ids = [n.id for n in loaded_planned.nodes]
        assert "n1" not in planned_ids

    def test_is_planned_diverged_true_when_different(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
        planned = ArchModel(nodes=[
            ModelNode("n1", "container", "Auth"),
            ModelNode("n2", "container", "Billing"),
        ])
        store.save_committed(committed)
        store.save_planned(planned)
        assert store.is_planned_diverged() is True

    def test_is_planned_diverged_false_when_same(self, tmp_path):
        store = ModelStore(tmp_path)
        model = ArchModel(nodes=[ModelNode("n1", "container", "Auth")])
        store.save_committed(model)
        store.save_planned(model)
        assert store.is_planned_diverged() is False

    def test_genesis_dir_created_if_missing(self, tmp_path):
        store = ModelStore(tmp_path)
        model = ArchModel()
        store.save_committed(model)
        assert (tmp_path / ".genesis" / "model.json").exists()

    def test_vagrant_responsibility_roundtrip(self, tmp_path):
        store = ModelStore(tmp_path)
        model = ArchModel(nodes=[ModelNode("n1", "container", "Auth", responsibilities=[
            ModelResponsibility("r1", "handles auth", vagrant=True)
        ])])
        store.save_committed(model)
        loaded = store.load_committed()
        assert loaded.nodes[0].responsibilities[0].vagrant is True

    def test_stale_responsibility_roundtrip(self, tmp_path):
        store = ModelStore(tmp_path)
        model = ArchModel(nodes=[ModelNode("n1", "container", "Auth", responsibilities=[
            ModelResponsibility("r1", "old claim", stale=True)
        ])])
        store.save_committed(model)
        loaded = store.load_committed()
        assert loaded.nodes[0].responsibilities[0].stale is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestMissingFiles:
    def test_no_genesis_dir_load_committed_returns_empty(self, tmp_path):
        store = ModelStore(tmp_path / "nonexistent_project")
        model = store.load_committed()
        assert isinstance(model, ArchModel)
        assert model.nodes == []

    def test_no_genesis_dir_load_planned_returns_empty(self, tmp_path):
        store = ModelStore(tmp_path / "nonexistent_project")
        model = store.load_planned()
        assert isinstance(model, ArchModel)
        assert model.nodes == []

    def test_missing_committed_file_returns_empty(self, tmp_path):
        (tmp_path / ".genesis").mkdir()
        store = ModelStore(tmp_path)
        model = store.load_committed()
        assert model.nodes == []

    def test_missing_planned_file_falls_back_to_committed(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[ModelNode("n1", "system", "API")])
        store.save_committed(committed)
        # Do NOT save planned
        planned = store.load_planned()
        assert len(planned.nodes) == 1
        assert planned.nodes[0].id == "n1"

    def test_missing_both_files_returns_empty(self, tmp_path):
        store = ModelStore(tmp_path)
        assert store.load_committed().nodes == []
        assert store.load_planned().nodes == []


class TestCorruptedJSON:
    def test_corrupted_committed_returns_empty_with_warning(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("{ this is not valid JSON }")
        store = ModelStore(tmp_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = store.load_committed()
        assert model.nodes == []
        assert any("not valid JSON" in str(w.message) for w in caught)

    def test_corrupted_planned_returns_empty_with_warning(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "planned.json").write_text("not json at all !!!")
        store = ModelStore(tmp_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = store.load_planned()
        assert model.nodes == []
        assert any("not valid JSON" in str(w.message) for w in caught)

    def test_empty_committed_file_returns_empty(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("")
        store = ModelStore(tmp_path)
        model = store.load_committed()
        assert model.nodes == []

    def test_committed_wrong_root_type_returns_empty_with_warning(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text(json.dumps([1, 2, 3]))
        store = ModelStore(tmp_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = store.load_committed()
        assert model.nodes == []
        assert any("unexpected root type" in str(w.message) for w in caught)

    def test_partial_json_missing_keys_loads_with_defaults(self, tmp_path):
        """JSON with missing keys (e.g. only version) should load gracefully."""
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text(json.dumps({"version": "1"}))
        store = ModelStore(tmp_path)
        model = store.load_committed()
        assert model.nodes == []
        assert model.links == []
        assert model.groups == []


class TestSchemaVersioning:
    def test_unknown_version_emits_warning_but_loads(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        data = {
            "version": "99",
            "nodes": [{"id": "n1", "kind": "system", "name": "X"}],
            "links": [], "groups": [], "source_map": {},
        }
        (genesis / "model.json").write_text(json.dumps(data))
        store = ModelStore(tmp_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = store.load_committed()
        assert len(model.nodes) == 1
        assert any("version" in str(w.message).lower() for w in caught)

    def test_saved_model_has_current_version(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        raw = json.loads((tmp_path / ".genesis" / "model.json").read_text())
        assert raw["version"] == CURRENT_VERSION

    def test_version_preserved_on_roundtrip(self, tmp_path):
        store = ModelStore(tmp_path)
        model = ArchModel(version="1")
        store.save_committed(model)
        loaded = store.load_committed()
        assert loaded.version == "1"


class TestEmptyModel:
    def test_empty_model_saves_and_loads(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        loaded = store.load_committed()
        assert loaded.nodes == []
        assert loaded.links == []
        assert loaded.groups == []
        assert loaded.source_map == {}

    def test_empty_model_is_not_diverged(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        store.save_planned(ArchModel())
        assert store.is_planned_diverged() is False

    def test_empty_planned_falls_back_to_empty_committed(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        planned = store.load_planned()
        assert planned.nodes == []


class TestFullRoundtrip:
    def _full_model(self) -> ArchModel:
        return ArchModel(
            nodes=[
                ModelNode(
                    id="n1", kind="container", name="Auth",
                    parent_id="sys1", technology="Python/FastAPI",
                    description="Handles authentication",
                    responsibilities=[
                        ModelResponsibility("r1", "validates JWT",
                                            vagrant=False, stale=False,
                                            last_touched_at="2026-01-01T00:00:00+00:00"),
                        ModelResponsibility("r2", "issues tokens",
                                            vagrant=True, stale=False),
                    ],
                    external=False, vagrant=False,
                ),
                ModelNode(id="n2", kind="person", name="Admin User",
                          external=True),
            ],
            links=[
                ModelLink("l1", "n2", "n1", label="logs in", method="POST /auth/login"),
            ],
            groups=[
                ModelGroup("g1", "Security", member_ids=["n1"],
                           description="Auth boundary",
                           responsibilities=[
                               ModelResponsibility("gr1", "owns auth flows"),
                           ]),
            ],
            source_map={
                "r1": [{"pattern": "verify_token", "line": 42,
                        "end_line": 55, "symbol": "verify_token"}],
            },
        )

    def test_all_node_fields_roundtrip(self, tmp_path):
        model = self._full_model()
        store = ModelStore(tmp_path)
        store.save_committed(model)
        loaded = store.load_committed()

        n1 = next(n for n in loaded.nodes if n.id == "n1")
        assert n1.kind == "container"
        assert n1.name == "Auth"
        assert n1.parent_id == "sys1"
        assert n1.technology == "Python/FastAPI"
        assert n1.description == "Handles authentication"
        assert n1.external is False
        assert n1.vagrant is False

    def test_responsibility_fields_roundtrip(self, tmp_path):
        model = self._full_model()
        store = ModelStore(tmp_path)
        store.save_committed(model)
        loaded = store.load_committed()

        n1 = next(n for n in loaded.nodes if n.id == "n1")
        r1 = next(r for r in n1.responsibilities if r.id == "r1")
        assert r1.statement == "validates JWT"
        assert r1.vagrant is False
        assert r1.stale is False
        assert r1.last_touched_at == "2026-01-01T00:00:00+00:00"

        r2 = next(r for r in n1.responsibilities if r.id == "r2")
        assert r2.vagrant is True

    def test_link_fields_roundtrip(self, tmp_path):
        model = self._full_model()
        store = ModelStore(tmp_path)
        store.save_committed(model)
        loaded = store.load_committed()

        l1 = loaded.links[0]
        assert l1.id == "l1"
        assert l1.src == "n2"
        assert l1.dst == "n1"
        assert l1.label == "logs in"
        assert l1.method == "POST /auth/login"

    def test_group_fields_roundtrip(self, tmp_path):
        model = self._full_model()
        store = ModelStore(tmp_path)
        store.save_committed(model)
        loaded = store.load_committed()

        g1 = loaded.groups[0]
        assert g1.id == "g1"
        assert g1.name == "Security"
        assert g1.member_ids == ["n1"]
        assert g1.description == "Auth boundary"
        assert g1.responsibilities[0].statement == "owns auth flows"

    def test_source_map_roundtrip(self, tmp_path):
        model = self._full_model()
        store = ModelStore(tmp_path)
        store.save_committed(model)
        loaded = store.load_committed()

        assert "r1" in loaded.source_map
        anchor = loaded.source_map["r1"][0]
        assert anchor["pattern"] == "verify_token"
        assert anchor["line"] == 42
        assert anchor["symbol"] == "verify_token"

    def test_external_node_roundtrip(self, tmp_path):
        model = self._full_model()
        store = ModelStore(tmp_path)
        store.save_committed(model)
        loaded = store.load_committed()
        n2 = next(n for n in loaded.nodes if n.id == "n2")
        assert n2.external is True

    def test_none_fields_roundtrip(self, tmp_path):
        """Optional fields (parent_id, technology, description, method) survive as None."""
        model = ArchModel(nodes=[ModelNode("n1", "component", "X")])
        store = ModelStore(tmp_path)
        store.save_committed(model)
        loaded = store.load_committed()
        n = loaded.nodes[0]
        assert n.parent_id is None
        assert n.technology is None
        assert n.description is None


class TestDeterministicSerialization:
    def test_same_model_same_json_bytes(self, tmp_path):
        """Two saves of the same model must produce bitwise-identical JSON."""
        store = ModelStore(tmp_path)
        model = ArchModel(
            nodes=[ModelNode("n1", "container", "A"),
                   ModelNode("n2", "container", "B")],
            links=[ModelLink("l1", "n1", "n2")],
        )
        store.save_committed(model)
        first = (tmp_path / ".genesis" / "model.json").read_text()
        store.save_committed(model)
        second = (tmp_path / ".genesis" / "model.json").read_text()
        assert first == second

    def test_json_is_human_readable_indented(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[ModelNode("n1", "system", "X")]))
        raw = (tmp_path / ".genesis" / "model.json").read_text()
        # Should contain newlines and indentation
        assert "\n" in raw
        assert "  " in raw

    def test_json_contains_version_key(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        raw = json.loads((tmp_path / ".genesis" / "model.json").read_text())
        assert "version" in raw


class TestSafeWrite:
    def test_no_tmp_files_left_after_save(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        genesis = tmp_path / ".genesis"
        tmp_files = list(genesis.glob("model_*.tmp"))
        assert tmp_files == [], f"Temp files not cleaned up: {tmp_files}"

    def test_second_save_overwrites_first(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[ModelNode("n1", "system", "Old")]))
        store.save_committed(ArchModel(nodes=[ModelNode("n2", "system", "New")]))
        loaded = store.load_committed()
        ids = [n.id for n in loaded.nodes]
        assert "n2" in ids
        assert "n1" not in ids

    def test_planned_save_does_not_touch_committed(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[ModelNode("n1", "system", "Committed")])
        store.save_committed(committed)
        committed_mtime = (tmp_path / ".genesis" / "model.json").stat().st_mtime

        store.save_planned(ArchModel(nodes=[ModelNode("n2", "system", "Planned")]))
        committed_mtime_after = (tmp_path / ".genesis" / "model.json").stat().st_mtime
        assert committed_mtime == committed_mtime_after


class TestMarkImplemented:
    def test_new_node_added_to_committed(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "container", "Billing")
        ]))
        store.mark_implemented(["n1"])
        committed = store.load_committed()
        assert any(n.id == "n1" for n in committed.nodes)

    def test_existing_node_responsibilities_merged(self, tmp_path):
        """Responsibilities from planned are appended to existing committed node."""
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[
            ModelNode("n1", "container", "Auth", responsibilities=[
                ModelResponsibility("r1", "existing")
            ])
        ]))
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "container", "Auth", responsibilities=[
                ModelResponsibility("r1", "existing"),   # already in committed
                ModelResponsibility("r2", "new one"),    # new
            ])
        ]))
        store.mark_implemented(["n1"])
        committed = store.load_committed()
        n1 = next(n for n in committed.nodes if n.id == "n1")
        resp_ids = {r.id for r in n1.responsibilities}
        assert "r1" in resp_ids
        assert "r2" in resp_ids

    def test_duplicate_responsibility_not_doubled(self, tmp_path):
        """If r1 exists in committed, marking implemented must not duplicate it."""
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[
            ModelNode("n1", "container", "Auth", responsibilities=[
                ModelResponsibility("r1", "validates JWT")
            ])
        ]))
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "container", "Auth", responsibilities=[
                ModelResponsibility("r1", "validates JWT")
            ])
        ]))
        store.mark_implemented(["n1"])
        committed = store.load_committed()
        n1 = next(n for n in committed.nodes if n.id == "n1")
        assert len(n1.responsibilities) == 1

    def test_source_map_copied_on_mark_implemented(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        planned = ArchModel(
            nodes=[ModelNode("n1", "container", "Auth", responsibilities=[
                ModelResponsibility("r1", "issues JWT")
            ])],
            source_map={"r1": [{"pattern": "issue_token", "line": 10,
                                "end_line": 20, "symbol": "issue_token"}]},
        )
        store.save_planned(planned)
        store.mark_implemented(["n1"])
        committed = store.load_committed()
        assert "r1" in committed.source_map
        assert committed.source_map["r1"][0]["pattern"] == "issue_token"

    def test_non_implemented_node_stays_in_planned(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "container", "Billing"),
            ModelNode("n2", "container", "Shipping"),
        ]))
        store.mark_implemented(["n1"])
        planned = store.load_planned()
        planned_ids = [n.id for n in planned.nodes]
        assert "n2" in planned_ids
        assert "n1" not in planned_ids

    def test_mark_unknown_node_is_noop(self, tmp_path):
        """node_ids not present in planned must be silently skipped."""
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[ModelNode("n1", "system", "X")]))
        store.save_planned(ArchModel(nodes=[ModelNode("n1", "system", "X")]))
        store.mark_implemented(["nonexistent_id"])
        committed = store.load_committed()
        assert len(committed.nodes) == 1

    def test_mark_implemented_idempotent(self, tmp_path):
        """Calling mark_implemented twice with the same IDs is safe."""
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        store.save_planned(ArchModel(nodes=[ModelNode("n1", "container", "Auth")]))
        store.mark_implemented(["n1"])
        store.mark_implemented(["n1"])  # second call — node no longer in planned
        committed = store.load_committed()
        # n1 should appear exactly once in committed
        assert sum(1 for n in committed.nodes if n.id == "n1") == 1

    def test_mark_empty_list_is_noop(self, tmp_path):
        store = ModelStore(tmp_path)
        committed = ArchModel(nodes=[ModelNode("n1", "system", "X")])
        store.save_committed(committed)
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "system", "X"),
            ModelNode("n2", "system", "Y"),
        ]))
        store.mark_implemented([])
        c = store.load_committed()
        assert len(c.nodes) == 1  # unchanged


class TestIsPlannesDiverged:
    def test_diverged_by_extra_node(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[ModelNode("n1", "system", "A")]))
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "system", "A"),
            ModelNode("n2", "system", "B"),
        ]))
        assert store.is_planned_diverged() is True

    def test_diverged_by_extra_link(self, tmp_path):
        store = ModelStore(tmp_path)
        model = ArchModel(nodes=[ModelNode("n1", "system", "A"),
                                  ModelNode("n2", "system", "B")])
        store.save_committed(model)
        planned = ArchModel(
            nodes=list(model.nodes),
            links=[ModelLink("l1", "n1", "n2")],
        )
        store.save_planned(planned)
        assert store.is_planned_diverged() is True

    def test_diverged_by_extra_responsibility(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[
            ModelNode("n1", "system", "A", responsibilities=[
                ModelResponsibility("r1", "first")
            ])
        ]))
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "system", "A", responsibilities=[
                ModelResponsibility("r1", "first"),
                ModelResponsibility("r2", "second"),
            ])
        ]))
        assert store.is_planned_diverged() is True

    def test_diverged_by_changed_responsibility_statement(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[
            ModelNode("n1", "system", "A", responsibilities=[
                ModelResponsibility("r1", "original statement")
            ])
        ]))
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "system", "A", responsibilities=[
                ModelResponsibility("r1", "changed statement")
            ])
        ]))
        assert store.is_planned_diverged() is True

    def test_not_diverged_when_no_planned_file(self, tmp_path):
        """If planned.json is missing, load_planned returns committed → not diverged."""
        store = ModelStore(tmp_path)
        model = ArchModel(nodes=[ModelNode("n1", "system", "A")])
        store.save_committed(model)
        # No planned saved
        assert store.is_planned_diverged() is False

    def test_both_empty_not_diverged(self, tmp_path):
        store = ModelStore(tmp_path)
        assert store.is_planned_diverged() is False

    def test_same_nodes_different_descriptions_not_diverged(self, tmp_path):
        """description is not part of the structural signature."""
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[
            ModelNode("n1", "system", "A", description="old desc")
        ]))
        store.save_planned(ArchModel(nodes=[
            ModelNode("n1", "system", "A", description="new desc")
        ]))
        assert store.is_planned_diverged() is False

    def test_extra_group_causes_divergence(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel())
        store.save_planned(ArchModel(groups=[ModelGroup("g1", "Auth Layer")]))
        assert store.is_planned_diverged() is True


class TestPackageImports:
    def test_model_store_importable_from_package(self):
        from genesis_architect_pro import ModelStore  # noqa: F401

    def test_arch_model_importable_from_package(self):
        from genesis_architect_pro import ArchModel  # noqa: F401

    def test_model_node_importable_from_package(self):
        from genesis_architect_pro import ModelNode  # noqa: F401

    def test_model_link_importable_from_package(self):
        from genesis_architect_pro import ModelLink  # noqa: F401

    def test_model_group_importable_from_package(self):
        from genesis_architect_pro import ModelGroup  # noqa: F401

    def test_model_responsibility_importable_from_package(self):
        from genesis_architect_pro import ModelResponsibility  # noqa: F401


class TestNoProductionImpact:
    def test_score_project_unchanged(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import os\n")
        from genesis_architect_pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        assert "total" in result
        assert "confidence" in result

    def test_generate_plan_unchanged(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import os\n")
        from genesis_architect_pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        assert hasattr(plan, "steps")

    def test_model_store_does_not_interfere_with_genesis_dir(self, tmp_path):
        """Saving a model to .genesis/ must not corrupt other .genesis/ files."""
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        score_history = genesis / "score_history.jsonl"
        score_history.write_text('{"total": 80}\n')

        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[ModelNode("n1", "system", "X")]))

        # Score history must be intact
        assert score_history.read_text() == '{"total": 80}\n'
