"""Tests for the `genesis companion --ui` launcher (F2)."""

from genesis_architect.pro.gde_cli import cmd_companion_ui


class _FakeStream:
    """Minimal stand-in for sys.stdin/sys.stdout with a controllable isatty."""

    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class _ClosedStream:
    def isatty(self) -> bool:
        raise ValueError("I/O operation on closed file")


def _force_tty(monkeypatch, *, stdin: bool = True, stdout: bool = True) -> None:
    monkeypatch.setattr("sys.stdin", _FakeStream(stdin))
    monkeypatch.setattr("sys.stdout", _FakeStream(stdout))


class TestStdioIsInteractive:
    """Both streams must be real terminals before we provision anything."""

    def test_both_ttys_is_interactive(self, monkeypatch):
        from genesis_architect.pro.gde_cli import _stdio_is_interactive
        _force_tty(monkeypatch)
        assert _stdio_is_interactive() is True

    def test_piped_stdout_is_not_interactive(self, monkeypatch):
        from genesis_architect.pro.gde_cli import _stdio_is_interactive
        _force_tty(monkeypatch, stdout=False)
        assert _stdio_is_interactive() is False

    def test_redirected_stdin_is_not_interactive(self, monkeypatch):
        from genesis_architect.pro.gde_cli import _stdio_is_interactive
        _force_tty(monkeypatch, stdin=False)
        assert _stdio_is_interactive() is False

    def test_none_stream_is_not_interactive(self, monkeypatch):
        """pythonw on Windows leaves sys.stdout as None - must not raise."""
        from genesis_architect.pro.gde_cli import _stdio_is_interactive
        monkeypatch.setattr("sys.stdin", _FakeStream(True))
        monkeypatch.setattr("sys.stdout", None)
        assert _stdio_is_interactive() is False

    def test_closed_stream_is_not_interactive(self, monkeypatch):
        from genesis_architect.pro.gde_cli import _stdio_is_interactive
        monkeypatch.setattr("sys.stdin", _ClosedStream())
        monkeypatch.setattr("sys.stdout", _FakeStream(True))
        assert _stdio_is_interactive() is False


class TestLauncher:
    def test_offline_writes_ui_and_returns(self, tmp_path, monkeypatch):
        # Force the backend import to fail -> offline path (writes UI, returns 0,
        # never blocks). We monkeypatch the streaming server import to raise.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name.endswith("streaming.server") or name == "genesis_architect.pro.streaming.server":
                raise ImportError("websockets not installed (simulated)")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        rc = cmd_companion_ui(tmp_path, no_browser=True)
        assert rc == 0
        ui = tmp_path / ".genesis" / "ui" / "companion.html"
        assert ui.exists()
        assert ui.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")

    def test_offline_ui_has_offline_state(self, tmp_path, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if "streaming.server" in name:
                raise ImportError("simulated")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        cmd_companion_ui(tmp_path, no_browser=True)
        html = (tmp_path / ".genesis" / "ui" / "companion.html").read_text(encoding="utf-8")
        assert "offline" in html  # honest offline state, no fake progress


class TestNoAutoInstallDuringTests:
    """`genesis companion --ui` provisions packages by shelling out to pip.

    That must never fire implicitly - a test run (or CI job) that silently
    pip-installs into its own environment is non-reproducible and was the
    cause of real cross-test pollution: it installed `websockets` mid-suite,
    which flipped the streaming tests from skipped to failing.
    """

    def test_auto_install_is_disabled_under_pytest(self):
        from genesis_architect.pro.gde_cli import _auto_install_disabled
        assert _auto_install_disabled() is True

    def test_env_var_opts_out(self, monkeypatch):
        from genesis_architect.pro.gde_cli import (
            NO_AUTO_INSTALL_ENV,
            _auto_install_disabled,
        )
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv(NO_AUTO_INSTALL_ENV, raising=False)
        # A terminal has to be faked now: pytest captures stdout, so without
        # this the TTY check alone would disable provisioning and the env var
        # under test would prove nothing.
        _force_tty(monkeypatch)
        assert _auto_install_disabled() is False
        monkeypatch.setenv(NO_AUTO_INSTALL_ENV, "1")
        assert _auto_install_disabled() is True

    def test_no_terminal_disables_it(self, monkeypatch):
        """The reason this exists: a headless run must not provision.

        With no TTY there is nobody to watch a 1-2 GB download or interrupt a
        pip call that can sit for 30 minutes, so the launcher just appears to
        hang - in CI, in Docker, under a service manager, or piped to a file.
        """
        from genesis_architect.pro.gde_cli import (
            NO_AUTO_INSTALL_ENV,
            _auto_install_disabled,
        )
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv(NO_AUTO_INSTALL_ENV, raising=False)
        _force_tty(monkeypatch, stdout=False)
        assert _auto_install_disabled() is True

    def test_blank_env_var_is_not_an_opt_out(self, monkeypatch):
        """Only a non-empty value counts, so `GENESIS_NO_AUTO_INSTALL=` is inert."""
        from genesis_architect.pro.gde_cli import (
            NO_AUTO_INSTALL_ENV,
            _auto_install_disabled,
        )
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        _force_tty(monkeypatch)
        monkeypatch.setenv(NO_AUTO_INSTALL_ENV, "   ")
        assert _auto_install_disabled() is False

    def test_auto_setup_voice_is_a_noop_when_disabled(self, monkeypatch):
        """The guard must return before importing the provisioning module."""
        import builtins

        from genesis_architect.pro import gde_cli

        real_import = builtins.__import__

        def exploding_import(name, *a, **k):
            if "voice.setup" in name:
                raise AssertionError(
                    "auto-provisioning ran during tests - it shells out to pip"
                )
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", exploding_import)
        gde_cli._auto_setup_voice()  # must not raise

    def test_launcher_never_shells_out_to_pip(self, tmp_path, monkeypatch):
        """End-to-end guard on the real launcher entry point.

        Forces the offline path (as the tests above do) so the call returns
        instead of blocking on a live server, then asserts nothing spawned a
        subprocess along the way.
        """
        import builtins
        import subprocess

        from genesis_architect.pro.gde_cli import cmd_companion_ui

        real_import = builtins.__import__

        def offline_import(name, *a, **k):
            if "streaming.server" in name:
                raise ImportError("simulated: force the offline path")
            return real_import(name, *a, **k)

        def forbidden(*a, **k):
            raise AssertionError(f"test run shelled out to a subprocess: {a!r}")

        monkeypatch.setattr(subprocess, "run", forbidden)
        monkeypatch.setattr(builtins, "__import__", offline_import)
        assert cmd_companion_ui(tmp_path, no_browser=True) == 0
