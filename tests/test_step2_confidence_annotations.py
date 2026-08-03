"""
Step 2 tests: confidence annotations on AntiPattern, score_project, and RefactorStep.

All tests verify:
  - new fields present and in-range
  - basis strings are non-empty, human-readable strings
  - existing consumers / fields are unchanged (backward compatibility)
  - JSON output includes confidence fields
  - detectors without much evidence produce lower confidence
"""

import json
import textwrap
from pathlib import Path



# ---------------------------------------------------------------------------
# Helpers
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
    (src / "app.py").write_text("from src.utils import helper\n")
    (src / "utils.py").write_text("import os\n")
    if with_tests:
        tests = root / "tests"
        tests.mkdir(exist_ok=True)
        for name in ("test_main.py", "test_app.py"):
            (tests / name).write_text("def test_placeholder(): pass\n")
    (root / "pyproject.toml").write_text("[tool.poetry]\nname='testproject'\n")


def _inject_graph(root: Path, graph: dict) -> None:
    """Write a synthetic import graph straight into the cache.

    import_graph.load_or_build() now checks the injected cache against the
    real filesystem (mtime + file set) and rebuilds if they disagree — a
    real files-added-but-cache-stale bug this used to paper over (see
    import_graph.py's load_or_build/_cache_is_stale). So every module key
    the fake graph claims must exist as a real (empty is fine) file on disk,
    or the staleness check discards this synthetic graph and rebuilds from
    the (empty) tmp_path, and the fabricated god-class/cycle disappears.
    """
    for rel_path in graph.get("modules", {}):
        f = root / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            f.write_text("")

    genesis_dir = root / ".genesis"
    genesis_dir.mkdir(exist_ok=True)
    (genesis_dir / "import_graph.json").write_text(json.dumps(graph))


def _god_class_graph(root: Path, fan_out: int = 20) -> dict:
    """Pre-built graph with one god class."""
    mods = {f"src/mod_{i}.py": {
        "imports": [], "imported_by": ["src/god.py"],
        "fan_out": 0, "fan_in": 1, "lines": 1,
        "is_entry_point": False, "layer": "unknown",
    } for i in range(fan_out)}
    mods["src/god.py"] = {
        "imports": [f"src/mod_{i}.py" for i in range(fan_out)],
        "imported_by": [], "fan_out": fan_out, "fan_in": 0,
        "lines": 50, "is_entry_point": False, "layer": "unknown",
    }
    return {
        "language": "python", "modules": mods, "cycles": [],
        "dark_modules": [], "entry_points": [],
        "module_count": fan_out + 1, "built_at": "2026-01-01T00:00:00+00:00",
    }


def _cycle_graph(root: Path) -> dict:
    return {
        "language": "python",
        "modules": {
            "src/a.py": {"imports": ["src/b.py"], "imported_by": ["src/b.py"],
                         "fan_out": 1, "fan_in": 1, "lines": 10,
                         "is_entry_point": False, "layer": "unknown"},
            "src/b.py": {"imports": ["src/a.py"], "imported_by": ["src/a.py"],
                         "fan_out": 1, "fan_in": 1, "lines": 10,
                         "is_entry_point": False, "layer": "unknown"},
        },
        "cycles": [["src/a.py", "src/b.py", "src/a.py"]],
        "dark_modules": [], "entry_points": [],
        "module_count": 2, "built_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# AntiPattern.confidence / basis
# ---------------------------------------------------------------------------

class TestAntiPatternConfidence:
    def test_all_patterns_have_confidence_field(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        for p in report.patterns:
            assert hasattr(p, "confidence"), f"Missing confidence on {p.type}"
            assert 0.0 <= p.confidence <= 1.0, (
                f"confidence out of range for {p.type}: {p.confidence}"
            )

    def test_all_patterns_have_basis_field(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        for p in report.patterns:
            assert hasattr(p, "basis"), f"Missing basis on {p.type}"
            assert isinstance(p.basis, str)

    def test_god_class_confidence_is_float_in_range(self, tmp_path):
        _inject_graph(tmp_path, _god_class_graph(tmp_path, fan_out=20))
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        gods = [p for p in report.patterns if p.type == "god-class"]
        assert gods, "Expected a god-class to be detected"
        assert 0.0 <= gods[0].confidence <= 1.0

    def test_god_class_basis_mentions_fan_out(self, tmp_path):
        _inject_graph(tmp_path, _god_class_graph(tmp_path, fan_out=20))
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        gods = [p for p in report.patterns if p.type == "god-class"]
        assert gods
        assert "fan_out" in gods[0].basis

    def test_god_class_extreme_fan_out_has_higher_confidence(self, tmp_path):
        """fan_out=40 should produce higher confidence than fan_out=16."""
        _inject_graph(tmp_path, _god_class_graph(tmp_path, fan_out=40))
        from genesis_architect.pro.antipattern_detector import detect_all
        high_report = detect_all(tmp_path)
        high_conf = [p.confidence for p in high_report.patterns if p.type == "god-class"][0]

        tmp2 = tmp_path / "low"
        tmp2.mkdir()
        _inject_graph(tmp2, _god_class_graph(tmp2, fan_out=16))
        low_report = detect_all(tmp2)
        low_conf = [p.confidence for p in low_report.patterns if p.type == "god-class"][0]

        assert high_conf >= low_conf, (
            f"Higher fan_out should produce >= confidence: high={high_conf}, low={low_conf}"
        )

    def test_circular_dep_2node_confidence_is_1(self, tmp_path):
        _inject_graph(tmp_path, _cycle_graph(tmp_path))
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        cycles = [p for p in report.patterns if p.type == "circular-dep"]
        assert cycles
        assert cycles[0].confidence == 1.0

    def test_circular_dep_basis_mentions_cycle_length(self, tmp_path):
        _inject_graph(tmp_path, _cycle_graph(tmp_path))
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        cycles = [p for p in report.patterns if p.type == "circular-dep"]
        assert cycles
        assert "cycle_length" in cycles[0].basis

    def test_dead_code_confidence_below_circular_dep(self, tmp_path):
        """Dead code is less certain than a direct import cycle."""
        # Build a graph with both a cycle and dead code
        graph = {
            "language": "python",
            "modules": {
                "src/a.py": {"imports": ["src/b.py"], "imported_by": ["src/b.py"],
                             "fan_out": 1, "fan_in": 1, "lines": 5,
                             "is_entry_point": False, "layer": "unknown"},
                "src/b.py": {"imports": ["src/a.py"], "imported_by": ["src/a.py"],
                             "fan_out": 1, "fan_in": 1, "lines": 5,
                             "is_entry_point": False, "layer": "unknown"},
                "src/orphan.py": {"imports": [], "imported_by": [],
                                   "fan_out": 0, "fan_in": 0, "lines": 30,
                                   "is_entry_point": False, "layer": "unknown"},
            },
            "cycles": [["src/a.py", "src/b.py", "src/a.py"]],
            "dark_modules": [], "entry_points": [],
            "module_count": 3, "built_at": "2026-01-01T00:00:00+00:00",
        }
        _inject_graph(tmp_path, graph)
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        cycle_confs = [p.confidence for p in report.patterns if p.type == "circular-dep"]
        dead_confs = [p.confidence for p in report.patterns if p.type == "dead-code"]
        assert cycle_confs and dead_confs
        assert cycle_confs[0] > dead_confs[0], (
            "Circular dep should be more certain than dead code"
        )

    def test_existing_fields_unchanged(self, tmp_path):
        """Existing AntiPattern fields must still be present after adding confidence."""
        _inject_graph(tmp_path, _god_class_graph(tmp_path, fan_out=20))
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        for p in report.patterns:
            for field in ("id", "type", "severity", "file", "description",
                          "metrics", "affected_modules", "suggested_fix"):
                assert hasattr(p, field), f"Existing field '{field}' missing from {p.type}"

    def test_to_dict_includes_confidence(self, tmp_path):
        """AntiPattern serialised via to_dict / asdict must include confidence."""
        _inject_graph(tmp_path, _god_class_graph(tmp_path, fan_out=20))
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        d = report.to_dict()
        assert "patterns" in d
        if d["patterns"]:
            first = d["patterns"][0]
            assert "confidence" in first, "confidence missing from serialised pattern"
            assert "basis" in first, "basis missing from serialised pattern"

    def test_json_output_includes_confidence(self, tmp_path):
        """json.dumps(report.to_dict()) must round-trip confidence cleanly."""
        _inject_graph(tmp_path, _god_class_graph(tmp_path, fan_out=20))
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        raw = json.dumps(report.to_dict())
        parsed = json.loads(raw)
        if parsed["patterns"]:
            first = parsed["patterns"][0]
            assert isinstance(first["confidence"], float)
            assert isinstance(first["basis"], str)

    def test_confidence_default_is_1_for_new_antipattern(self):
        """Default constructor must produce confidence=1.0 (backward-compat default)."""
        from genesis_architect.pro.antipattern_detector import AntiPattern
        ap = AntiPattern(id="x", type="god-class", severity="HIGH", file="a.py",
                         description="test")
        assert ap.confidence == 1.0
        assert ap.basis == ""

    def test_basis_is_nonempty_for_detected_patterns(self, tmp_path):
        """Detected patterns must have a non-empty basis string."""
        _inject_graph(tmp_path, _god_class_graph(tmp_path, fan_out=20))
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        for p in report.patterns:
            if p.type in ("god-class", "hub-file", "circular-dep", "dead-code"):
                assert p.basis, f"basis is empty for detected {p.type}"


# ---------------------------------------------------------------------------
# score_project confidence
# ---------------------------------------------------------------------------

class TestScoreConfidence:
    def test_score_result_has_confidence_key(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        assert "confidence" in result

    def test_score_result_has_confidence_basis_key(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        assert "confidence_basis" in result

    def test_score_confidence_is_float_in_range(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        c = result["confidence"]
        assert isinstance(c, float)
        assert 0.0 <= c <= 1.0

    def test_score_confidence_basis_is_string(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        assert isinstance(result["confidence_basis"], str)
        assert len(result["confidence_basis"]) > 0

    def test_score_confidence_basis_mentions_modules(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        assert "module" in result["confidence_basis"].lower()

    def test_existing_score_keys_still_present(self, tmp_path):
        """No existing key must be removed or renamed by Step 2."""
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        for key in ("total", "modularity", "coupling", "cohesion", "layering",
                    "profile", "weights", "cycle_penalty", "issues",
                    "module_count", "cycle_count", "dark_module_count",
                    "language", "timestamp"):
            assert key in result, f"Existing key '{key}' missing from score result"

    def test_more_modules_higher_confidence(self, tmp_path):
        """A project with 50+ modules should have higher confidence than a 3-module one."""
        from genesis_architect.pro.architecture_scorer import _score_confidence
        small_conf, _ = _score_confidence(module_count=3, cycle_count=0, history_entries=0)
        large_conf, _ = _score_confidence(module_count=50, cycle_count=0, history_entries=0)
        assert large_conf >= small_conf

    def test_history_raises_confidence(self, tmp_path):
        from genesis_architect.pro.architecture_scorer import _score_confidence
        no_hist, _ = _score_confidence(module_count=10, cycle_count=0, history_entries=0)
        with_hist, _ = _score_confidence(module_count=10, cycle_count=0, history_entries=3)
        assert with_hist > no_hist

    def test_many_cycles_lowers_confidence(self, tmp_path):
        from genesis_architect.pro.architecture_scorer import _score_confidence
        no_cycles, _ = _score_confidence(module_count=20, cycle_count=0, history_entries=0)
        many_cycles, _ = _score_confidence(module_count=20, cycle_count=10, history_entries=0)
        assert many_cycles <= no_cycles

    def test_json_output_includes_confidence(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        raw = json.dumps(result)
        parsed = json.loads(raw)
        assert "confidence" in parsed
        assert "confidence_basis" in parsed
        assert isinstance(parsed["confidence"], float)

    def test_all_profiles_produce_confidence(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project, PROFILES
        for profile in PROFILES:
            result = score_project(tmp_path, profile=profile)
            assert "confidence" in result, f"confidence missing for profile={profile}"
            assert 0.0 <= result["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# RefactorStep.confidence / confidence_basis
# ---------------------------------------------------------------------------

class TestRefactorStepConfidence:
    def test_refactor_step_has_confidence_field(self):
        from genesis_architect.pro.refactoring_planner import RefactorStep
        step = RefactorStep(id=1, tier=1, rule="hub-splitter",
                            priority="HIGH", title="test", why="because")
        assert hasattr(step, "confidence")
        assert 0.0 <= step.confidence <= 1.0

    def test_refactor_step_has_confidence_basis_field(self):
        from genesis_architect.pro.refactoring_planner import RefactorStep
        step = RefactorStep(id=1, tier=1, rule="hub-splitter",
                            priority="HIGH", title="test", why="because")
        assert hasattr(step, "confidence_basis")
        assert isinstance(step.confidence_basis, str)

    def test_existing_step_fields_still_present(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        for step in plan.steps:
            for field in ("id", "tier", "rule", "priority", "title", "why",
                          "operations", "complexity", "score_impact"):
                assert hasattr(step, field), f"Existing field '{field}' missing from RefactorStep"

    def test_plan_steps_confidence_in_range(self, tmp_path):
        """Every step produced by generate_plan must have confidence in [0, 1]."""
        # Build project with a god class to trigger rule generation
        src = tmp_path / "src"
        src.mkdir()
        for i in range(18):
            (src / f"mod_{i}.py").write_text(f"X_{i} = {i}\n")
        imports = [f"from src.mod_{i} import X_{i}" for i in range(18)]
        (src / "god.py").write_text("\n".join(imports) + "\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")

        from genesis_architect.pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        for step in plan.steps:
            assert 0.0 <= step.confidence <= 1.0, (
                f"step {step.id} confidence out of range: {step.confidence}"
            )

    def test_critical_step_confidence_above_medium(self, tmp_path):
        """CRITICAL priority steps should have higher confidence than MEDIUM ones."""
        from genesis_architect.pro.refactoring_planner import _step_confidence
        crit_conf, _ = _step_confidence("CRITICAL")
        med_conf, _ = _step_confidence("MEDIUM")
        assert crit_conf > med_conf

    def test_step_confidence_basis_nonempty_for_generated_steps(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(18):
            (src / f"mod_{i}.py").write_text(f"X_{i} = {i}\n")
        imports = [f"from src.mod_{i} import X_{i}" for i in range(18)]
        (src / "god.py").write_text("\n".join(imports) + "\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")

        from genesis_architect.pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        for step in plan.steps:
            assert step.confidence_basis, (
                f"step {step.id} has empty confidence_basis"
            )

    def test_to_dict_includes_confidence(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(18):
            (src / f"mod_{i}.py").write_text(f"X_{i} = {i}\n")
        imports = [f"from src.mod_{i} import X_{i}" for i in range(18)]
        (src / "god.py").write_text("\n".join(imports) + "\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")

        from genesis_architect.pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        d = plan.to_dict()
        for step_d in d["steps"]:
            assert "confidence" in step_d, f"confidence missing from step dict: {step_d['id']}"
            assert "confidence_basis" in step_d

    def test_json_round_trip_confidence(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(18):
            (src / f"mod_{i}.py").write_text(f"X_{i} = {i}\n")
        imports = [f"from src.mod_{i} import X_{i}" for i in range(18)]
        (src / "god.py").write_text("\n".join(imports) + "\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")

        from genesis_architect.pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        raw = json.dumps(plan.to_dict())
        parsed = json.loads(raw)
        for step_d in parsed["steps"]:
            assert isinstance(step_d["confidence"], float)
            assert isinstance(step_d["confidence_basis"], str)

    def test_default_step_confidence_is_0_8(self):
        """Default constructor confidence must be 0.8 (the spec default)."""
        from genesis_architect.pro.refactoring_planner import RefactorStep
        step = RefactorStep(id=1, tier=1, rule="x", priority="HIGH",
                            title="t", why="w")
        assert step.confidence == 0.8
        assert step.confidence_basis == ""

    def test_step_inherits_antipattern_confidence(self, tmp_path):
        """Steps derived from high-confidence anti-patterns should reflect that."""
        from genesis_architect.pro.antipattern_detector import AntiPattern
        from genesis_architect.pro.refactoring_planner import _step_confidence
        ap = AntiPattern(id="x", type="god-class", severity="CRITICAL",
                         file="a.py", description="test",
                         confidence=0.99, basis="fan_out=40")
        conf, basis = _step_confidence("CRITICAL", ap)
        assert conf <= 0.99, "Step confidence must not exceed anti-pattern detection confidence"
        assert "0.99" in basis or "fan_out" in basis


# ---------------------------------------------------------------------------
# Backward compatibility: old consumers can ignore confidence
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_antipattern_report_to_dict_still_works(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.antipattern_detector import detect_all
        report = detect_all(tmp_path)
        d = report.to_dict()
        # Legacy consumers only read these keys — they must still be present
        assert "patterns" in d
        assert "critical_count" in d
        assert "high_count" in d
        assert "medium_count" in d
        assert "low_count" in d
        assert "module_count" in d
        assert "analysed_at" in d

    def test_score_project_old_keys_intact(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.architecture_scorer import score_project
        result = score_project(tmp_path)
        # A consumer that reads only these keys must still work
        _ = result["total"] + result["modularity"] + result["coupling"]
        assert result["profile"] in ("default", "frontend-spa", "backend-monolith",
                                     "microservices", "data-pipeline", "library")

    def test_refactoring_plan_to_dict_old_keys_intact(self, tmp_path):
        _make_python_project(tmp_path)
        from genesis_architect.pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        d = plan.to_dict()
        assert "steps" in d
        assert "tier1_count" in d
        assert "tier2_count" in d
        assert "total_score_impact" in d
        assert "generated_at" in d

    def test_step_to_dict_old_keys_intact(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(18):
            (src / f"mod_{i}.py").write_text(f"X_{i} = {i}\n")
        (src / "god.py").write_text(
            "\n".join(f"from src.mod_{i} import X_{i}" for i in range(18)) + "\n"
        )
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='x'\n")
        from genesis_architect.pro.refactoring_planner import generate_plan
        plan = generate_plan(tmp_path)
        d = plan.to_dict()
        for step_d in d["steps"]:
            for key in ("id", "title", "tier", "priority", "rule", "why",
                        "operations", "complexity", "score_impact"):
                assert key in step_d, f"Old key '{key}' missing from step dict"
