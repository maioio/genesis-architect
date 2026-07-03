"""
Genesis Companion — live microphone listener + wake word.

Closes the last voice gap: the STT pipeline can transcribe *supplied* audio, but
nothing captured from a live microphone. This module records from the mic and
turns speech into instructions, in two modes:

  - **Push-to-talk (PTT):** record while a key/flag is held, then transcribe.
  - **Wake word:** continuously listen; when the wake phrase ("genesis" /
    "ג'נסיס") is heard, capture the following utterance and transcribe it.

Design rules (match the rest of voice/):
  - Local only — no cloud. Uses sounddevice for capture + the existing
    STTPipeline for transcription.
  - Graceful degradation: if sounddevice or a mic is unavailable, every method
    reports honestly and no-ops (never raises, never fakes a transcript).
  - Wake-word detection is transcript-based (no extra model): a short rolling
    window is transcribed and matched against the wake phrases. This is honest
    and dependency-light; a dedicated wake model can slot in later behind the
    same interface.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field

_log = logging.getLogger("genesis.voice.listen")

# Wake phrases per language. Matched case-insensitively as substrings of the
# rolling transcript (Whisper may render "ג'נסיס" a few ways, so we allow
# variants).
WAKE_WORDS = {
    "en": ("genesis", "hey genesis", "ok genesis"),
    "he": ("ג'נסיס", "גנסיס", "היי ג'נסיס", "ג׳נסיס"),
}

_SAMPLE_RATE = 16000       # what faster-whisper expects
_CHANNELS = 1
_DEFAULT_MAX_SECONDS = 15  # safety cap on a single utterance


@dataclass
class ListenResult:
    ok: bool
    text: str = ""
    reason: str = ""       # why it failed / degraded, when ok is False


@dataclass
class MicStatus:
    available: bool
    detail: str = ""
    devices: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Capability probe
# ---------------------------------------------------------------------------

def mic_status() -> MicStatus:
    """Report whether a microphone can be used, honestly."""
    try:
        import sounddevice as sd  # type: ignore[import]
    except ImportError:
        return MicStatus(False,
                         "sounddevice not installed. Run: "
                         "pip install genesis-architect-pro[voice]")
    try:
        inputs = [d["name"] for d in sd.query_devices()
                  if d.get("max_input_channels", 0) > 0]
        if not inputs:
            return MicStatus(False, "No input device (microphone) found.")
        return MicStatus(True, f"{len(inputs)} input device(s) available.",
                         inputs)
    except Exception as exc:  # noqa: BLE001
        return MicStatus(False, f"microphone probe failed: {exc}")


def is_wake(text: str, lang: str = "en") -> bool:
    """True if the transcript contains a wake phrase for the language."""
    if not text:
        return False
    low = text.lower()
    for word in WAKE_WORDS.get(lang, ()):
        if word.lower() in low:
            return True
    # also check the other language's words (bilingual users)
    other = "he" if lang == "en" else "en"
    return any(w.lower() in low for w in WAKE_WORDS.get(other, ()))


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def _record(seconds: float, sample_rate: int = _SAMPLE_RATE):
    """Record `seconds` of mono audio. Returns a numpy float32 array or None."""
    try:
        import sounddevice as sd  # type: ignore[import]
        import numpy as np  # noqa: F401  (sd returns a numpy array)
    except ImportError:
        return None
    try:
        frames = sd.rec(int(seconds * sample_rate), samplerate=sample_rate,
                        channels=_CHANNELS, dtype="float32")
        sd.wait()
        return frames.reshape(-1)
    except Exception as exc:  # noqa: BLE001
        _log.warning("mic record failed: %s", exc)
        return None


def _transcribe_array(audio, stt) -> str:
    """Transcribe a numpy audio array via the STT pipeline. Writes a temp WAV
    because faster-whisper reads files; honest empty string on any failure."""
    if audio is None or stt is None or not getattr(stt, "available", False):
        return ""
    import tempfile
    import os
    import wave
    try:
        import numpy as np
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        with wave.open(path, "wb") as w:
            w.setnchannels(_CHANNELS)
            w.setsampwidth(2)
            w.setframerate(_SAMPLE_RATE)
            w.writeframes(pcm.tobytes())
        try:
            return stt.transcribe(path).strip()
        finally:
            os.unlink(path)
    except Exception as exc:  # noqa: BLE001
        _log.warning("transcription failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Push-to-talk
# ---------------------------------------------------------------------------

def listen_once(seconds: float = 5.0, stt=None) -> ListenResult:
    """Record for `seconds` and return the transcript. The push-to-talk
    primitive: the caller decides when to start (e.g. on key-down) and how long.
    """
    status = mic_status()
    if not status.available:
        return ListenResult(False, reason=status.detail)
    if stt is None:
        from genesis_architect_pro.voice.pipeline import STTPipeline
        stt = STTPipeline()
    if not getattr(stt, "available", False):
        return ListenResult(False,
                            reason="Speech-to-text model not ready. Run: "
                                   "genesis companion --setup")
    seconds = max(0.5, min(seconds, _DEFAULT_MAX_SECONDS))
    audio = _record(seconds, stt and _SAMPLE_RATE or _SAMPLE_RATE)
    text = _transcribe_array(audio, stt)
    if not text:
        return ListenResult(False, reason="No speech detected.")
    return ListenResult(True, text=text)


# ---------------------------------------------------------------------------
# Wake-word listener (continuous)
# ---------------------------------------------------------------------------

class WakeWordListener:
    """Continuously listens for the wake phrase, then captures the following
    utterance and hands the transcript to a callback.

    Runs in a background thread. Honest + interruptible: `start()` is a no-op
    (returns False) if the mic or STT is unavailable; `stop()` ends the loop.
    """

    def __init__(self, on_instruction, lang: str = "en", stt=None,
                 window_seconds: float = 2.0, utterance_seconds: float = 6.0):
        self._on_instruction = on_instruction
        self._lang = lang
        self._stt = stt
        self._window = window_seconds
        self._utterance = utterance_seconds
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.last_error = ""

    def available(self) -> bool:
        if not mic_status().available:
            self.last_error = mic_status().detail
            return False
        if self._stt is None:
            from genesis_architect_pro.voice.pipeline import STTPipeline
            self._stt = STTPipeline()
        if not getattr(self._stt, "available", False):
            self.last_error = ("STT model not ready — run "
                               "genesis companion --setup")
            return False
        return True

    def start(self) -> bool:
        """Begin listening. Returns True if the loop started."""
        if not self.available():
            _log.warning("WakeWordListener not started: %s", self.last_error)
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="genesis-wake-listener")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            window = _record(self._window, _SAMPLE_RATE)
            heard = _transcribe_array(window, self._stt)
            if heard and is_wake(heard, self._lang):
                # Capture the instruction that follows the wake word. If the same
                # window already carried words after the wake phrase, use them;
                # otherwise record a fresh utterance.
                after = _strip_wake(heard, self._lang)
                instruction = after or _transcribe_array(
                    _record(self._utterance, _SAMPLE_RATE), self._stt)
                if instruction:
                    try:
                        self._on_instruction(instruction)
                    except Exception:  # noqa: BLE001
                        _log.exception("wake callback error")
            time.sleep(0.05)


def _strip_wake(text: str, lang: str) -> str:
    """Remove the wake phrase from the front of a transcript, returning any
    trailing instruction ('genesis recover this' -> 'recover this')."""
    low = text.lower()
    words = list(WAKE_WORDS.get(lang, ())) + list(
        WAKE_WORDS.get("he" if lang == "en" else "en", ()))
    for w in sorted(words, key=len, reverse=True):
        idx = low.find(w.lower())
        if idx != -1:
            return text[idx + len(w):].strip(" ,.:—-")
    return ""
