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


class TestHubFileDiscrimination:
    """The hub-file rule counts production coupling, not test coverage — and
    tells a vocabulary apart from a hub."""

    @staticmethod
    def _mod(importers, fan_out=3):
        return {
            "fan_in": len(importers),
            "fan_out": fan_out,
            "imported_by": importers,
            "lines": 100,
        }

    def _detect(self, modules):
        from genesis_architect.core.antipattern_detector import _detect_hub_files
        return _detect_hub_files(modules)

    def test_test_importers_do_not_count_as_coupling(self):
        """Adding tests must never degrade an architecture score.

        A test is a leaf: nothing depends on it, so a change cannot cascade
        *through* it. 20 test importers and 4 production ones is not a hub.
        """
        modules = {"src/thing.py": self._mod(
            [f"tests/test_{i}.py" for i in range(20)]
            + [f"src/user{i}.py" for i in range(4)]
        )}
        assert self._detect(modules) == []

    def test_production_importers_still_flag(self):
        modules = {"src/thing.py": self._mod(
            [f"src/user{i}.py" for i in range(25)]
        )}
        found = self._detect(modules)
        assert len(found) == 1
        assert found[0].severity == "CRITICAL"
        assert found[0].metrics["fan_in"] == 25

    def test_metrics_keep_the_raw_count_visible(self):
        """Excluding tests from the verdict must not hide them from the report."""
        modules = {"src/thing.py": self._mod(
            [f"src/user{i}.py" for i in range(25)] + ["tests/test_a.py"]
        )}
        m = self._detect(modules)[0].metrics
        assert m["fan_in"] == 25
        assert m["fan_in_including_tests"] == 26
        assert m["test_importers"] == 1

    def test_vocabulary_is_low_not_critical(self):
        """High fan-in, zero fan-out: a shared vocabulary cannot propagate a
        change it never receives."""
        modules = {"src/types.py": self._mod(
            [f"src/user{i}.py" for i in range(25)], fan_out=0
        )}
        found = self._detect(modules)
        assert len(found) == 1
        assert found[0].severity == "LOW"
        assert "vocabulary" in found[0].description

    def test_vocabulary_fix_does_not_advise_splitting(self):
        """Splitting a vocabulary yields two vocabularies and duplicate types."""
        modules = {"src/types.py": self._mod(
            [f"src/user{i}.py" for i in range(25)], fan_out=0
        )}
        assert "No action needed" in self._detect(modules)[0].suggested_fix

    def test_a_module_that_imports_others_is_still_a_hub(self):
        """The discriminator is fan_out, so one outgoing edge is enough."""
        modules = {"src/thing.py": self._mod(
            [f"src/user{i}.py" for i in range(25)], fan_out=1
        )}
        assert self._detect(modules)[0].severity == "CRITICAL"

    def test_falls_back_to_fan_in_when_importers_unknown(self):
        """An older graph without `imported_by` must still be evaluated."""
        modules = {"src/thing.py": {"fan_in": 25, "fan_out": 3, "lines": 100}}
        assert self._detect(modules)[0].severity == "CRITICAL"

    def test_nested_and_suffixed_test_paths_are_recognised(self):
        modules = {"src/thing.py": self._mod(
            ["pkg/tests/test_a.py", "a/test/b.py", "src/thing_test.py",
             "tests/test_c.py"] + [f"src/user{i}.py" for i in range(4)]
        )}
        assert self._detect(modules) == []
