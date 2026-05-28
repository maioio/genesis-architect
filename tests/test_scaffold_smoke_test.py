"""Tests for scripts/scaffold_smoke_test.py"""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent

from genesis_architect.core.scaffold_smoke_test import build_command, _validate_semver, SMOKE_TEMPLATES


class TestBuildCommand:
    def test_cli_entrypoint_substituted(self):
        cmd = build_command("cli", entrypoint="mytool")
        assert "mytool" in cmd
        assert "--version" in cmd

    def test_library_pkg_substituted(self):
        cmd = build_command("library", pkg="mylib")
        assert "mylib" in cmd
        assert "import" in cmd

    def test_service_port_substituted(self):
        cmd = build_command("service", port="9000")
        assert "9000" in cmd
        assert "health" in cmd

    def test_service_default_port(self):
        cmd = build_command("service")
        assert "8080" in cmd

    def test_frontend_is_npm_build(self):
        cmd = build_command("frontend")
        assert "npm run build" in cmd

    def test_all_archetypes_produce_non_empty_command(self):
        for arch in ("cli", "library", "service", "frontend"):
            cmd = build_command(arch, entrypoint="x", pkg="x", port="8080")
            assert cmd.strip(), f"Empty command for archetype: {arch}"


class TestValidateSemver:
    def test_detects_semver_in_output(self):
        assert _validate_semver("mytool 1.2.3") is True

    def test_detects_major_minor_only(self):
        assert _validate_semver("version 2.0") is True

    def test_rejects_no_semver(self):
        assert _validate_semver("error: command not found") is False

    def test_rejects_empty_string(self):
        assert _validate_semver("") is False

    def test_detects_semver_in_longer_output(self):
        assert _validate_semver("Genesis Architect CLI version 2.4.0 (c) 2026") is True


class TestSmokeTemplatesConstant:
    def test_all_four_archetypes_defined(self):
        for arch in ("cli", "library", "service", "frontend"):
            assert arch in SMOKE_TEMPLATES

    def test_templates_are_non_empty(self):
        for arch, tpl in SMOKE_TEMPLATES.items():
            assert tpl.strip(), f"Empty template for {arch}"


class TestMain:
    def test_print_only_exits_0(self):
        import unittest.mock as mock
        from genesis_architect.core.scaffold_smoke_test import main
        with mock.patch("sys.argv", ["scaffold_smoke_test.py",
                                     "--archetype", "frontend",
                                     "--print-only"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_missing_entrypoint_for_cli_exits_2(self):
        import unittest.mock as mock
        from genesis_architect.core.scaffold_smoke_test import main
        with mock.patch("sys.argv", ["scaffold_smoke_test.py",
                                     "--archetype", "cli",
                                     "--print-only"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_missing_pkg_for_library_exits_2(self):
        import unittest.mock as mock
        from genesis_architect.core.scaffold_smoke_test import main
        with mock.patch("sys.argv", ["scaffold_smoke_test.py",
                                     "--archetype", "library",
                                     "--print-only"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2
