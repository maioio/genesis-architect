"""Tests for the free-core c4_generator (Levels 1-2; Level 3 is Pro)."""
import json
from pathlib import Path


def _make_project(tmp_path: Path) -> Path:
    g = tmp_path / ".genesis"
    g.mkdir()
    (g / "evidence.json").write_text(json.dumps(
        {"archetype": "service", "language": "python"}))
    (g / "import_graph.json").write_text(json.dumps({
        "language": "python",
        "modules": {"a": {"imports": ["b"], "fan_in": 0, "fan_out": 1, "layer": "app"},
                    "b": {"imports": [], "fan_in": 1, "fan_out": 0, "layer": "core"}},
    }))
    return tmp_path


class TestFreeC4Base:
    def test_emits_context_and_container(self, tmp_path):
        from genesis_architect.core.c4_generator import generate_c4_doc
        out = generate_c4_doc(_make_project(tmp_path))
        assert "Level 1: System Context" in out
        assert "Level 2: Containers" in out

    def test_no_component_level_by_default(self, tmp_path):
        from genesis_architect.core.c4_generator import generate_c4_doc
        out = generate_c4_doc(_make_project(tmp_path))
        assert "Level 3: Components" not in out

    def test_component_function_is_pro_only(self):
        from genesis_architect.core import c4_generator as c4
        assert not hasattr(c4, "_generate_component_diagram")

    def test_component_section_injection(self, tmp_path):
        """Pro supplies Level 3 through component_section without changing core."""
        from genesis_architect.core.c4_generator import generate_c4_doc
        out = generate_c4_doc(_make_project(tmp_path),
                              component_section="```mermaid\nC4Component\n```")
        assert "Level 3: Components" in out
        assert "C4Component" in out

    def test_writes_to_output_path(self, tmp_path):
        from genesis_architect.core.c4_generator import generate_c4_doc
        out_file = tmp_path / "docs" / "C4.md"
        generate_c4_doc(_make_project(tmp_path), output_path=out_file)
        assert out_file.exists()
        assert "C4 Architecture" in out_file.read_text(encoding="utf-8")
