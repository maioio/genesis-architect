"""Tests for companion_ui - the self-contained Floating Assistant web app."""
from genesis_architect.pro.companion_ui import (
    DEFAULT_PORT, render_companion_html, write_companion_html,
)


class TestRender:
    def test_self_contained_html(self):
        html = render_companion_html()
        assert html.startswith("<!DOCTYPE html>")
        assert "<script>" in html and "<style>" in html
        # the only external references are the Google Fonts stylesheet lines
        external = [ln for ln in html.splitlines()
                    if "http" in ln and "fonts.g" not in ln]
        assert external == [], f"unexpected external refs: {external}"

    def test_has_bubble_panel_canvas_hooks(self):
        html = render_companion_html()
        assert 'id="bubble"' in html          # collapsed bubble
        assert 'id="panel"' in html           # expanded panel
        assert "Companion.canvas()" in html   # canvas handoff
        assert "Companion.expand()" in html   # bubble -> panel

    def test_config_injected(self):
        html = render_companion_html(ws_port=12345, ws_token="secret123", theme="dark")
        assert "12345" in html and "secret123" in html and "dark" in html
        assert "window.GENESIS_CFG" in html

    def test_default_port_matches_server(self):
        # must match streaming/server.py _PORT so the UI connects out of the box
        assert DEFAULT_PORT == 47291
        assert str(DEFAULT_PORT) in render_companion_html()

    def test_speaks_server_protocol(self):
        html = render_companion_html()
        # auth handshake + inbound/outbound message types
        assert '"type":"auth"' in html or "type:'auth'" in html
        assert "user.intent" in html and "user.approval" in html
        # renders real engine events
        assert "engine.start" in html and "engine.progress" in html
        assert "gate.approval_required" in html

    def test_wire_format_matches_router(self):
        # outbound must use {type, payload:{instruction}} and payload:{gate_name,
        # decision} — the exact contract streaming/inbound.py reads.
        html = render_companion_html()
        assert "payload:{instruction:txt}" in html
        assert "gate_name:pendingGate" in html and "decision:ok?'approve':'reject'" in html
        # inbound reads m.payload (not m.data)
        assert "m.payload" in html

    def test_has_quick_actions_and_activity_levels(self):
        html = render_companion_html()
        for a in ("recover this project", "run research", "ask the committee"):
            assert a in html
        for lvl in ("quiet", "balanced", "active", "expert"):
            assert lvl in html

    def test_honest_offline_state(self):
        html = render_companion_html()
        assert "offline" in html and "idle" in html
        # never fabricates progress: bubble starts idle, bar hidden
        assert "Genesis — idle" in html


class TestWrite:
    def test_write_creates_file(self, tmp_path):
        p = write_companion_html(tmp_path, ws_port=47291, ws_token="t")
        assert p is not None and p.exists()
        assert p.name == "companion.html"
        assert p.parent.name == "ui"
        assert p.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
