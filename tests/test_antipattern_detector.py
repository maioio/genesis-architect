"""Tests for the free-core antipattern_detector (4 base detectors)."""
import textwrap
from pathlib import Path


def _make_py_project(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for rel, content in files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content))
    return tmp_path


class TestFreeAntipatternBase:
    def test_base_detectors_present(self):
        import genesis_architect.core.antipattern_detector as ap
        for fn in ("_detect_god_classes", "_detect_hub_files",
                   "_detect_circular_deps", "_detect_dead_code"):
            assert hasattr(ap, fn), f"free core must ship {fn}"

    def test_advanced_detectors_not_in_free(self):
        import genesis_architect.core.antipattern_detector as ap
        for fn in ("_detect_feature_envy", "_detect_leaky_abstractions",
                   "_detect_shotgun_surgery"):
            assert not hasattr(ap, fn), f"advanced detector {fn} must be Pro-only"

    def test_detect_all_runs_and_returns_report(self, tmp_path):
        from genesis_architect.core.antipattern_detector import detect_all
        _make_py_project(tmp_path, {"a.py": "import b\n", "b.py": "x=1\n"})
        report = detect_all(tmp_path)
        assert hasattr(report, "patterns")
        types = {p.type for p in report.patterns}
        advanced = {"feature-envy", "leaky-abstraction", "shotgun-surgery"}
        assert not (types & advanced)

    def test_dead_code_detected(self, tmp_path):
        from genesis_architect.core.antipattern_detector import detect_all
        # orphan.py is imported by nobody -> dead code
        _make_py_project(tmp_path, {
            "main.py": "import used\n",
            "used.py": "x=1\n",
            "orphan.py": "y=2\n",
        })
        report = detect_all(tmp_path)
        assert any(p.type == "dead-code" for p in report.patterns)

    def test_extra_detectors_hook(self, tmp_path):
        """Pro injects advanced detectors through this hook without changing core."""
        from genesis_architect.core.antipattern_detector import detect_all, AntiPattern

        def fake_detector(modules, cycles):
            return [AntiPattern(id="x", type="feature-envy", severity="LOW",
                                file="a.py", description="injected")]

        _make_py_project(tmp_path, {"a.py": "x=1\n"})
        report = detect_all(tmp_path, extra_detectors=[fake_detector])
        assert any(p.type == "feature-envy" for p in report.patterns)
