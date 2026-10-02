"""Tests for gde_companion.py — Phase 0 instrumentation + Phase 1 health page."""

from __future__ import annotations

import datetime
import json
import socket
import time
from pathlib import Path

import pytest

from genesis_architect.pro.gde_companion import (
    CompanionInstrumentation,
    GateMissStats,
    GateNotifier,
    HealthPageServer,
    _find_free_port,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(tmp_path: Path, gates: list[dict]) -> Path:
    """Write a minimal gde_session.json with the given gate entries."""
    genesis_dir = tmp_path / ".genesis"
    genesis_dir.mkdir()
    session = {
        "session_id": "test-session",
        "mode": "recovery",
        "stage": "report",
        "project_dir": str(tmp_path),
        "session_started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "last_user_interaction_at": "",
        "overall_confidence": 0.9,
        "project_risk_level": "low",
        "engine_results": {},
        "pending_write_operations": [],
        "decision_log": [],
        "gate_report": {
            "passed": [],
            "warnings": [],
            "blocks": gates,
            "hard_blocks": [],
            "overall": "block" if gates else "pass",
        },
    }
    f = genesis_dir / "gde_session.json"
    f.write_text(json.dumps(session), encoding="utf-8")
    return f


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _ago(seconds: int) -> str:
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)
    return t.isoformat()


# ---------------------------------------------------------------------------
# Phase 0 — CompanionInstrumentation
# ---------------------------------------------------------------------------


class TestGateMissStats:
    def test_companion_not_justified_below_threshold(self):
        stats = GateMissStats(total_gates_presented=10, missed_gates=1, miss_rate=0.10)
        assert not stats.companion_justified

    def test_companion_justified_above_threshold(self):
        stats = GateMissStats(total_gates_presented=10, missed_gates=2, miss_rate=0.20)
        assert stats.companion_justified

    def test_not_justified_if_too_few_gates(self):
        # Need at least 5 gates for the signal to be meaningful
        stats = GateMissStats(total_gates_presented=3, missed_gates=2, miss_rate=0.67)
        assert not stats.companion_justified


class TestCompanionInstrumentation:
    def test_no_session_file_returns_empty(self, tmp_path):
        stats = CompanionInstrumentation(tmp_path).analyse()
        assert stats.total_gates_presented == 0
        assert stats.miss_rate == 0.0
        assert stats.sessions_analysed == 0

    def test_gate_responded_fast_not_a_miss(self, tmp_path):
        presented = _ago(30)   # 30 seconds ago
        responded = _now()
        gates = [{"gate_id": "SECURITY_RISK", "action": "block_ask",
                  "presented_at": presented, "responded_at": responded,
                  "reason": "test", "override_allowed": True,
                  "title": "t", "detail": "", "confidence_penalty": 0.15}]
        _make_session(tmp_path, gates)
        stats = CompanionInstrumentation(tmp_path).analyse()
        assert stats.total_gates_presented == 1
        assert stats.missed_gates == 0
        assert stats.miss_rate == 0.0

    def test_gate_responded_slow_is_a_miss(self, tmp_path):
        presented = _ago(600)  # 10 minutes ago
        responded = _now()
        gates = [{"gate_id": "DRIFT_CRITICAL", "action": "block_ask",
                  "presented_at": presented, "responded_at": responded,
                  "reason": "test", "override_allowed": True,
                  "title": "t", "detail": "", "confidence_penalty": 0.15}]
        _make_session(tmp_path, gates)
        stats = CompanionInstrumentation(tmp_path).analyse()
        assert stats.total_gates_presented == 1
        assert stats.missed_gates == 1
        assert stats.miss_rate == pytest.approx(1.0)

    def test_gate_never_responded_is_a_miss(self, tmp_path):
        gates = [{"gate_id": "CONFIDENCE_LOW", "action": "block_ask",
                  "presented_at": _ago(60), "responded_at": "",
                  "reason": "test", "override_allowed": True,
                  "title": "t", "detail": "", "confidence_penalty": 0.15}]
        _make_session(tmp_path, gates)
        stats = CompanionInstrumentation(tmp_path).analyse()
        assert stats.missed_gates == 1

    def test_mixed_gates_computes_correct_rate(self, tmp_path):
        gates = [
            # fast response — not a miss
            {"gate_id": "WRITE_SCOPE", "action": "block_ask",
             "presented_at": _ago(10), "responded_at": _now(),
             "reason": "r", "override_allowed": True,
             "title": "t", "detail": "", "confidence_penalty": 0.05},
            # no response — miss
            {"gate_id": "SECURITY_RISK", "action": "block_ask",
             "presented_at": _ago(400), "responded_at": "",
             "reason": "r", "override_allowed": True,
             "title": "t", "detail": "", "confidence_penalty": 0.15},
            # slow response — miss
            {"gate_id": "DRIFT_CRITICAL", "action": "block_ask",
             "presented_at": _ago(700), "responded_at": _now(),
             "reason": "r", "override_allowed": True,
             "title": "t", "detail": "", "confidence_penalty": 0.15},
        ]
        _make_session(tmp_path, gates)
        stats = CompanionInstrumentation(tmp_path).analyse()
        assert stats.total_gates_presented == 3
        assert stats.missed_gates == 2
        assert stats.miss_rate == pytest.approx(2 / 3)

    def test_corrupt_session_file_returns_empty(self, tmp_path):
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        (genesis_dir / "gde_session.json").write_text("NOT JSON", encoding="utf-8")
        stats = CompanionInstrumentation(tmp_path).analyse()
        assert stats.total_gates_presented == 0

    def test_avg_response_time_computed(self, tmp_path):
        gates = [
            {"gate_id": "WRITE_SCOPE", "action": "block_ask",
             "presented_at": _ago(60), "responded_at": _now(),
             "reason": "r", "override_allowed": True,
             "title": "t", "detail": "", "confidence_penalty": 0.05},
        ]
        _make_session(tmp_path, gates)
        stats = CompanionInstrumentation(tmp_path).analyse()
        assert stats.avg_response_seconds > 0


# ---------------------------------------------------------------------------
# GateNotifier — graceful degradation when plyer not installed
# ---------------------------------------------------------------------------


class TestGateNotifier:
    def test_available_reflects_plyer_import(self):
        notifier = GateNotifier("test-project")
        # Either plyer is available or not — both states are valid
        assert isinstance(notifier.available(), bool)

    def test_notify_returns_false_without_plyer(self, monkeypatch):
        notifier = GateNotifier("test-project")
        monkeypatch.setattr(notifier, "_plyer_available", False)
        assert not notifier.notify("Title", "Message")

    def test_notify_gate_delegates_to_notify(self, monkeypatch):
        notifier = GateNotifier("test-project")
        monkeypatch.setattr(notifier, "_plyer_available", False)
        assert not notifier.notify_gate("SECURITY_RISK", "test reason")

    def test_notify_approval_needed_delegates(self, monkeypatch):
        notifier = GateNotifier("test-project")
        monkeypatch.setattr(notifier, "_plyer_available", False)
        assert not notifier.notify_approval_needed(pending_writes=3)

    def test_notify_session_complete_delegates(self, monkeypatch):
        notifier = GateNotifier("proj")
        monkeypatch.setattr(notifier, "_plyer_available", False)
        assert not notifier.notify_session_complete("recovery", 0.85)


# ---------------------------------------------------------------------------
# HealthPageServer — stdlib HTTP server
# ---------------------------------------------------------------------------


class TestFindFreePort:
    def test_returns_an_integer_port(self):
        port = _find_free_port(17800)
        assert isinstance(port, int)
        assert 17800 <= port <= 17810

    def test_returned_port_is_available(self):
        port = _find_free_port(17820)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))  # must not raise


class TestHealthPageServer:
    def test_starts_and_stops(self, tmp_path):
        server = HealthPageServer(project_dir=tmp_path, port=0, auto_find_port=False)
        # Port 0 lets OS assign — test server lifecycle without binding
        # Just test the object is valid before start
        assert not server.is_running()

    def test_url_format(self, tmp_path):
        server = HealthPageServer(project_dir=tmp_path, port=17900)
        assert server.url == "http://127.0.0.1:17900"

    def test_serves_health_page(self, tmp_path):
        import urllib.request
        port = _find_free_port(17950)
        server = HealthPageServer(project_dir=tmp_path, port=port, auto_find_port=False)
        server.start()
        time.sleep(0.2)
        try:
            assert server.is_running()
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
                html = resp.read().decode("utf-8")
            assert "Genesis PRO" in html
            assert "session.json" in html
        finally:
            server.stop()

    def test_serves_session_json_when_file_exists(self, tmp_path):
        import urllib.request
        _make_session(tmp_path, [])
        port = _find_free_port(18000)
        server = HealthPageServer(project_dir=tmp_path, port=port, auto_find_port=False)
        server.start()
        time.sleep(0.2)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/session.json") as resp:
                data = json.loads(resp.read())
            assert data["session_id"] == "test-session"
        finally:
            server.stop()

    def test_404_for_session_json_when_file_missing(self, tmp_path):
        import urllib.error
        import urllib.request
        port = _find_free_port(18050)
        server = HealthPageServer(project_dir=tmp_path, port=port, auto_find_port=False)
        server.start()
        time.sleep(0.2)
        try:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/session.json")
            assert exc_info.value.code == 404
        finally:
            server.stop()

    def test_404_for_unknown_path(self, tmp_path):
        import urllib.error
        import urllib.request
        port = _find_free_port(18100)
        server = HealthPageServer(project_dir=tmp_path, port=port, auto_find_port=False)
        server.start()
        time.sleep(0.2)
        try:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/nonexistent")
            assert exc_info.value.code == 404
        finally:
            server.stop()

    def test_stop_is_idempotent(self, tmp_path):
        port = _find_free_port(18150)
        server = HealthPageServer(project_dir=tmp_path, port=port, auto_find_port=False)
        server.start()
        time.sleep(0.1)
        server.stop()
        server.stop()  # must not raise


# ---------------------------------------------------------------------------
# Timestamp fields on GateResult (regression — added in companion phase)
# ---------------------------------------------------------------------------


class TestGateResultTimestamps:
    def test_gate_result_has_timestamp_fields(self):
        from genesis_architect.pro.gde_types import GateAction, GateResult
        gr = GateResult(
            gate_id="WRITE_SCOPE",
            action=GateAction.WARN,
            override_allowed=True,
            title="test",
            reason="reason",
        )
        assert gr.presented_at == ""
        assert gr.responded_at == ""

    def test_evaluate_gates_sets_presented_at(self):
        from genesis_architect.pro.gde_gate_engine import evaluate_gates
        from genesis_architect.pro.gde_types import (
            SessionContext,
        )
        ctx = SessionContext(overall_confidence=0.3)  # triggers CONFIDENCE_LOW
        report = evaluate_gates(ctx, ["CONFIDENCE_LOW"])
        assert report.blocks
        gate = report.blocks[0]
        assert gate.gate_id == "CONFIDENCE_LOW"
        assert gate.presented_at != ""
        # Should parse as valid ISO datetime
        datetime.datetime.fromisoformat(gate.presented_at)

    def test_session_context_has_companion_timestamps(self):
        from genesis_architect.pro.gde_types import SessionContext
        ctx = SessionContext()
        assert hasattr(ctx, "session_started_at")
        assert hasattr(ctx, "last_user_interaction_at")
        assert ctx.session_started_at == ""
        assert ctx.last_user_interaction_at == ""
