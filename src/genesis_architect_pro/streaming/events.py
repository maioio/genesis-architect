"""Genesis Companion streaming — event types and emitter.

Defines the 20+ message types that flow over the WebSocket from the
genesis-core sidecar to the Companion UI. Each event is a JSON-serialisable
dataclass. The emitter is a synchronous callable that any part of the
codebase can call — it queues events onto an asyncio queue that the
WebSocket server drains.

Design rule: events are fire-and-forget. Emitting an event never blocks
the caller and never raises. A missing or closed WebSocket is silently
ignored.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Message types (matches COMPANION_APP_ARCHITECTURE.md §2.2)
# ---------------------------------------------------------------------------

class MessageType(str, Enum):
    # Engine lifecycle
    ENGINE_START      = "engine.start"
    ENGINE_PROGRESS   = "engine.progress"
    ENGINE_DONE       = "engine.done"
    ENGINE_FAILED     = "engine.failed"
    # Gate
    GATE_FIRED        = "gate.fired"
    GATE_APPROVAL     = "gate.approval_required"
    # Session
    SESSION_START      = "session.start"
    SESSION_CONFIDENCE = "session.confidence"
    SESSION_REPLY      = "session.reply"
    SESSION_DONE       = "session.done"
    # Committee (PRO)
    COMMITTEE_ADVISOR  = "committee.advisor_round"
    COMMITTEE_SYNTHESIS = "committee.synthesis"
    # Voice
    VOICE_TRANSCRIPT  = "voice.transcript"
    VOICE_TTS_CHUNK   = "voice.tts_chunk"
    # IDE bridge
    IDE_LINE_EVENT    = "ide.line_event"
    # Diff / approval
    DIFF_READY        = "diff.ready"
    # Inbound (UI → sidecar) — included for completeness / parsing
    USER_INTENT       = "user.intent"
    USER_APPROVAL     = "user.approval"
    USER_VOICE_START  = "user.voice_start"
    USER_VOICE_END    = "user.voice_end"


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

@dataclass
class StreamMessage:
    type: MessageType
    payload: dict[str, Any]
    session_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))

    def to_json(self) -> str:
        d = {
            "id": self.id,
            "type": self.type.value,
            "ts": self.ts,
            "session_id": self.session_id,
            "payload": self.payload,
        }
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "StreamMessage":
        d = json.loads(raw)
        return cls(
            type=MessageType(d["type"]),
            payload=d.get("payload", {}),
            session_id=d.get("session_id", ""),
            id=d.get("id", str(uuid.uuid4())),
            ts=d.get("ts", 0),
        )


# ---------------------------------------------------------------------------
# Typed constructors (keeps payloads consistent with the spec)
# ---------------------------------------------------------------------------

def engine_start(engine_id: str, phase: int, total_phases: int, session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.ENGINE_START,
        session_id=session_id,
        payload={"engine": engine_id, "phase": phase, "total_phases": total_phases},
    )

def engine_progress(engine_id: str, pct: float, current_op: str = "", session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.ENGINE_PROGRESS,
        session_id=session_id,
        payload={"engine": engine_id, "pct": round(pct, 2), "current_op": current_op},
    )

def engine_done(engine_id: str, confidence: float, result_summary: str = "", session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.ENGINE_DONE,
        session_id=session_id,
        payload={"engine": engine_id, "confidence": round(confidence, 4), "result_summary": result_summary},
    )

def engine_failed(engine_id: str, error: str, confidence_penalty: float = 0.0, session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.ENGINE_FAILED,
        session_id=session_id,
        payload={"engine": engine_id, "error": error, "confidence_penalty": round(confidence_penalty, 4)},
    )

def gate_fired(gate_name: str, gate_type: str, overridable: bool, session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.GATE_FIRED,
        session_id=session_id,
        payload={"gate_name": gate_name, "type": gate_type, "overridable": overridable},
    )

def gate_approval_required(gate_name: str, description: str, diff_preview: str = "", session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.GATE_APPROVAL,
        session_id=session_id,
        payload={"gate_name": gate_name, "description": description, "diff_preview": diff_preview},
    )

def session_confidence(confidence: float, risk_level: str, session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.SESSION_CONFIDENCE,
        session_id=session_id,
        payload={"confidence": round(confidence, 4), "risk_level": risk_level},
    )

def session_start(session_id: str, mode: str = "", instruction: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.SESSION_START,
        session_id=session_id,
        payload={"mode": mode, "instruction": instruction},
    )

def session_reply(text: str, session_id: str = "") -> StreamMessage:
    """The assistant's conversational answer for a completed run — shown as a
    chat turn in the Companion and spoken aloud."""
    return StreamMessage(
        type=MessageType.SESSION_REPLY,
        session_id=session_id,
        payload={"text": text},
    )

def session_done(session_id: str, confidence: float, risk_level: str, mode: str) -> StreamMessage:
    return StreamMessage(
        type=MessageType.SESSION_DONE,
        session_id=session_id,
        payload={"confidence": round(confidence, 4), "risk_level": risk_level, "mode": mode},
    )

def committee_advisor(advisor: str, position: str, confidence: float, session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.COMMITTEE_ADVISOR,
        session_id=session_id,
        payload={"advisor": advisor, "position": position, "confidence": round(confidence, 4)},
    )

def committee_synthesis(verdict: str, consensus_type: str, minority_view: str | None, session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.COMMITTEE_SYNTHESIS,
        session_id=session_id,
        payload={"verdict": verdict, "consensus_type": consensus_type, "minority_view": minority_view},
    )

def diff_ready(diff_id: str, files_changed: int, preview_html: str = "", session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.DIFF_READY,
        session_id=session_id,
        payload={"diff_id": diff_id, "files_changed": files_changed, "preview_html": preview_html},
    )

def ide_line_event(file: str, line: int, pattern: str, severity: str, suggestion: str, session_id: str = "") -> StreamMessage:
    return StreamMessage(
        type=MessageType.IDE_LINE_EVENT,
        session_id=session_id,
        payload={"file": file, "line": line, "pattern": pattern, "severity": severity, "suggestion": suggestion},
    )


# ---------------------------------------------------------------------------
# Emitter — thread-safe, non-blocking
# ---------------------------------------------------------------------------

class StreamEmitter:
    """Collects events from sync code and forwards them to an asyncio queue.

    Usage (sync caller, e.g. GDE runner)::

        emitter = StreamEmitter()
        emitter.emit(engine_start("import_graph", phase=1, total_phases=3))

    The WebSocket server reads from emitter.queue.
    If no WebSocket is connected, events are silently discarded.
    """

    def __init__(self, maxsize: int = 256) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None
        self._maxsize = maxsize

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach to a running event loop. Called by the WebSocket server at startup."""
        self._loop = loop
        self._queue = asyncio.Queue(maxsize=self._maxsize)

    @property
    def queue(self) -> asyncio.Queue | None:
        return self._queue

    def emit(self, message: StreamMessage) -> None:
        """Enqueue a message from any thread. Never raises, never blocks."""
        if self._loop is None or self._queue is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, message)
        except Exception:
            pass  # queue full or loop closed — discard silently

    def detach(self) -> None:
        self._loop = None
        self._queue = None


# Module-level default emitter — used by runner_patch and engine adapters.
default_emitter = StreamEmitter()
