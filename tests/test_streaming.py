"""Tests for the Genesis Companion streaming layer.

Unit tests: events, emitter, runner_patch.
Integration: full mock GDE run with hooks installed → events collected.
"""

from __future__ import annotations

import asyncio
import json
import threading
from unittest.mock import patch

import pytest

from genesis_architect_pro.streaming.events import (
    MessageType,
    StreamEmitter,
    StreamMessage,
    committee_synthesis,
    engine_done,
    engine_failed,
    engine_start,
    gate_fired,
    session_confidence,
    session_done,
)
from genesis_architect_pro.streaming.runner_patch import (
    install,
    is_installed,
    uninstall,
    _build_summary,
)


# ---------------------------------------------------------------------------
# Auth handshake — the client waits for a schema-valid auth.ok before it
# considers itself connected. If the server stays silent (or replies with a
# bare {type} that fails schema validation) the UI holds a live socket but
# shows "connecting" forever. This guards that contract.
# ---------------------------------------------------------------------------

def test_auth_ok_is_a_full_envelope():
    from genesis_architect_pro.streaming.server import _control_envelope
    env = json.loads(_control_envelope("auth.ok"))
    assert env["type"] == "auth.ok"
    assert isinstance(env.get("id"), str) and env["id"]
    assert isinstance(env.get("ts"), (int, float))
    assert env.get("payload") == {}


def test_valid_token_gets_auth_ok():
    pytest.importorskip("websockets")
    from genesis_architect_pro.streaming.server import CompanionServer

    async def _run():
        srv = CompanionServer(port=47298)
        srv.start_in_background()
        await asyncio.sleep(0.5)
        import websockets
        try:
            async with websockets.connect("ws://127.0.0.1:47298") as ws:
                await ws.send(json.dumps({"type": "auth", "token": srv.token}))
                reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
        finally:
            srv.stop()
        return reply

    reply = asyncio.run(_run())
    assert reply["type"] == "auth.ok"
    assert reply["id"] and reply["ts"]


def test_idle_connection_stays_open():
    """Regression: _drain_outbound must not poke a version-specific 'closed'
    attribute. Newer websockets renamed it; touching it raised AttributeError
    ~1s after connect and dropped the socket — the green/yellow flapping."""
    pytest.importorskip("websockets")
    from genesis_architect_pro.streaming.server import CompanionServer

    async def _run():
        srv = CompanionServer(port=47294)
        srv.start_in_background()
        await asyncio.sleep(0.5)
        import websockets
        still_open = False
        try:
            async with websockets.connect(
                "ws://127.0.0.1:47294", ping_interval=None
            ) as ws:
                await ws.send(json.dumps({"type": "auth", "token": srv.token}))
                await asyncio.wait_for(ws.recv(), timeout=3)  # auth.ok
                # idle well past the old ~1s failure point
                try:
                    await asyncio.wait_for(ws.recv(), timeout=4)
                except asyncio.TimeoutError:
                    pass
                # socket must still be usable
                await ws.send(json.dumps({"type": "noop", "payload": {}}))
                still_open = True
        finally:
            srv.stop()
        return still_open

    assert asyncio.run(_run()) is True


def test_bad_token_gets_auth_fail_then_close():
    pytest.importorskip("websockets")
    from genesis_architect_pro.streaming.server import CompanionServer

    async def _run():
        srv = CompanionServer(port=47297)
        srv.start_in_background()
        await asyncio.sleep(0.5)
        import websockets
        got = None
        try:
            async with websockets.connect("ws://127.0.0.1:47297") as ws:
                await ws.send(json.dumps({"type": "auth", "token": "wrong"}))
                got = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
        except Exception:
            pass
        finally:
            srv.stop()
        return got

    reply = asyncio.run(_run())
    assert reply is not None and reply["type"] == "auth.fail"


# ---------------------------------------------------------------------------
# Unit: StreamMessage
# ---------------------------------------------------------------------------

def test_stream_message_to_json_round_trip():
    msg = engine_start("import_graph", phase=1, total_phases=3, session_id="sess_1")
    raw = msg.to_json()
    parsed = StreamMessage.from_json(raw)
    assert parsed.type == MessageType.ENGINE_START
    assert parsed.payload["engine"] == "import_graph"
    assert parsed.payload["phase"] == 1
    assert parsed.session_id == "sess_1"


def test_stream_message_has_id_and_ts():
    msg = engine_done("scorer", confidence=0.85)
    data = json.loads(msg.to_json())
    assert "id" in data
    assert len(data["id"]) > 0
    assert data["ts"] > 0


def test_engine_failed_payload():
    msg = engine_failed("import_graph", error="timeout", confidence_penalty=0.1, session_id="s")
    data = json.loads(msg.to_json())
    assert data["type"] == "engine.failed"
    assert data["payload"]["error"] == "timeout"
    assert data["payload"]["confidence_penalty"] == pytest.approx(0.1)


def test_gate_fired_payload():
    msg = gate_fired("CONFIDENCE_LOW", gate_type="soft_block", overridable=True, session_id="s")
    data = json.loads(msg.to_json())
    assert data["type"] == "gate.fired"
    assert data["payload"]["overridable"] is True


def test_session_confidence_payload():
    msg = session_confidence(0.73, "medium", session_id="s")
    data = json.loads(msg.to_json())
    assert data["payload"]["confidence"] == pytest.approx(0.73)
    assert data["payload"]["risk_level"] == "medium"


def test_committee_synthesis_with_minority():
    msg = committee_synthesis("refactor", "split", "Contrarian disagrees", session_id="s")
    data = json.loads(msg.to_json())
    assert data["payload"]["minority_view"] == "Contrarian disagrees"


def test_session_done_payload():
    msg = session_done("sess_1", 0.82, "low", "recovery")
    data = json.loads(msg.to_json())
    assert data["type"] == "session.done"
    assert data["payload"]["mode"] == "recovery"


def test_unknown_type_raises():
    with pytest.raises(Exception):
        StreamMessage.from_json(json.dumps({"type": "not.a.type", "payload": {}}))


# ---------------------------------------------------------------------------
# Unit: StreamEmitter
# ---------------------------------------------------------------------------

def test_emitter_no_loop_is_silent():
    emitter = StreamEmitter()
    msg = engine_start("x", 1, 1)
    # No loop attached → must not raise
    emitter.emit(msg)


def test_emitter_attach_creates_queue():
    emitter = StreamEmitter()

    async def _run():
        loop = asyncio.get_running_loop()
        emitter.attach(loop)
        assert emitter.queue is not None
        msg = engine_start("test_engine", 1, 2, session_id="s")
        emitter.emit(msg)
        await asyncio.sleep(0.01)
        received = await asyncio.wait_for(emitter.queue.get(), timeout=1.0)
        assert received.type == MessageType.ENGINE_START
        assert received.payload["engine"] == "test_engine"
        emitter.detach()

    asyncio.run(_run())


def test_emitter_detach_silences_emit():
    emitter = StreamEmitter()

    async def _run():
        loop = asyncio.get_running_loop()
        emitter.attach(loop)
        emitter.detach()
        # After detach — must not raise
        emitter.emit(engine_start("x", 1, 1))

    asyncio.run(_run())


def test_emitter_thread_safe():
    """Emit from multiple threads simultaneously — no crash, no deadlock."""
    emitter = StreamEmitter()
    collected: list[StreamMessage] = []

    async def _run():
        loop = asyncio.get_running_loop()
        emitter.attach(loop)

        def _emit_many():
            for i in range(20):
                emitter.emit(engine_start(f"eng_{i}", i, 20))

        threads = [threading.Thread(target=_emit_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        await asyncio.sleep(0.05)
        queue = emitter.queue
        while not queue.empty():
            collected.append(queue.get_nowait())
        emitter.detach()

    asyncio.run(_run())
    assert len(collected) == 100  # 5 threads × 20 messages


# ---------------------------------------------------------------------------
# Unit: runner_patch
# ---------------------------------------------------------------------------

def test_install_is_idempotent():
    install()
    install()  # second call must not raise or double-patch
    assert is_installed()
    uninstall()
    assert not is_installed()


def test_uninstall_when_not_installed():
    uninstall()  # must not raise
    assert not is_installed()


def test_build_summary_scorer():
    output = {"score": 72, "score_label": "GOOD"}
    assert "72" in _build_summary("architecture_scorer", output)
    assert "GOOD" in _build_summary("architecture_scorer", output)


def test_build_summary_antipattern():
    output = {"critical_count": 2, "high_count": 5}
    summary = _build_summary("antipattern_detector", output)
    assert "2" in summary and "5" in summary


def test_build_summary_fragility():
    output = {"volatile_count": 1, "fragile_count": 3, "stable_count": 10}
    summary = _build_summary("fragility_classifier", output)
    assert "VOLATILE:1" in summary


def test_build_summary_import_graph():
    output = {"graph": {"a": [], "b": []}, "cycles": [["a", "b"]]}
    summary = _build_summary("import_graph", output)
    assert "2 modules" in summary
    assert "1 cycles" in summary


def test_build_summary_unknown_engine():
    assert _build_summary("unknown_engine", {"foo": "bar"}) == ""


# ---------------------------------------------------------------------------
# Integration: install hooks → run GDE → collect events
# ---------------------------------------------------------------------------

def test_integration_hooks_capture_engine_events():
    """Install hooks, run a minimal GDE session, verify events are emitted."""
    from pathlib import Path
    from genesis_architect_pro.streaming.events import StreamEmitter
    from genesis_architect_pro.streaming import runner_patch
    import genesis_architect_pro.gde_runner as runner_module

    emitter = StreamEmitter()
    captured: list[StreamMessage] = []

    async def _run():
        loop = asyncio.get_running_loop()
        emitter.attach(loop)

        # Patch the default emitter temporarily
        original = runner_patch.default_emitter
        import genesis_architect_pro.streaming.runner_patch as rp_mod
        import genesis_architect_pro.streaming.events as ev_mod
        rp_mod.default_emitter = emitter
        ev_mod.default_emitter = emitter

        install()

        # Build minimal SessionContext and fake engine descriptor
        from genesis_architect_pro.gde_types import (
            SessionContext, GDEMode, EngineDescriptor, EngineCategory
        )
        ctx = SessionContext(session_id="test_sess", mode=GDEMode.RECOVERY, project_dir=Path("."))

        desc = EngineDescriptor(
            id="fake_engine",
            name="Fake Engine",
            module="genesis_architect_pro.streaming.events",  # any importable module
            entry_point="default_emitter",  # will fail — we mock _invoke
            category=EngineCategory.ANALYSIS,
            input_keys=[],
            output_keys=[],
        )

        # Patch _invoke to return a valid output without real engine
        with patch.object(runner_module, "_invoke", return_value={"_confidence": 0.9, "_warnings": []}):
            runner_module._run_single(desc, ctx)

        await asyncio.sleep(0.05)
        queue = emitter.queue
        while not queue.empty():
            captured.append(queue.get_nowait())

        uninstall()
        rp_mod.default_emitter = original
        ev_mod.default_emitter = original
        emitter.detach()

    asyncio.run(_run())

    types = {m.type for m in captured}
    assert MessageType.ENGINE_START in types
    assert MessageType.ENGINE_DONE in types
    assert MessageType.SESSION_CONFIDENCE in types


def test_integration_hooks_capture_failure_event():
    """Engine that raises → ENGINE_FAILED event emitted."""
    from pathlib import Path
    from genesis_architect_pro.streaming.events import StreamEmitter
    import genesis_architect_pro.gde_runner as runner_module

    emitter = StreamEmitter()
    captured: list[StreamMessage] = []

    async def _run():
        loop = asyncio.get_running_loop()
        emitter.attach(loop)

        import genesis_architect_pro.streaming.runner_patch as rp_mod
        import genesis_architect_pro.streaming.events as ev_mod
        original = rp_mod.default_emitter
        rp_mod.default_emitter = emitter
        ev_mod.default_emitter = emitter

        install()

        from genesis_architect_pro.gde_types import (
            SessionContext, GDEMode, EngineDescriptor, EngineCategory
        )
        ctx = SessionContext(session_id="fail_sess", mode=GDEMode.RECOVERY, project_dir=Path("."))
        desc = EngineDescriptor(
            id="failing_engine",
            name="Failing Engine",
            module="genesis_architect_pro.streaming.events",
            entry_point="default_emitter",
            category=EngineCategory.ANALYSIS,
            input_keys=[],
            output_keys=[],
            is_optional=True,
        )

        with patch.object(runner_module, "_invoke", side_effect=RuntimeError("boom")):
            runner_module._run_single(desc, ctx)

        await asyncio.sleep(0.05)
        queue = emitter.queue
        while not queue.empty():
            captured.append(queue.get_nowait())

        uninstall()
        rp_mod.default_emitter = original
        ev_mod.default_emitter = original
        emitter.detach()

    asyncio.run(_run())

    types = {m.type for m in captured}
    assert MessageType.ENGINE_FAILED in types
    failed = next(m for m in captured if m.type == MessageType.ENGINE_FAILED)
    assert "boom" in failed.payload["error"]
