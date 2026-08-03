"""Tests for the one-command Companion auto-provision (voice/setup.py)."""
from __future__ import annotations

import sys
from unittest.mock import patch

from genesis_architect.pro.voice.setup import (
    COMPANION_PACKAGES,
    ProvisionResult,
    ensure_companion_packages,
    missing_companion_packages,
)


class TestMissingCompanionPackages:
    def test_nothing_missing_when_all_importable(self):
        with patch("genesis_architect.pro.voice.setup._pkg_available",
                   return_value=True):
            assert missing_companion_packages() == []

    def test_all_missing_when_none_importable(self):
        with patch("genesis_architect.pro.voice.setup._pkg_available",
                   return_value=False):
            missing = missing_companion_packages()
        assert sorted(missing) == sorted(COMPANION_PACKAGES.values())

    def test_webrtcvad_requirement_uses_wheels_package(self):
        """Plain webrtcvad is sdist-only and fails without a compiler —
        the provision list must use webrtcvad-wheels."""
        assert COMPANION_PACKAGES["webrtcvad"].startswith("webrtcvad-wheels")


class TestEnsureCompanionPackages:
    def test_noop_when_everything_present(self):
        with patch("genesis_architect.pro.voice.setup._pkg_available",
                   return_value=True):
            result = ensure_companion_packages()
        assert result.ok
        assert result.installed == []
        assert len(result.already_present) == len(COMPANION_PACKAGES)

    def test_installs_missing_via_pip(self):
        calls = {}

        def fake_run(cmd, **kw):
            calls["cmd"] = cmd

            class P:
                returncode = 0
                stdout = ""
                stderr = ""
            return P()

        avail = {"rich"}  # only rich present; everything else missing

        def fake_avail(mod):
            # After "pip install" runs, report everything importable.
            return mod in avail or "cmd" in calls

        with patch("genesis_architect.pro.voice.setup._pkg_available",
                   side_effect=fake_avail), \
             patch("subprocess.run", side_effect=fake_run):
            result = ensure_companion_packages()

        assert result.ok
        assert "pip" in calls["cmd"]
        if sys.version_info < (3, 13):
            # kokoro is only offered on Python <3.13 — its spacy dependency
            # has no wheels on newer versions and pip falls back to a
            # from-source build that effectively hangs.
            assert any(req.startswith("kokoro") for req in result.installed)
        assert all(not req.startswith("rich") for req in result.installed)

    def test_pip_invoked_with_utf8_decoding(self):
        """Regression: on Windows, subprocess text=True decodes pip's UTF-8
        output with cp1252 and crashes on byte 0x9d. The call MUST pass
        encoding='utf-8', errors='replace' — this broke `companion --ui`."""
        captured = {}

        def fake_run(cmd, **kw):
            captured.update(kw)

            class P:
                returncode = 0
                stdout = ""
                stderr = ""
            return P()

        with patch("genesis_architect.pro.voice.setup._pkg_available",
                   side_effect=lambda m: "cmd" in captured or m == "rich"), \
             patch("subprocess.run", side_effect=fake_run):
            ensure_companion_packages()

        assert captured.get("encoding") == "utf-8"
        assert captured.get("errors") == "replace"

    def test_pip_failure_reported_not_raised(self):
        def fake_run(cmd, **kw):
            class P:
                returncode = 1
                stdout = ""
                stderr = "ERROR: No matching distribution found"
            return P()

        with patch("genesis_architect.pro.voice.setup._pkg_available",
                   return_value=False), \
             patch("subprocess.run", side_effect=fake_run):
            result = ensure_companion_packages()
        assert not result.ok
        assert result.installed == []
        assert "No matching distribution" in result.failed[0]

    def test_exception_reported_not_raised(self):
        with patch("genesis_architect.pro.voice.setup._pkg_available",
                   return_value=False), \
             patch("subprocess.run", side_effect=OSError("pip missing")):
            result = ensure_companion_packages()
        assert not result.ok
        assert "pip missing" in result.failed[0]

    def test_progress_callback_called(self):
        messages = []

        def fake_run(cmd, **kw):
            class P:
                returncode = 0
                stdout = ""
                stderr = ""
            return P()

        installed = {"flag": False}

        def fake_avail(mod):
            return installed["flag"]

        with patch("genesis_architect.pro.voice.setup._pkg_available",
                   side_effect=lambda m: installed["flag"]), \
             patch("subprocess.run",
                   side_effect=lambda *a, **k: (installed.update(flag=True), fake_run(a))[1]):
            ensure_companion_packages(progress=messages.append)
        assert messages and "Installing" in messages[0]

    def test_result_ok_property(self):
        assert ProvisionResult().ok
        assert not ProvisionResult(failed=["x"]).ok
