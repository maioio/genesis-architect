"""Genesis Companion streaming — inbound message router.

Routes messages arriving FROM the Tauri app (via WebSocket) to the
appropriate backend handler. All message types are defined in events.py.

Inbound types handled:
  user.intent       — free text instruction, runs a GDE session
  user.approval     — approve / reject / defer a pending gate
  user.voice_start  — begin STT audio capture
  user.voice_end    — finalize STT, transcribe, treat result as user.intent

Design contract:
  - InboundRouter.handle() is always called from a thread pool (see server.py)
  - It must never raise: errors are caught, logged, and emitted as error events
  - GDE sessions run in background threads so handle() returns quickly
  - Pending gates are stored in _pending_gates keyed by gate_name
"""

from __future__ import annotations

import logging
import threading
import tempfile
import os
from pathlib import Path
from typing import Optional

from genesis_architect_pro.streaming.events import (
    StreamEmitter,
    StreamMessage,
    MessageType,
    StreamMessage,
    gate_approval_required,
    session_done,
)

_log = logging.getLogger("genesis.inbound")

# Sentinel emitted to the UI when a handler raises
_ERROR_TYPE = "error"


def _emit_error(emitter: StreamEmitter, msg: str, session_id: str = "") -> None:
    from genesis_architect_pro.streaming.events import StreamMessage, MessageType
    emitter.emit(StreamMessage(
        type=MessageType.SESSION_CONFIDENCE,  # reuse an existing type as error carrier
        payload={"error": msg},
        session_id=session_id,
    ))


class InboundRouter:
    """Routes inbound WebSocket messages to the appropriate backend handler.

    Args:
        project_dir: The project directory for GDE sessions.
        emitter: StreamEmitter used to send outbound events back to the UI.
    """

    def __init__(self, project_dir: Path, emitter: StreamEmitter) -> None:
        self._project_dir = Path(project_dir)
        self._emitter = emitter
        # gate_name -> threading.Event that unblocks the waiting GDE thread
        self._pending_gates: dict[str, _PendingGate] = {}
        self._pending_lock = threading.Lock()
        # Audio accumulator for voice recording
        self._voice_chunks: list[bytes] = []
        self._voice_lock = threading.Lock()
        # Lazy STT pipeline (loads only when first used)
        self._stt: Optional[object] = None
        self._stt_loaded = False

    # ------------------------------------------------------------------
    # Public entry point — called from server.py thread pool
    # ------------------------------------------------------------------

    def handle(self, msg: StreamMessage) -> None:
        """Dispatch one inbound message. Never raises."""
        try:
            t = msg.type
            if t == MessageType.USER_INTENT:
                self._handle_intent(msg)
            elif t == MessageType.USER_APPROVAL:
                self._handle_approval(msg)
            elif t == MessageType.USER_VOICE_START:
                self._handle_voice_start(msg)
            elif t == MessageType.USER_VOICE_END:
                self._handle_voice_end(msg)
            else:
                _log.debug("InboundRouter: unhandled message type %s", msg.type)
        except Exception as exc:
            _log.exception("InboundRouter: unhandled error in handle()")
            _emit_error(self._emitter, str(exc), msg.session_id)

    # ------------------------------------------------------------------
    # user.intent
    # ------------------------------------------------------------------

    def _handle_intent(self, msg: StreamMessage) -> None:
        instruction = msg.payload.get("instruction", "").strip()
        if not instruction:
            _log.warning("InboundRouter: user.intent with empty instruction")
            return
        _log.info("InboundRouter: user.intent -> '%s'", instruction[:80])
        # Run GDE in a background thread so handle() returns immediately
        t = threading.Thread(
            target=self._run_gde,
            args=(instruction, msg.session_id),
            daemon=True,
            name="genesis-inbound-gde",
        )
        t.start()

    def _run_gde(self, instruction: str, session_id: str) -> None:
        """Run a full GDE session and emit session_done when complete."""
        try:
            import genesis_architect_pro.gde_engine_registration  # noqa: F401
            from genesis_architect_pro import GenesisDecisionEngine

            gde = GenesisDecisionEngine(
                project_dir=self._project_dir,
                parallel=True,
            )
            report = gde.run(instruction)

            self._emitter.emit(
                session_done(
                    session_id=report.session_id,
                    confidence=report.overall_confidence,
                    risk_level=str(report.project_risk_level),
                    mode=report.mode.value,
                )
            )
        except Exception as exc:
            _log.exception("InboundRouter: GDE session failed")
            _emit_error(self._emitter, f"GDE error: {exc}", session_id)

    # ------------------------------------------------------------------
    # user.approval
    # ------------------------------------------------------------------

    def _handle_approval(self, msg: StreamMessage) -> None:
        gate_name = msg.payload.get("gate_name", "")
        decision = msg.payload.get("decision", "")  # "approve" | "reject" | "defer"

        if not gate_name:
            _log.warning("InboundRouter: user.approval missing gate_name")
            return

        _log.info("InboundRouter: user.approval gate=%s decision=%s", gate_name, decision)

        with self._pending_lock:
            pending = self._pending_gates.get(gate_name)

        if pending is None:
            _log.warning("InboundRouter: no pending gate for '%s'", gate_name)
            return

        pending.decision = decision
        pending.event.set()

    def register_pending_gate(self, gate_name: str) -> "_PendingGate":
        """Register a gate that is waiting for UI approval.

        Returns a PendingGate. Caller should block on pending.event.wait()
        then read pending.decision.
        """
        pg = _PendingGate(gate_name)
        with self._pending_lock:
            self._pending_gates[gate_name] = pg
        return pg

    def clear_pending_gate(self, gate_name: str) -> None:
        with self._pending_lock:
            self._pending_gates.pop(gate_name, None)

    # ------------------------------------------------------------------
    # user.voice_start
    # ------------------------------------------------------------------

    def _handle_voice_start(self, msg: StreamMessage) -> None:
        with self._voice_lock:
            self._voice_chunks = []
        _log.debug("InboundRouter: voice recording started")

    # ------------------------------------------------------------------
    # user.voice_end
    # ------------------------------------------------------------------

    def _handle_voice_end(self, msg: StreamMessage) -> None:
        # Collect any audio bytes sent inline (optional: payload.audio_b64)
        audio_b64 = msg.payload.get("audio_b64", "")
        with self._voice_lock:
            chunks = list(self._voice_chunks)
            self._voice_chunks = []

        if audio_b64:
            import base64
            try:
                chunks.append(base64.b64decode(audio_b64))
            except Exception:
                pass

        if not chunks:
            _log.warning("InboundRouter: voice_end with no audio data")
            return

        audio_bytes = b"".join(chunks)
        t = threading.Thread(
            target=self._transcribe_and_run,
            args=(audio_bytes, msg.session_id),
            daemon=True,
            name="genesis-inbound-stt",
        )
        t.start()

    def _transcribe_and_run(self, audio_bytes: bytes, session_id: str) -> None:
        stt = self._get_stt()
        if stt is None or not stt.available:
            _log.warning("InboundRouter: STT unavailable, dropping voice_end")
            _emit_error(self._emitter, "STT not available — install voice extra", session_id)
            return

        # Write to temp file and transcribe
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with open(tmp, "wb") as f:
                f.write(audio_bytes)
            text = stt.transcribe(tmp)
        except Exception as exc:
            _log.warning("InboundRouter: STT error: %s", exc)
            return
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        if not text:
            _log.warning("InboundRouter: STT returned empty transcript")
            return

        # Emit the transcript so the UI can show it
        from genesis_architect_pro.streaming.events import StreamMessage, MessageType
        self._emitter.emit(StreamMessage(
            type=MessageType.VOICE_TRANSCRIPT,
            session_id=session_id,
            payload={"text": text},
        ))

        # Treat transcript as a user.intent
        _log.info("InboundRouter: voice -> intent '%s'", text[:80])
        self._run_gde(text, session_id)

    def _get_stt(self):  # type: ignore[return]
        if not self._stt_loaded:
            self._stt_loaded = True
            try:
                from genesis_architect_pro.voice.pipeline import STTPipeline
                self._stt = STTPipeline()
            except Exception as exc:
                _log.warning("InboundRouter: failed to load STTPipeline: %s", exc)
                self._stt = None
        return self._stt


# ---------------------------------------------------------------------------
# Pending gate helper
# ---------------------------------------------------------------------------

class _PendingGate:
    """Holds the state for a gate waiting on UI approval."""

    def __init__(self, gate_name: str) -> None:
        self.gate_name = gate_name
        self.decision: str = "defer"  # default if event times out
        self.event = threading.Event()
