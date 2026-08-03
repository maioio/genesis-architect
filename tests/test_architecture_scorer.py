"""Tests for the free-core architecture_scorer (base / default profile)."""
import json
import textwrap
from pathlib import Path

import pytest


def _make_py_project(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for rel, content in files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content))
    return tmp_path


class TestFreeScorerBase:
    def test_only_default_profile_shipped_in_free(self):
        from genesis_architect.core.architecture_scorer import PROFILES
        assert list(PROFILES.keys()) == ["default"]

    def test_score_project_runs_with_default(self, tmp_path):
        from genesis_architect.core.architecture_scorer import score_project
        _make_py_project(tmp_path, {
            "a.py": "import b\n",
            "b.py": "x = 1\n",
        })
        result = score_project(tmp_path)
        assert 0 <= result["total"] <= 100
        assert result["profile"] == "default"
        assert set(["modularity", "coupling", "cohesion", "layering"]) <= result.keys()

    def test_score_label_bands(self):
        from genesis_architect.core.architecture_scorer import score_label
        assert score_label(90) == "EXCELLENT"
        assert score_label(70) == "GOOD"
        assert score_label(55) == "FAIR"
        assert score_label(40) == "POOR"
        assert score_label(10) == "CRITICAL"

    def test_unknown_profile_falls_back_to_default(self, tmp_path):
        from genesis_architect.core.architecture_scorer import score_project
        _make_py_project(tmp_path, {"a.py": "x = 1\n"})
        result = score_project(tmp_path, profile="microservices")  # not in free
        assert result["profile"] == "default"

    def test_profiles_arg_lets_caller_inject_profiles(self, tmp_path):
        """Pro uses this to supply adaptive profiles without changing core."""
        from genesis_architect.core.architecture_scorer import score_project
        _make_py_project(tmp_path, {"a.py": "x = 1\n"})
        custom = {
            "default": {"modularity": 0.4, "coupling": 0.25, "cohesion": 0.2, "layering": 0.15},
            "library": {"modularity": 0.4, "coupling": 0.2, "cohesion": 0.3, "layering": 0.1},
        }
        result = score_project(tmp_path, profile="library", profiles=custom)
        assert result["profile"] == "library"
