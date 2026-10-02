"""Tests for dependency_scanner.py - the Knowledge Graph's CVE/risk data feed.

find_python_dependencies() is pure/local and tested directly. scan_dependency_
cves() calls out to OSV.dev — mocked here for a deterministic, network-free
suite; the Docker QA pass covers the real network path.
"""

from genesis_architect_pro.dependency_scanner import (
    find_python_dependencies,
    scan_dependency_cves,
    scan_do_not_touch_risks,
)


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestFindPythonDependencies:
    def test_third_party_import_detected(self, tmp_path):
        _write(tmp_path / "pyproject.toml", "[project]\nname = \"t\"\n")
        _write(tmp_path / "src" / "app" / "loader.py", "import yaml\n")
        deps = find_python_dependencies(tmp_path)
        assert deps == {"src/app/loader.py": {"pyyaml"}}

    def test_stdlib_import_excluded(self, tmp_path):
        _write(tmp_path / "pyproject.toml", "[project]\nname = \"t\"\n")
        _write(tmp_path / "src" / "app" / "util.py", "import os\nimport json\n")
        assert find_python_dependencies(tmp_path) == {}

    def test_internal_import_excluded(self, tmp_path):
        _write(tmp_path / "pyproject.toml", "[project]\nname = \"t\"\n")
        _write(tmp_path / "src" / "app" / "__init__.py", "")
        _write(tmp_path / "src" / "app" / "a.py", "from app import b\n")
        _write(tmp_path / "src" / "app" / "b.py", "")
        assert find_python_dependencies(tmp_path) == {}

    def test_import_alias_mapped_to_real_pypi_name(self, tmp_path):
        _write(tmp_path / "pyproject.toml", "[project]\nname = \"t\"\n")
        _write(tmp_path / "src" / "app" / "img.py", "from PIL import Image\n")
        deps = find_python_dependencies(tmp_path)
        assert deps == {"src/app/img.py": {"pillow"}}

    def test_non_python_project_returns_empty(self, tmp_path):
        _write(tmp_path / "package.json", "{}")
        _write(tmp_path / "src" / "index.ts", "import x from 'y'\n")
        assert find_python_dependencies(tmp_path) == {}


class TestScanDependencyCVEs:
    def test_no_dependencies_no_network_call(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "genesis_architect_pro.package_registry.query_osv",
            lambda *a, **k: calls.append(a) or None,
        )
        _write(tmp_path / "pyproject.toml", "[project]\nname = \"t\"\n")
        assert scan_dependency_cves(tmp_path) == []
        assert calls == []

    def test_vulnerable_package_reported_with_modules(self, tmp_path, monkeypatch):
        _write(tmp_path / "pyproject.toml", "[project]\nname = \"t\"\n")
        _write(tmp_path / "src" / "app" / "loader.py", "import yaml\n")

        class FakeSignal:
            vuln_ids = ["CVE-2020-14343"]

        monkeypatch.setattr(
            "genesis_architect_pro.package_registry.query_osv",
            lambda pkg, eco, version="": FakeSignal(),
        )
        cves = scan_dependency_cves(tmp_path)
        assert cves == [{
            "id": "CVE-2020-14343", "package": "pyyaml",
            "modules": ["src/app/loader.py"], "confidence": 0.9,
        }]

    def test_osv_failure_degrades_to_no_cves_not_a_crash(self, tmp_path, monkeypatch):
        _write(tmp_path / "pyproject.toml", "[project]\nname = \"t\"\n")
        _write(tmp_path / "src" / "app" / "loader.py", "import yaml\n")

        def boom(*a, **k):
            raise ConnectionError("OSV unreachable")

        monkeypatch.setattr("genesis_architect_pro.package_registry.query_osv", boom)
        assert scan_dependency_cves(tmp_path) == []

    def test_bounded_to_max_packages(self, tmp_path, monkeypatch):
        _write(tmp_path / "pyproject.toml", "[project]\nname = \"t\"\n")
        for i in range(5):
            _write(tmp_path / "src" / "app" / f"m{i}.py", f"import pkg{i}\n")

        calls = []

        class EmptySignal:
            vuln_ids: list = []

        def fake_osv(pkg, eco, version=""):
            calls.append(pkg)
            return EmptySignal()

        monkeypatch.setattr("genesis_architect_pro.package_registry.query_osv", fake_osv)
        scan_dependency_cves(tmp_path, max_packages=2)
        assert len(calls) == 2


class TestScanDoNotTouchRisks:
    def test_no_crash_on_empty_project(self, tmp_path):
        assert scan_do_not_touch_risks(tmp_path) == []

    def test_volatile_module_becomes_risk(self, tmp_path, monkeypatch):
        class FakeClassification:
            module = "src/app/hot.py"
            status = "VOLATILE"

        class FakeReport:
            classifications = [FakeClassification()]

        monkeypatch.setattr(
            "genesis_architect_pro.fragility_classifier.classify_all",
            lambda *a, **k: FakeReport(),
        )
        risks = scan_do_not_touch_risks(tmp_path)
        assert len(risks) == 1
        assert risks[0]["module"] == "src/app/hot.py"
        assert risks[0]["id"] == "do-not-touch:src/app/hot.py"

    def test_classifier_failure_degrades_to_empty(self, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr("genesis_architect_pro.fragility_classifier.classify_all", boom)
        assert scan_do_not_touch_risks(tmp_path) == []
