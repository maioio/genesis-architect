"""Tests for the `genesis companion --ui` launcher (F2)."""

from genesis_architect_pro.gde_cli import cmd_companion_ui


class TestLauncher:
    def test_offline_writes_ui_and_returns(self, tmp_path, monkeypatch):
        # Force the backend import to fail -> offline path (writes UI, returns 0,
        # never blocks). We monkeypatch the streaming server import to raise.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name.endswith("streaming.server") or name == "genesis_architect_pro.streaming.server":
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
