"""Genesis Companion — VoicePipeline orchestrator.

This module ties together three new behaviors that turn the voice companion
from a clunky bot into something that feels alive:

  1. Real end-of-turn detection — `listen_stream()` (streaming VAD) replaces
     fixed-duration recording in listener.py. This module just calls it.

  2. Barge-in — TTSPipeline.stop() is called the instant VAD detects new
     speech onset while the assistant is playing audio. A background
     "barge-in watcher" thread runs VAD during TTS playback; on speech
     onset it sets a stop event and calls tts.stop(). Full-duplex: the mic
     InputStream stays open throughout.

  3. Mid-turn context prefetch — a partial-transcript callback fires as
     speech frames accumulate. An entity extractor scans each partial for
     file/module names. When one is found, async context tasks are launched
     (fragility lookup + knowledge-graph query) so results are ready by the
     time the user finishes speaking.

Local-first invariant: nothing leaves the machine. Entity names extracted
from partials are matched against the local project graph only.

Usage (minimal):
    from genesis_architect_pro.voice.voice_pipeline import VoicePipeline

    pipeline = VoicePipeline(project_root=".")
    pipeline.start()          # background wake-word listener
    # or for a single PTT turn:
    result = pipeline.listen_and_respond()
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

_log = logging.getLogger("genesis.voice.pipeline")


# ---------------------------------------------------------------------------
# Entity extractor — recognises file/module names in a partial transcript
# ---------------------------------------------------------------------------

class EntityExtractor:
    """Lightweight entity extractor for partial voice transcripts.

    Looks for patterns that match known project modules or file paths.
    All matching is local — no LLM required for extraction.

    Patterns recognised:
      - CamelCase identifiers (AuthModule, PaymentService, …)
      - snake_case identifiers that are ≥2 parts (auth_module, import_graph)
      - Bare filenames with extension (.py / .ts / .js)
      - Bare module references preceded by "module", "file", "class", "function"
    """

    _CAMEL_RE   = re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b')
    _SNAKE_RE   = re.compile(r'\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\b')
    _FILE_RE    = re.compile(r'\b[\w/\\]+\.(?:py|ts|js|jsx|tsx|go|rs)\b')
    _KEYWORD_RE = re.compile(
        r'\b(?:module|file|class|function|method|service|component)\s+([A-Za-z_][\w]*)',
        re.IGNORECASE,
    )

    def __init__(self, known_modules: set[str] | None = None) -> None:
        # Optional set of known module names for tighter matching
        self._known = {m.lower() for m in (known_modules or set())}

    def extract(self, text: str) -> str | None:
        """Return the first entity name found in text, or None."""
        if not text:
            return None

        # Keyword-preceded name (highest confidence)
        for m in self._KEYWORD_RE.finditer(text):
            return m.group(1)

        # CamelCase (high confidence — rarely appears in natural speech otherwise)
        for m in self._CAMEL_RE.finditer(text):
            return m.group(0)

        # File path with extension
        for m in self._FILE_RE.finditer(text):
            return m.group(0)

        # snake_case — only if in known modules list (too many false positives otherwise)
        if self._known:
            for m in self._SNAKE_RE.finditer(text):
                if m.group(0) in self._known:
                    return m.group(0)

        return None

    def update_known(self, modules: set[str]) -> None:
        self._known = {m.lower() for m in modules}


# ---------------------------------------------------------------------------
# Context prefetch — async wrapper around local engines
# ---------------------------------------------------------------------------

class ContextPrefetcher:
    """Fires async context-fetch tasks as soon as an entity is extracted.

    The tasks run against local engines only:
      - Fragility classifier (is the module VOLATILE/FRAGILE/STABLE?)
      - Knowledge graph (what does Genesis know about this module?)

    Results are held in `self.result` and awaited by the final-transcript
    handler. If the fetch completes before the user finishes speaking, the
    response feels instant.
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        self._root = Path(project_root)
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.result: dict[str, Any] = {}
        self.last_entity: str | None = None

    def start_loop_in_thread(self) -> None:
        """Run an asyncio event loop in a daemon thread for background tasks."""
        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        t = threading.Thread(target=_run, daemon=True, name="genesis-prefetch-loop")
        t.start()
        # Wait for the loop to be assigned
        while self._loop is None:
            time.sleep(0.01)

    def prefetch(self, entity: str) -> None:
        """Schedule a context fetch for entity if the loop is running."""
        if entity == self.last_entity:
            return  # already fetching / fetched this entity
        self.last_entity = entity
        self.result = {}
        if self._loop and self._loop.is_running():
            self._task = asyncio.run_coroutine_threadsafe(
                self._fetch(entity), self._loop
            )

    async def _fetch(self, entity: str) -> None:
        """Run local context lookups concurrently."""
        fragility_task = asyncio.create_task(self._fragility_lookup(entity))
        kg_task        = asyncio.create_task(self._kg_lookup(entity))
        frag, kg = await asyncio.gather(fragility_task, kg_task,
                                         return_exceptions=True)
        self.result = {
            "entity":    entity,
            "fragility": frag if not isinstance(frag, Exception) else None,
            "kg":        kg   if not isinstance(kg, Exception)   else None,
        }

    async def _fragility_lookup(self, entity: str) -> dict | None:
        """Query the fragility classifier for a module name (async wrapper)."""
        try:
            from genesis_architect_pro.fragility_classifier import classify_module
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, classify_module, entity, str(self._root)
            )
            return result
        except Exception as exc:
            _log.debug("prefetch fragility error for %s: %s", entity, exc)
            return None

    async def _kg_lookup(self, entity: str) -> dict | None:
        """Query the knowledge graph for a module/node (async wrapper)."""
        try:
            from genesis_architect_pro.knowledge_graph import load_graph
            loop = asyncio.get_event_loop()
            graph = await loop.run_in_executor(None, load_graph, str(self._root))
            node = self._find_node(graph, entity)
            if node is None:
                return None
            return {"id": node.id, "label": node.label,
                    "props": dict(node.metadata)}
        except Exception as exc:
            _log.debug("prefetch KG error for %s: %s", entity, exc)
            return None

    @staticmethod
    def _find_node(graph: Any, entity: str):
        """Match a bare entity name (e.g. "auth_module") to a graph node.

        Node ids are namespaced ("module:src/auth_module.py",
        "anti_pattern:dead-code:src/auth_module.py") so an exact
        graph.get_node(entity) lookup never matches a bare voice-extracted
        name - it only ever matched if the caller happened to pass a full,
        correctly-prefixed id. Search by path tail / label instead.
        """
        needle = entity.lower()
        exact = graph.get_node(needle)
        if exact is not None:
            return exact
        for node_id, node in graph.nodes.items():
            tail = node_id.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
            if needle == tail or needle in node_id.lower() or needle == node.label.lower():
                return node
        return None

    def await_result(self, timeout: float = 0.5) -> dict[str, Any]:
        """Block until the prefetch task completes (or timeout), return result."""
        if self._task is None:
            return {}
        try:
            self._task.result() if self._task.done() else \
                self._task.add_done_callback(lambda _: None)
            # poll with timeout
            deadline = time.monotonic() + timeout
            while not self._task.done() and time.monotonic() < deadline:
                time.sleep(0.02)
        except Exception:
            pass
        return dict(self.result)


# ---------------------------------------------------------------------------
# Barge-in watcher — runs VAD while TTS is playing
# ---------------------------------------------------------------------------

class BargeInWatcher:
    """Monitors the microphone while TTS is playing.

    Runs a lightweight energy / webrtcvad check in a background thread.
    When speech onset is detected, it:
      1. Calls tts.stop() immediately.
      2. Sets the provided barge_event so the pipeline knows to start
         listening again.

    This is "full-duplex" in the sense that the mic InputStream never
    closes; even while audio plays, we're watching for the user's voice.
    """

    _ONSET_FRAMES  = 2   # this many consecutive speech frames = barge-in

    def __init__(self, tts, on_barge_in: Callable[[], None]) -> None:
        self._tts = tts
        self._on_barge_in = on_barge_in
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        """Start the watcher. No-op if already running."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._watch, daemon=True, name="genesis-bargein-watcher"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _watch(self) -> None:
        try:
            import sounddevice as sd  # type: ignore[import]
            import numpy as np
        except ImportError:
            return

        from genesis_architect_pro.voice.listener import _build_vad, _frame_is_speech

        backend = _build_vad()
        onset_count = 0

        def callback(indata, frames, time_info, status):
            nonlocal onset_count
            if self._stop.is_set():
                raise sd.CallbackStop()
            chunk = indata[:, 0] if indata.ndim > 1 else indata
            pcm16 = (np.clip(chunk, -1.0, 1.0) * 32767).astype("<i2")
            speech = _frame_is_speech(backend, pcm16.tobytes(), chunk)

            if speech:
                onset_count += 1
                if onset_count >= self._ONSET_FRAMES:
                    self._tts.stop()
                    try:
                        self._on_barge_in()
                    except Exception:
                        pass
                    raise sd.CallbackStop()
            else:
                onset_count = 0

        try:
            with sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="float32",
                blocksize=backend.frame_samples,
                callback=callback,
            ):
                self._stop.wait()
        except sd.CallbackStop:
            pass
        except Exception as exc:
            _log.debug("BargeInWatcher stream error: %s", exc)


# ---------------------------------------------------------------------------
# VoicePipeline — top-level orchestrator
# ---------------------------------------------------------------------------

class VoicePipeline:
    """Full voice pipeline: listen → prefetch → respond → barge-in.

    Brings together:
      - listener.listen_stream()  — streaming VAD end-of-turn detection
      - TTSPipeline.stop()        — barge-in cancel token
      - ContextPrefetcher         — mid-turn entity prefetch
      - BargeInWatcher            — full-duplex barge-in detection
      - WakeWordListener          — background wake-phrase detection

    The GDE callback (on_instruction) receives:
        (text: str, context: dict) → str (the reply to speak)

    If on_instruction is not provided, the pipeline logs but does not respond.

    Args:
        project_root: path to the project being analysed.
        on_instruction: async or sync callable (text, context) → reply_text.
        lang: 'en' | 'he' for wake phrase matching.
        silence_ms: trailing silence before end-of-turn (default 600ms).
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        on_instruction: Callable[[str, dict], str] | None = None,
        lang: str = "en",
        silence_ms: int = 600,
    ) -> None:
        self._root = Path(project_root)
        self._on_instruction = on_instruction
        self._lang = lang
        self._silence_ms = silence_ms

        # Lazy-init heavy deps
        self._stt = None
        self._tts = None

        self._extractor = EntityExtractor()
        self._prefetcher = ContextPrefetcher(project_root)
        self._prefetcher.start_loop_in_thread()

        self._barge_event = threading.Event()
        self._bargein_watcher: BargeInWatcher | None = None
        self._wake_listener = None

    def _ensure_stt_tts(self) -> bool:
        if self._stt is None:
            from genesis_architect_pro.voice.pipeline import STTPipeline
            self._stt = STTPipeline()
        if self._tts is None:
            from genesis_architect_pro.voice.pipeline import TTSPipeline
            self._tts = TTSPipeline()
        return getattr(self._stt, "available", False)

    # -- public entry points -------------------------------------------------

    def start(self) -> bool:
        """Start background wake-word listener. Returns True if available."""
        if not self._ensure_stt_tts():
            _log.warning("VoicePipeline: STT unavailable — start() is a no-op")
            return False
        from genesis_architect_pro.voice.listener import WakeWordListener
        self._wake_listener = WakeWordListener(
            on_instruction=self._handle_instruction,
            lang=self._lang,
            stt=self._stt,
        )
        return self._wake_listener.start()

    def stop(self) -> None:
        """Stop wake-word listener and any active playback."""
        if self._wake_listener:
            self._wake_listener.stop()
        if self._tts:
            self._tts.stop()
        if self._bargein_watcher:
            self._bargein_watcher.stop()

    def listen_and_respond(self) -> str:
        """Capture one VAD-delimited utterance and respond. PTT-style call."""
        if not self._ensure_stt_tts():
            return ""

        # Accumulate partial PCM bytes → entity extraction
        partial_buf: list[bytes] = []

        def on_partial(pcm_bytes: bytes) -> None:
            partial_buf.append(pcm_bytes)
            # Attempt transcription of accumulated partials periodically
            # (every ~10 partial callbacks ≈ 300ms of new audio)
            if len(partial_buf) % 10 == 0:
                self._try_prefetch_from_partials(b"".join(partial_buf))

        stop_event = threading.Event()
        from genesis_architect_pro.voice.listener import listen_stream
        result = listen_stream(
            stt=self._stt,
            on_partial=on_partial,
            stop_event=stop_event,
            silence_ms=self._silence_ms,
        )

        if not result.ok:
            _log.debug("listen_and_respond: no speech — %s", result.reason)
            return ""

        return self._handle_instruction(result.text)

    # -- internal ------------------------------------------------------------

    def _try_prefetch_from_partials(self, pcm_bytes: bytes) -> None:
        """Decode a partial PCM span and attempt entity extraction."""
        try:
            import numpy as np
            arr = (np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32) / 32768.0)
            partial_text = self._stt.transcribe_array(arr) if self._stt else ""
            if partial_text:
                self._on_partial_transcript(partial_text)
        except Exception as exc:
            _log.debug("partial prefetch decode error: %s", exc)

    def _on_partial_transcript(self, partial: str) -> None:
        """Extract entity from partial transcript → fire prefetch task."""
        entity = self._extractor.extract(partial)
        if entity:
            _log.debug("prefetch triggered for entity: %s", entity)
            self._prefetcher.prefetch(entity)

    def _handle_instruction(self, text: str) -> str:
        """Process a complete utterance: get prefetch context, call GDE, speak."""
        _log.info("instruction: %s", text)

        # Wait for any in-flight prefetch (it's probably already done)
        context = self._prefetcher.await_result(timeout=0.4)
        _log.debug("prefetch context for '%s': %s",
                   context.get("entity"), list(context.keys()))

        if self._on_instruction is None:
            _log.info("no GDE callback — logging only")
            return text

        try:
            reply = self._on_instruction(text, context)
        except Exception as exc:  # noqa: BLE001
            _log.warning("GDE callback error: %s", exc)
            reply = "Sorry, I ran into an error processing that."

        if reply and self._tts:
            self._speak_with_bargein(reply)

        return reply

    def _speak_with_bargein(self, text: str) -> None:
        """Speak text while watching for barge-in.

        Starts BargeInWatcher before playback; on barge-in the watcher
        calls tts.stop() and sets barge_event.
        """
        if self._tts is None:
            return

        self._barge_event.clear()
        watcher = BargeInWatcher(
            tts=self._tts,
            on_barge_in=self._barge_event.set,
        )
        watcher.start()
        try:
            from genesis_architect_pro.voice.pipeline import Urgency
            self._tts.speak(text, urgency=Urgency.NORMAL)
            # For NORMAL urgency, speak() spawns a daemon thread; wait for it
            # by polling is_speaking (also stops if barge-in fires)
            deadline = time.monotonic() + 60
            while self._tts.is_speaking and time.monotonic() < deadline:
                if self._barge_event.is_set():
                    break
                time.sleep(0.05)
        finally:
            watcher.stop()

        if self._barge_event.is_set():
            _log.debug("barge-in detected — playback stopped")
            # Optionally kick off a new listen turn here
