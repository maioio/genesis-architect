"""Genesis Companion streaming — inbound message router.

Routes messages arriving FROM the Tauri app (via WebSocket) to the
appropriate backend handler. All message types are defined in events.py.

Inbound types handled:
  user.intent       — free text instruction, runs a GDE session
  user.approval     — approve / reject / defer a pending gate
  user.voice_start  — begin STT audio capture
  user.voice_end    — finalize STT, transcribe, treat result as user.intent

Gate resume flow:
  1. _run_gde() calls gde.run(instruction) → report
  2. If report has BLOCK → emit gate.approval_required + diff.ready, register PendingGate
  3. _handle_approval() finds the PendingGate, sets decision + event
  4. _run_gde() resumes, calls gde.approve() + gde.commit()
  5. IDE Bridge index is hot-swapped after every GDE run

Design contract:
  - InboundRouter.handle() is always called from a thread pool (see server.py)
  - It must never raise: errors are caught, logged, and emitted as error events
  - GDE sessions run in background threads so handle() returns quickly
  - Pending gates are stored in _pending_gates keyed by session_id
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
    gate_approval_required,
    session_done,
    session_reply,
    session_start,
    diff_ready,
)

_log = logging.getLogger("genesis.inbound")

# Timeout (seconds) to wait for UI approval before auto-deferring
_GATE_TIMEOUT_S = 300


def _emit_error(emitter: StreamEmitter, msg: str, session_id: str = "") -> None:
    emitter.emit(StreamMessage(
        type=MessageType.SESSION_CONFIDENCE,
        payload={"error": msg},
        session_id=session_id,
    ))


def _is_hebrew(text: str) -> bool:
    return any(0x0590 <= ord(c) <= 0x05FF for c in text)


def _compose_reply(report: object, instruction: str) -> str:
    """Turn a SessionReport into a short spoken-style answer with the actual
    findings — what a voice assistant would say, not a status line.

    Answers in the user's language (Hebrew instruction → Hebrew reply).
    Never raises; falls back to a minimal sentence on any surprise shape.
    """
    he = _is_hebrew(instruction)
    try:
        results = getattr(report, "engine_results", {}) or {}

        def out(engine: str) -> dict:
            r = results.get(engine)
            return getattr(r, "output", {}) or {} if r is not None else {}

        score = out("architecture_scorer").get("score")
        cycles = out("import_graph").get("cycles") or []
        critical = out("antipattern_detector").get("critical_count") or 0
        volatile = out("fragility_classifier").get("volatile_count") or 0
        pending = len(getattr(report, "pending_writes", []) or [])
        gate = getattr(getattr(report, "gate_report", None), "overall", None)
        gate_val = getattr(gate, "value", "") if gate is not None else ""
        mode = getattr(getattr(report, "mode", None), "value", "") or "session"

        parts: list[str] = []
        if he:
            parts.append(f"סיימתי את ריצת ה-{mode}.")
            if isinstance(score, (int, float)):
                parts.append(f"ציון הארכיטקטורה הוא {round(score)} מתוך 100.")
            findings = []
            if cycles:
                findings.append(f"{len(cycles)} תלויות מעגליות")
            if critical:
                findings.append(f"{critical} אנטי-תבניות קריטיות")
            if volatile:
                findings.append(f"{volatile} מודולים תנודתיים")
            if findings:
                parts.append("מצאתי " + ", ".join(findings) + ".")
            elif isinstance(score, (int, float)) and score >= 80:
                parts.append("לא מצאתי בעיות מהותיות.")
            if gate_val == "hard_block":
                parts.append("שער קשיח חסם את הריצה — שום דבר לא ייכתב.")
            elif pending:
                parts.append(f"יש {pending} כתיבות שממתינות לאישור שלך בפאנל.")
        else:
            parts.append(f"Done — {mode} run complete.")
            if isinstance(score, (int, float)):
                parts.append(f"Architecture score is {round(score)} out of 100.")
            findings = []
            if cycles:
                findings.append(f"{len(cycles)} circular dependenc{'y' if len(cycles) == 1 else 'ies'}")
            if critical:
                findings.append(f"{critical} critical anti-pattern{'s' if critical != 1 else ''}")
            if volatile:
                findings.append(f"{volatile} volatile module{'s' if volatile != 1 else ''}")
            if findings:
                parts.append("I found " + ", ".join(findings) + ".")
            elif isinstance(score, (int, float)) and score >= 80:
                parts.append("No significant issues found.")
            if gate_val == "hard_block":
                parts.append("A hard gate blocked this run — nothing will be written.")
            elif pending:
                parts.append(f"{pending} write{'s' if pending != 1 else ''} awaiting your approval in the panel.")

        return " ".join(parts)
    except Exception:
        return "הריצה הסתיימה." if he else "The run is complete."


class InboundRouter:
    """Routes inbound WebSocket messages to the appropriate backend handler.

    Args:
        project_dir: The project directory for GDE sessions.
        emitter: StreamEmitter used to send outbound events back to the UI.
        ide_bridge: Optional IDEBridgeServer — updated after each GDE run.
    """

    def __init__(
        self,
        project_dir: Path,
        emitter: StreamEmitter,
        ide_bridge: object | None = None,
    ) -> None:
        self._project_dir = Path(project_dir)
        self._emitter = emitter
        self._ide_bridge = ide_bridge  # IDEBridgeServer | None
        # session_id / gate_name -> _PendingGate (waiting for user.approval)
        self._pending_gates: dict[str, _PendingGate] = {}
        self._pending_lock = threading.Lock()
        # Audio accumulator for voice recording
        self._voice_chunks: list[bytes] = []
        self._voice_lock = threading.Lock()
        # Lazy STT pipeline (loads only when first used)
        self._stt: Optional[object] = None
        self._stt_loaded = False
        # Lazy TTS pipeline for spoken replies
        self._tts: Optional[object] = None
        self._tts_loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_ide_bridge(self, bridge: object) -> None:
        """Attach the IDEBridgeServer after construction (used in gde_cli.py)."""
        self._ide_bridge = bridge

    def _speak(self, text: str) -> None:
        """Speak the reply aloud (local TTS). Best-effort and non-blocking —
        voice being unavailable must never break the session flow.

        GENESIS_COMPANION_MUTE=1 skips loading the TTS stack entirely — used
        by the test suite (loading onnxruntime inside pytest triggered an
        access-violation crash later in the run) and useful for silent CI.
        """
        if os.environ.get("GENESIS_COMPANION_MUTE"):
            return
        try:
            if not self._tts_loaded:
                self._tts_loaded = True
                from genesis_architect_pro.voice.pipeline import TTSPipeline
                self._tts = TTSPipeline()
            if self._tts is not None:
                self._tts.speak(text)  # NORMAL urgency → plays on a daemon thread
        except Exception as exc:
            _log.debug("InboundRouter: TTS unavailable (%s)", exc)

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
        t = threading.Thread(
            target=self._run_gde,
            args=(instruction, msg.session_id),
            daemon=True,
            name="genesis-inbound-gde",
        )
        t.start()

    def _run_gde(self, instruction: str, session_id: str) -> None:
        """Run a full GDE session including approve/commit gate resume flow."""
        try:
            import genesis_architect_pro.gde_engine_registration  # noqa: F401
            from genesis_architect_pro import GenesisDecisionEngine
            from genesis_architect_pro.gde_types import (
                ApprovalChoice,
                ApprovalDecision,
                GateOutcome,
            )

            gde = GenesisDecisionEngine(
                project_dir=self._project_dir,
                parallel=True,
            )
            self._emitter.emit(session_start(
                session_id=session_id, instruction=instruction,
            ))
            report = gde.run(instruction)

            # Hot-swap IDE Bridge pattern index after every run
            self._update_ide_bridge(report)

            # Conversational answer — shown as a chat turn and spoken aloud.
            # Emitted before any approval wait so the user hears the findings
            # immediately, including whether their approval is needed.
            reply = _compose_reply(report, instruction)
            self._emitter.emit(session_reply(reply, session_id=report.session_id))
            self._speak(reply)

            gate_overall = report.gate_report.overall

            # HARD_BLOCK: cannot be overridden
            if gate_overall == GateOutcome.HARD_BLOCK:
                _log.info("InboundRouter: GDE HARD_BLOCK — no approval possible")
                self._emitter.emit(session_done(
                    session_id=report.session_id,
                    confidence=report.overall_confidence,
                    risk_level=str(report.project_risk_level),
                    mode=report.mode.value,
                ))
                return

            # BLOCK/WARN with pending writes — needs UI approval
            has_blocks = bool(report.gate_report.blocks)
            has_writes = bool(getattr(report, "pending_writes", None))
            needs_approval = (gate_overall in (GateOutcome.BLOCK, GateOutcome.WARN)) and (
                has_blocks or has_writes
            )

            if needs_approval:
                approval_request = gde.approve(report)
                preview_html = self._build_diff_preview(approval_request)
                pending_count = len(getattr(approval_request, "pending_writes", []))
                gate_key = f"{report.session_id[:8]}-gate"

                # Emit gate.approval_required → Panel shows gate banner
                self._emitter.emit(gate_approval_required(
                    gate_name=gate_key,
                    description=getattr(approval_request, "summary", "Approval required"),
                    diff_preview=preview_html,
                    session_id=report.session_id,
                ))

                # Emit diff.ready → Panel shows ApprovalModal with full diff
                if preview_html:
                    import uuid as _uuid
                    self._emitter.emit(diff_ready(
                        diff_id=str(_uuid.uuid4()),
                        files_changed=pending_count,
                        preview_html=preview_html,
                        session_id=report.session_id,
                    ))

                # Block this thread until UI responds (or 5-min timeout → defer)
                pg = self._register_pending_gate(report.session_id, gate_key)
                resolved = pg.event.wait(timeout=_GATE_TIMEOUT_S)
                self._clear_pending_gate(report.session_id, gate_key)

                decision_str = pg.decision if resolved else "defer"
                _log.info(
                    "InboundRouter: gate %s resolved=%s decision=%s",
                    gate_key, resolved, decision_str,
                )

                choice_map = {
                    "approve": ApprovalChoice.APPROVE,
                    "reject": ApprovalChoice.REJECT,
                    "defer": ApprovalChoice.DEFER,
                }
                choice = choice_map.get(decision_str, ApprovalChoice.DEFER)

                if choice != ApprovalChoice.DEFER:
                    decision = ApprovalDecision(
                        session_id=report.session_id,
                        choice=choice,
                    )
                    commit_result = gde.commit(report, decision)
                    if not commit_result.success:
                        for err in commit_result.errors:
                            _log.error("InboundRouter: commit error: %s", err)

            # Emit session.done in all non-HARD_BLOCK paths
            self._emitter.emit(session_done(
                session_id=report.session_id,
                confidence=report.overall_confidence,
                risk_level=str(report.project_risk_level),
                mode=report.mode.value,
            ))

        except Exception as exc:
            _log.exception("InboundRouter: GDE session failed")
            _emit_error(self._emitter, f"GDE error: {exc}", session_id)

    def _build_diff_preview(self, approval_request: object) -> str:
        """Build minimal HTML diff preview from pending write operations."""
        writes = getattr(approval_request, "pending_writes", [])
        if not writes:
            return ""
        lines = [
            "<ul style='margin:0;padding-left:1.2em;"
            "font-family:monospace;font-size:12px;line-height:1.6'>"
        ]
        for op in writes[:20]:
            path = getattr(op, "target_path", "?")
            desc = getattr(op, "description", "")
            reversible = getattr(op, "is_reversible", True)
            rev_label = (
                "<span style='color:#888'>reversible</span>"
                if reversible
                else "<span style='color:#f87171;font-weight:600'>IRREVERSIBLE</span>"
            )
            lines.append(f"<li><code>{path}</code> — {desc} ({rev_label})</li>")
        lines.append("</ul>")
        return "\n".join(lines)

    def _update_ide_bridge(self, report: object) -> None:
        """Hot-swap IDE Bridge pattern index after a GDE run."""
        if self._ide_bridge is None:
            return
        try:
            from genesis_architect_pro.ide_bridge import build_index_from_engine_results
            raw_results: dict = {}
            for eid, r in getattr(report, "engine_results", {}).items():
                raw_results[eid] = {
                    "output": getattr(r, "output", {}),
                    "status": str(getattr(r, "status", "")),
                }
            index = build_index_from_engine_results(raw_results)
            self._ide_bridge.update_index(index, session_id=report.session_id)
            _log.debug("InboundRouter: IDE Bridge index updated (%d files)", len(index))
        except Exception as exc:
            _log.warning("InboundRouter: IDE Bridge update failed: %s", exc)

    # ------------------------------------------------------------------
    # user.approval
    # ------------------------------------------------------------------

    def _handle_approval(self, msg: StreamMessage) -> None:
        gate_id = msg.payload.get("gate_id") or msg.payload.get("gate_name", "")
        decision = msg.payload.get("decision", "defer")

        if not gate_id:
            _log.warning("InboundRouter: user.approval missing gate_id")
            return

        _log.info("InboundRouter: user.approval gate=%s decision=%s", gate_id, decision)

        with self._pending_lock:
            pg = self._pending_gates.get(gate_id)
            if pg is None:
                # Try prefix match (gate_id may be "<session[:8]>-gate" or full session_id)
                for key, candidate in self._pending_gates.items():
                    if key.startswith(gate_id[:8]) or gate_id.startswith(key[:8]):
                        pg = candidate
                        break

        if pg is None:
            _log.warning("InboundRouter: no pending gate matching '%s'", gate_id)
            return

        pg.decision = decision
        pg.event.set()

    def _register_pending_gate(self, session_id: str, gate_key: str) -> "_PendingGate":
        pg = _PendingGate(gate_key)
        with self._pending_lock:
            self._pending_gates[gate_key] = pg
            self._pending_gates[session_id] = pg
        return pg

    def _clear_pending_gate(self, session_id: str, gate_key: str) -> None:
        with self._pending_lock:
            self._pending_gates.pop(gate_key, None)
            self._pending_gates.pop(session_id, None)

    # Kept for external callers (gate_notifier_patch)
    def register_pending_gate(self, gate_name: str) -> "_PendingGate":
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

        self._emitter.emit(StreamMessage(
            type=MessageType.VOICE_TRANSCRIPT,
            session_id=session_id,
            payload={"text": text, "is_final": True},
        ))

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
        self.decision: str = "defer"
        self.event = threading.Event()