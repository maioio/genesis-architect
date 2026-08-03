"""Tests for InboundRouter (streaming/inbound.py).

All external dependencies (GDE runner, STTPipeline, StreamEmitter) are mocked.
The router must never raise and must emit appropriate events.
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from genesis_architect.pro.streaming.events import (
    MessageType,
    StreamEmitter,
    StreamMessage,
)
from genesis_architect.pro.streaming.inbound import InboundRouter, _PendingGate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_msg(msg_type: MessageType, payload: dict, session_id: str = "") -> StreamMessage:
    return StreamMessage(type=msg_type, payload=payload, session_id=session_id)


class _CapturingEmitter(StreamEmitter):
    """StreamEmitter that records emitted messages for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.emitted: list[StreamMessage] = []
        self._lock = threading.Lock()

    def emit(self, message: StreamMessage) -> None:
        with self._lock:
            self.emitted.append(message)

    def types(self) -> list[str]:
        with self._lock:
            return [m.type.value for m in self.emitted]

    def wait_for(self, msg_type: MessageType, timeout: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if any(m.type == msg_type for m in self.emitted):
                    return True
            time.sleep(0.05)
        return False


def _make_router(tmp_path: Path) -> tuple[InboundRouter, _CapturingEmitter]:
    emitter = _CapturingEmitter()
    router = InboundRouter(project_dir=tmp_path, emitter=emitter)
    return router, emitter


# ---------------------------------------------------------------------------
# Tests: user.intent
# ---------------------------------------------------------------------------

class TestUserIntent:
    def test_intent_runs_gde_and_emits_session_done(self, tmp_path):
        """A valid user.intent message must trigger a GDE run and emit session.done."""
        router, emitter = _make_router(tmp_path)

        mock_report = MagicMock()
        mock_report.session_id = str(uuid.uuid4())
        mock_report.overall_confidence = 0.85
        mock_report.project_risk_level = "LOW"
        mock_report.mode.value = "refactor"

        mock_gde = MagicMock()
        mock_gde.run.return_value = mock_report

        with patch("genesis_architect.pro.gde_engine_registration", create=True), \
             patch("genesis_architect.pro.GenesisDecisionEngine", return_value=mock_gde):
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "refactor imports"})
            router.handle(msg)
            found = emitter.wait_for(MessageType.SESSION_DONE, timeout=3.0)

        assert found, f"session.done not emitted. Got: {emitter.types()}"
        done_msgs = [m for m in emitter.emitted if m.type == MessageType.SESSION_DONE]
        assert done_msgs[0].payload["confidence"] == pytest.approx(0.85, abs=1e-3)

    def test_intent_empty_instruction_does_not_crash(self, tmp_path):
        """An empty instruction is silently dropped, no crash, no GDE run."""
        router, emitter = _make_router(tmp_path)
        msg = _make_msg(MessageType.USER_INTENT, {"instruction": ""})
        router.handle(msg)
        # give background thread time to run if any
        time.sleep(0.1)
        assert MessageType.SESSION_DONE not in [m.type for m in emitter.emitted]

    def test_intent_gde_error_emits_error_event(self, tmp_path):
        """A GDE crash must emit an error event, not propagate to the caller."""
        router, emitter = _make_router(tmp_path)

        mock_gde = MagicMock()
        mock_gde.run.side_effect = RuntimeError("engine exploded")

        with patch("genesis_architect.pro.gde_engine_registration", create=True), \
             patch("genesis_architect.pro.GenesisDecisionEngine", return_value=mock_gde):
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "do something"})
            router.handle(msg)
            # Wait for background thread to finish
            time.sleep(0.5)

        # Error is emitted as a session_confidence event with an "error" key
        error_msgs = [m for m in emitter.emitted if "error" in m.payload]
        assert error_msgs, f"No error event emitted. Got: {emitter.types()}"


# ---------------------------------------------------------------------------
# Tests: user.approval
# ---------------------------------------------------------------------------

class TestUserApproval:
    def test_approval_sets_pending_gate_decision(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        pg = router.register_pending_gate("SECURITY_RISK")

        msg = _make_msg(
            MessageType.USER_APPROVAL,
            {"gate_name": "SECURITY_RISK", "decision": "approve"},
        )
        router.handle(msg)
        pg.event.wait(timeout=1.0)

        assert pg.decision == "approve"
        assert pg.event.is_set()

    def test_approval_reject(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        pg = router.register_pending_gate("HARD_GATE")

        msg = _make_msg(
            MessageType.USER_APPROVAL,
            {"gate_name": "HARD_GATE", "decision": "reject"},
        )
        router.handle(msg)
        pg.event.wait(timeout=1.0)
        assert pg.decision == "reject"

    def test_approval_defer(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        pg = router.register_pending_gate("OPTIONAL_GATE")

        msg = _make_msg(
            MessageType.USER_APPROVAL,
            {"gate_name": "OPTIONAL_GATE", "decision": "defer"},
        )
        router.handle(msg)
        pg.event.wait(timeout=1.0)
        assert pg.decision == "defer"

    def test_approval_unknown_gate_does_not_crash(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        msg = _make_msg(
            MessageType.USER_APPROVAL,
            {"gate_name": "NONEXISTENT_GATE", "decision": "approve"},
        )
        # Must not raise
        router.handle(msg)

    def test_approval_missing_gate_name_does_not_crash(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        msg = _make_msg(
            MessageType.USER_APPROVAL,
            {"decision": "approve"},
        )
        router.handle(msg)

    def test_clear_pending_gate(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        router.register_pending_gate("GATE_A")
        router.clear_pending_gate("GATE_A")
        with router._pending_lock:
            assert "GATE_A" not in router._pending_gates


# ---------------------------------------------------------------------------
# Tests: user.voice_start / user.voice_end
# ---------------------------------------------------------------------------

class TestVoice:
    def test_voice_start_resets_chunks(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        with router._voice_lock:
            router._voice_chunks = [b"old data"]
        msg = _make_msg(MessageType.USER_VOICE_START, {})
        router.handle(msg)
        with router._voice_lock:
            assert router._voice_chunks == []

    def test_voice_end_no_audio_does_not_crash(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        msg = _make_msg(MessageType.USER_VOICE_END, {})
        router.handle(msg)  # must not raise

    def test_voice_end_stt_unavailable_emits_error(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        import base64
        audio = base64.b64encode(b"\x00" * 100).decode()

        mock_stt = MagicMock()
        mock_stt.available = False
        router._stt = mock_stt
        router._stt_loaded = True

        msg = _make_msg(MessageType.USER_VOICE_END, {"audio_b64": audio})
        router.handle(msg)
        time.sleep(0.3)

        error_msgs = [m for m in emitter.emitted if "error" in m.payload]
        assert error_msgs, "Expected error event when STT unavailable"

    def test_voice_end_with_audio_transcribes_and_runs_gde(self, tmp_path):
        """voice_end with valid audio must transcribe then run a GDE session."""
        router, emitter = _make_router(tmp_path)
        import base64
        audio = base64.b64encode(b"\x00" * 200).decode()

        mock_stt = MagicMock()
        mock_stt.available = True
        mock_stt.transcribe.return_value = "refactor the auth module"
        router._stt = mock_stt
        router._stt_loaded = True

        mock_report = MagicMock()
        mock_report.session_id = str(uuid.uuid4())
        mock_report.overall_confidence = 0.9
        mock_report.project_risk_level = "LOW"
        mock_report.mode.value = "refactor"

        mock_gde = MagicMock()
        mock_gde.run.return_value = mock_report

        with patch("genesis_architect.pro.gde_engine_registration", create=True), \
             patch("genesis_architect.pro.GenesisDecisionEngine", return_value=mock_gde):
            msg = _make_msg(MessageType.USER_VOICE_END, {"audio_b64": audio})
            router.handle(msg)
            found = emitter.wait_for(MessageType.SESSION_DONE, timeout=3.0)

        assert found, f"Expected session.done after voice round-trip. Got: {emitter.types()}"
        transcript_msgs = [m for m in emitter.emitted if m.type == MessageType.VOICE_TRANSCRIPT]
        assert transcript_msgs, "Expected voice.transcript event"
        assert transcript_msgs[0].payload["text"] == "refactor the auth module"


# ---------------------------------------------------------------------------
# Tests: unknown message type
# ---------------------------------------------------------------------------

class TestUnknownType:
    def test_unknown_type_does_not_crash(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        # Build a message with a known enum value but not handled
        msg = _make_msg(MessageType.IDE_LINE_EVENT, {"file": "x.py", "line": 1})
        router.handle(msg)  # must not raise


# ---------------------------------------------------------------------------
# Tests: PendingGate
# ---------------------------------------------------------------------------

class TestPendingGate:
    def test_default_decision_is_defer(self):
        pg = _PendingGate("MY_GATE")
        assert pg.decision == "defer"
        assert not pg.event.is_set()

    def test_event_is_settable(self):
        pg = _PendingGate("MY_GATE")
        pg.event.set()
        assert pg.event.is_set()
