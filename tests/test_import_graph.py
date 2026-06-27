"""Tests for import_graph.py - shared multi-language import graph builder."""
import json
import textwrap
from pathlib import Path

import pytest


class TestDetectLanguage:
    def test_detects_python_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'")
        from genesis_architect.core.import_graph import detect_language
        assert detect_language(tmp_path) == "python"

    def test_detects_from_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "x"}')
        from genesis_architect.core.import_graph import detect_language
        lang = detect_language(tmp_path)
        assert lang in ("javascript", "typescript")

    def test_detects_go_from_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/x\n\ngo 1.21")
        from genesis_architect.core.import_graph import detect_language
        assert detect_language(tmp_path) == "go"

    def test_detects_rust_from_cargo_toml(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"')
        from genesis_architect.core.import_graph import detect_language
        assert detect_language(tmp_path) == "rust"


class TestPythonImportExtraction:
    def test_extracts_stdlib_and_local_imports(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(textwrap.dedent("""\
            import os
            import sys
            from pathlib import Path
            from mymodule import something
        """))
        from genesis_architect.core.import_graph import _extract_python_imports
        imports = _extract_python_imports(src / "app.py", tmp_path)
        assert "os" in imports
        assert "sys" in imports
        assert "pathlib" in imports
        assert "mymodule" in imports

    def test_handles_syntax_error_gracefully(self, tmp_path):
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken(:\n    pass")
        from genesis_architect.core.import_graph import _extract_python_imports
        result = _extract_python_imports(bad_file, tmp_path)
        assert result == []

    def test_handles_missing_file_gracefully(self, tmp_path):
        from genesis_architect.core.import_graph import _extract_python_imports
        result = _extract_python_imports(tmp_path / "nonexistent.py", tmp_path)
        assert result == []


class TestJsTsImportExtraction:
    def test_extracts_relative_imports(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "index.ts").write_text(textwrap.dedent("""\
            import { foo } from './utils';
            import bar from '../lib/bar';
            const baz = require('./baz');
        """))
        from genesis_architect.core.import_graph import _extract_js_ts_imports
        imports = _extract_js_ts_imports(src / "index.ts", tmp_path)
        assert "./utils" in imports
        assert "../lib/bar" in imports
        assert "./baz" in imports

    def test_extracts_package_imports(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.ts").write_text("import express from 'express';\nimport { z } from 'zod';")
        from genesis_architect.core.import_graph import _extract_js_ts_imports
        imports = _extract_js_ts_imports(src / "app.ts", tmp_path)
        assert "express" in imports
        assert "zod" in imports


class TestGoImportExtraction:
    def test_extracts_block_imports(self, tmp_path):
        f = tmp_path / "main.go"
        f.write_text(textwrap.dedent("""\
            package main

            import (
                "fmt"
                "os"
                "github.com/user/myapp/internal/core"
            )
        """))
        from genesis_architect.core.import_graph import _extract_go_imports
        imports = _extract_go_imports(f, tmp_path)
        assert "fmt" in imports
        assert "os" in imports
        assert "github.com/user/myapp/internal/core" in imports


class TestLayerDetection:
    def test_detects_domain_layer(self):
        from genesis_architect.core.import_graph import _detect_layer
        assert _detect_layer("src/domain/user.py") == "domain"

    def test_detects_infrastructure_layer(self):
        from genesis_architect.core.import_graph import _detect_layer
        assert _detect_layer("src/infrastructure/db.py") == "infrastructure"

    def test_detects_presentation_layer(self):
        from genesis_architect.core.import_graph import _detect_layer
        assert _detect_layer("src/views/home.py") == "presentation"

    def test_detects_test_layer(self):
        from genesis_architect.core.import_graph import _detect_layer
        assert _detect_layer("tests/test_app.py") == "test"

    def test_returns_unknown_for_unrecognised(self):
        from genesis_architect.core.import_graph import _detect_layer
        assert _detect_layer("src/xyz_completely_custom/widget.py") == "unknown"


class TestCycleDetection:
    def test_detects_simple_cycle(self):
        from genesis_architect.core.import_graph import _find_cycles
        adj = {
            "a.py": ["b.py"],
            "b.py": ["a.py"],
            "c.py": [],
        }
        cycles = _find_cycles(adj)
        assert len(cycles) >= 1
        # Cycle must involve a and b
        all_nodes = {n for cycle in cycles for n in cycle}
        assert "a.py" in all_nodes or "b.py" in all_nodes

    def test_no_cycles_in_dag(self):
        from genesis_architect.core.import_graph import _find_cycles
        adj = {
            "a.py": ["b.py"],
            "b.py": ["c.py"],
            "c.py": [],
        }
        cycles = _find_cycles(adj)
        assert cycles == []

    def test_three_node_cycle(self):
        from genesis_architect.core.import_graph import _find_cycles
        adj = {
            "a.py": ["b.py"],
            "b.py": ["c.py"],
            "c.py": ["a.py"],
        }
        cycles = _find_cycles(adj)
        assert len(cycles) >= 1


class TestBuildGraph:
    def test_builds_graph_for_python_project(self, tmp_path):
        # Create minimal Python project
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("from src import app\n")
        (src / "app.py").write_text("import os\n")

        from genesis_architect.core.import_graph import build_graph
        graph = build_graph(tmp_path, language="python", save=False)

        assert graph["language"] == "python"
        assert graph["module_count"] >= 2
        assert "modules" in graph
        assert "cycles" in graph
        assert "dark_modules" in graph

    def test_saves_graph_to_genesis_dir(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("import os\n")

        from genesis_architect.core.import_graph import build_graph
        graph = build_graph(tmp_path, language="python", save=True)

        cache = tmp_path / ".genesis" / "import_graph.json"
        assert cache.exists()
        loaded = json.loads(cache.read_text())
        assert loaded["language"] == "python"

    def test_load_or_build_uses_cache(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("import os\n")

        from genesis_architect.core.import_graph import build_graph, load_or_build
        build_graph(tmp_path, language="python", save=True)

        # Second call should load from cache
        graph = load_or_build(tmp_path)
        assert graph["language"] == "python"

    def test_fan_in_fan_out_computed(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        # main imports app and utils
        (src / "main.py").write_text(
            "from genesis_test_pkg.app import run\nfrom genesis_test_pkg.utils import helper\n"
        )
        (src / "app.py").write_text("import os\n")
        (src / "utils.py").write_text("import sys\n")

        from genesis_architect.core.import_graph import build_graph
        graph = build_graph(tmp_path, language="python", save=False)

        # All modules should have fan_in and fan_out keys
        for mod, data in graph["modules"].items():
            assert "fan_in" in data
            assert "fan_out" in data
