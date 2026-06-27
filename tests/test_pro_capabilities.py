"""Tests for the 7 new PRO analysis modules:
architecture_scorer, antipattern_detector, git_analyzer,
fragility_classifier, refactoring_planner, c4_generator, security_templates.
"""
import json
import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_python_project(root: Path, *, with_tests: bool = False) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "main.py").write_text(textwrap.dedent("""\
        import os
        import sys
        from src.app import run
        from src.utils import helper
    """))
    (src / "app.py").write_text(textwrap.dedent("""\
        import os
        from src.utils import helper
    """))
    (src / "utils.py").write_text("import os\n")

    if with_tests:
        tests = root / "tests"
        tests.mkdir(exist_ok=True)
        for name in ("test_main.py", "test_app.py", "test_utils.py"):
            (tests / name).write_text("def test_placeholder(): pass\n")

    (root / "pyproject.toml").write_text("[tool.poetry]\nname='testproject'\n")


# ---------------------------------------------------------------------------
# architecture_scorer
# ---------------------------------------------------------------------------

class TestArchitectureScorer:
    def test_score_returns_required_keys(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.architecture_scorer import score_project
        result = score_project(tmp_path)

        assert "total" in result
        assert 0 <= result["total"] <= 100
        assert "modularity" in result
        assert "coupling" in result
        assert "cohesion" in result
        assert "layering" in result

    def test_score_label_mapping(self):
        from genesis_architect_pro.architecture_scorer import score_label
        assert score_label(90) == "EXCELLENT"
        assert score_label(75) == "GOOD"
        assert score_label(55) == "FAIR"
        assert score_label(35) == "POOR"
        assert score_label(10) == "CRITICAL"

    def test_all_adaptive_profiles_run(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.architecture_scorer import score_project
        profiles = [
            "default", "frontend-spa", "backend-monolith",
            "microservices", "data-pipeline", "library",
        ]
        for profile in profiles:
            result = score_project(tmp_path, profile=profile)
            assert 0 <= result["total"] <= 100, f"Profile {profile} produced out-of-range score"

    def test_score_history_appended(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.architecture_scorer import (
            score_project, append_score_history, load_score_history
        )
        result = score_project(tmp_path)
        append_score_history(tmp_path, result)
        history = load_score_history(tmp_path)

        assert len(history) == 1
        assert "total" in history[0]
        assert "timestamp" in history[0]

    def test_score_history_accumulates(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.architecture_scorer import (
            score_project, append_score_history, load_score_history
        )
        score = score_project(tmp_path)
        append_score_history(tmp_path, score)
        append_score_history(tmp_path, score)
        history = load_score_history(tmp_path)

        assert len(history) == 2


# ---------------------------------------------------------------------------
# antipattern_detector
# ---------------------------------------------------------------------------

class TestAntipatternDetector:
    def test_detect_all_returns_report(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)

        assert hasattr(report, "patterns")
        assert hasattr(report, "to_dict")
        d = report.to_dict()
        assert "patterns" in d
        # counts are flat keys: critical_count, high_count, medium_count, low_count
        assert "critical_count" in d
        assert "high_count" in d

    def test_to_dict_has_severity_counts(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.antipattern_detector import detect_all
        d = detect_all(tmp_path).to_dict()
        for key in ("critical_count", "high_count", "medium_count", "low_count"):
            assert key in d

    def test_god_class_detected_for_high_fan_out(self, tmp_path):
        """Create a project where one module's fan_out exceeds GOD_CLASS_FAN_OUT=15.
        We manipulate the import graph directly to avoid relying on import resolution.
        """
        import json
        src = tmp_path / "src"
        src.mkdir()
        for i in range(20):
            (src / f"mod_{i}.py").write_text(f"X_{i} = {i}\n")
        (src / "god_class.py").write_text("# heavy module\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")

        # Pre-build a graph with known high fan_out for god_class
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        mods = {f"src/mod_{i}.py": {"imports": [], "imported_by": ["src/god_class.py"],
                                     "fan_out": 0, "fan_in": 1, "lines": 1,
                                     "is_entry_point": False, "layer": "unknown"}
                for i in range(20)}
        mods["src/god_class.py"] = {
            "imports": [f"src/mod_{i}.py" for i in range(20)],
            "imported_by": [],
            "fan_out": 20,
            "fan_in": 0,
            "lines": 1,
            "is_entry_point": False,
            "layer": "unknown",
        }
        graph = {
            "language": "python",
            "modules": mods,
            "cycles": [],
            "dark_modules": [],
            "entry_points": [],
            "module_count": 21,
            "built_at": "2026-01-01T00:00:00+00:00",
        }
        (genesis_dir / "import_graph.json").write_text(json.dumps(graph))

        from genesis_architect_pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        types = {p["type"] for p in report.to_dict()["patterns"]}
        assert "god-class" in types

    def test_circular_dep_detected(self, tmp_path):
        """Inject a pre-built graph with a cycle so cycle detection is triggered."""
        import json
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("# a\n")
        (src / "b.py").write_text("# b\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")

        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        graph = {
            "language": "python",
            "modules": {
                "src/a.py": {"imports": ["src/b.py"], "imported_by": ["src/b.py"],
                             "fan_out": 1, "fan_in": 1, "lines": 1,
                             "is_entry_point": False, "layer": "unknown"},
                "src/b.py": {"imports": ["src/a.py"], "imported_by": ["src/a.py"],
                             "fan_out": 1, "fan_in": 1, "lines": 1,
                             "is_entry_point": False, "layer": "unknown"},
            },
            "cycles": [["src/a.py", "src/b.py", "src/a.py"]],
            "dark_modules": [],
            "entry_points": [],
            "module_count": 2,
            "built_at": "2026-01-01T00:00:00+00:00",
        }
        (genesis_dir / "import_graph.json").write_text(json.dumps(graph))

        from genesis_architect_pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        types = {p["type"] for p in report.to_dict()["patterns"]}
        assert "circular-dep" in types


# ---------------------------------------------------------------------------
# git_analyzer
# ---------------------------------------------------------------------------

class TestGitAnalyzer:
    def test_non_git_dir_returns_empty(self, tmp_path):
        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_git_repo_returns_dict(self, tmp_path):
        import subprocess
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=False)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            capture_output=True, check=False, cwd=str(tmp_path)
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            capture_output=True, check=False, cwd=str(tmp_path)
        )
        (tmp_path / "main.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], capture_output=True, check=False, cwd=str(tmp_path))
        subprocess.run(
            ["git", "commit", "-m", "init"],
            capture_output=True, check=False, cwd=str(tmp_path)
        )

        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        assert isinstance(result, dict)

    def test_churn_entry_has_expected_keys(self, tmp_path):
        import subprocess
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=False)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            capture_output=True, check=False, cwd=str(tmp_path)
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            capture_output=True, check=False, cwd=str(tmp_path)
        )
        (tmp_path / "main.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], capture_output=True, check=False, cwd=str(tmp_path))
        subprocess.run(
            ["git", "commit", "-m", "init"],
            capture_output=True, check=False, cwd=str(tmp_path)
        )

        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        if result:
            first = next(iter(result.values()))
            for key in ("commits", "fix_commits", "fix_ratio", "churn_level"):
                assert key in first, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# fragility_classifier
# ---------------------------------------------------------------------------

class TestFragilityClassifier:
    def test_classify_all_returns_report(self, tmp_path):
        _make_python_project(tmp_path, with_tests=True)
        from genesis_architect_pro.fragility_classifier import classify_all
        report = classify_all(tmp_path)

        assert hasattr(report, "classifications")
        d = report.to_dict()
        assert "classifications" in d
        assert "total_modules" in d

    def test_counts_have_three_categories(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.fragility_classifier import classify_all
        d = classify_all(tmp_path).to_dict()
        for key in ("volatile_count", "fragile_count", "stable_count"):
            assert key in d

    def test_write_fragility_map_creates_file(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.fragility_classifier import classify_all, write_fragility_map
        report = classify_all(tmp_path)

        output_path = tmp_path / "FRAGILITY_MAP.md"
        write_fragility_map(report, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "STABLE" in content or "FRAGILE" in content or "VOLATILE" in content


# ---------------------------------------------------------------------------
# refactoring_planner
# ---------------------------------------------------------------------------

class TestRefactoringPlanner:
    def test_generate_plan_returns_plan(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)

        assert hasattr(plan, "steps")
        assert hasattr(plan, "to_dict")

    def test_plan_dict_has_steps_key(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.refactoring_planner import generate_plan
        d = generate_plan(tmp_path).to_dict()
        assert "steps" in d
        assert isinstance(d["steps"], list)

    def test_plan_steps_have_required_fields(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        imports = [f"from src.mod_{i} import X_{i}" for i in range(18)]
        for i in range(18):
            (src / f"mod_{i}.py").write_text(f"X_{i} = {i}\n")
        (src / "god.py").write_text("\n".join(imports) + "\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")

        from genesis_architect_pro.refactoring_planner import generate_plan
        d = generate_plan(tmp_path).to_dict()

        for step in d["steps"]:
            for field in ("id", "title", "tier", "priority"):
                assert field in step, f"Step missing field: {field}"

    def test_write_refactoring_plan_md_creates_file(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.refactoring_planner import generate_plan, write_refactoring_plan_md
        plan = generate_plan(tmp_path)
        write_refactoring_plan_md(plan, tmp_path / "REFACTORING_PLAN.md")

        assert (tmp_path / "REFACTORING_PLAN.md").exists()


# ---------------------------------------------------------------------------
# c4_generator
# ---------------------------------------------------------------------------

class TestC4Generator:
    def test_generate_c4_doc_returns_string(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.c4_generator import generate_c4_doc
        result = generate_c4_doc(tmp_path)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_c4_doc_writes_file(self, tmp_path):
        _make_python_project(tmp_path)
        output = tmp_path / "docs" / "architecture" / "C4_ARCHITECTURE.md"
        from genesis_architect_pro.c4_generator import generate_c4_doc
        generate_c4_doc(tmp_path, output_path=output)

        assert output.exists()

    def test_c4_doc_contains_architecture_content(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.c4_generator import generate_c4_doc
        content = generate_c4_doc(tmp_path)
        assert "```mermaid" in content or "graph" in content or "C4" in content or "Container" in content


# ---------------------------------------------------------------------------
# security_templates
# ---------------------------------------------------------------------------

class TestSecurityTemplates:
    def test_generate_security_docs_creates_stride(self, tmp_path):
        _make_python_project(tmp_path)
        evidence = {
            "language": "python",
            "archetype": "api",
            "stack": {"framework": "fastapi"},
        }
        (tmp_path / ".genesis").mkdir(exist_ok=True)
        (tmp_path / ".genesis" / "evidence.json").write_text(json.dumps(evidence))

        from genesis_architect_pro.security_templates import generate_security_docs
        generate_security_docs(tmp_path)

        stride = tmp_path / "docs" / "security" / "STRIDE_ANALYSIS.md"
        assert stride.exists()
        content = stride.read_text()
        assert "STRIDE" in content or "Spoofing" in content or "Tampering" in content

    def test_generate_security_docs_creates_owasp(self, tmp_path):
        _make_python_project(tmp_path)
        evidence = {"language": "python", "archetype": "api", "stack": {}}
        (tmp_path / ".genesis").mkdir(exist_ok=True)
        (tmp_path / ".genesis" / "evidence.json").write_text(json.dumps(evidence))

        from genesis_architect_pro.security_templates import generate_security_docs
        generate_security_docs(tmp_path)

        owasp = tmp_path / "docs" / "security" / "OWASP_CHECKLIST.md"
        assert owasp.exists()
        content = owasp.read_text()
        assert "OWASP" in content or "Injection" in content or "A01" in content

    def test_generate_security_docs_works_without_evidence(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect_pro.security_templates import generate_security_docs
        generate_security_docs(tmp_path)  # must not raise

        stride = tmp_path / "docs" / "security" / "STRIDE_ANALYSIS.md"
        owasp = tmp_path / "docs" / "security" / "OWASP_CHECKLIST.md"
        assert stride.exists()
        assert owasp.exists()

    def test_cli_archetype_marks_auth_na(self, tmp_path):
        _make_python_project(tmp_path)
        evidence = {"language": "python", "archetype": "cli", "stack": {}}
        (tmp_path / ".genesis").mkdir(exist_ok=True)
        (tmp_path / ".genesis" / "evidence.json").write_text(json.dumps(evidence))

        from genesis_architect_pro.security_templates import generate_security_docs
        generate_security_docs(tmp_path)

        owasp = (tmp_path / "docs" / "security" / "OWASP_CHECKLIST.md").read_text()
        assert "N/A" in owasp or "not applicable" in owasp.lower()
