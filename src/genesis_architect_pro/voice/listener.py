"""
Genesis Companion — live microphone listener + wake word.

Two capture modes:
  - **Push-to-talk (PTT):** `listen_once()` — record for a fixed duration and
    transcribe. Simple fallback.
  - **Streaming VAD:** `listen_stream()` / `WakeWordListener` — open a continuous
    InputStream, route frames through a lightweight VAD, close the utterance after
    ~600ms of trailing silence. No fixed-duration recording; the turn ends when
    the user stops talking.

Changes vs. the original implementation
  1. `_transcribe_array()` now feeds audio directly into faster-whisper as a
     numpy array (no temp WAV file per utterance).
  2. VAD is done by webrtcvad (preferred, tiny C extension) with a pure-Python
     energy fallback — so the code never crashes when webrtcvad is absent.
  3. Wake-word detection gates expensive STT behind cheap VAD: only transcribe
     frames that actually contain speech.
  4. `listen_stream()` — new public function that captures one VAD-delimited
     utterance and returns a ListenResult.  Used by VoicePipeline.
  5. `WakeWordListener._loop()` now uses the streaming path instead of
     fixed-duration blocking records.

Local-first invariant: no audio ever leaves the machine.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

_log = logging.getLogger("genesis.voice.listen")

WAKE_WORDS = {
    "en": ("genesis", "hey genesis", "ok genesis"),
    "he": ("ג'נסיס", "גנסיס", "היי ג'נסיס", "ג׳נסיס"),
}

_SAMPLE_RATE    = 16000   # what faster-whisper expects
_CHANNELS       = 1
_FRAME_MS       = 30      # VAD frame size in milliseconds (10/20/30 are valid for webrtcvad)
_FRAME_SAMPLES  = _SAMPLE_RATE * _FRAME_MS // 1000   # 480 samples per frame at 16 kHz
_VAD_MODE       = 3       # webrtcvad aggressiveness: 0 (least) – 3 (most aggressive)
_SILENCE_FRAMES = 20      # ~600ms silence (20 × 30ms) before closing an utterance
_PRE_ROLL_FRAMES = 5      # frames to keep before speech onset (so we don't clip the start)
_MAX_UTTERANCE_S = 15     # hard cap on a single utterance in seconds
_WAKE_WINDOW_S  = 2.0     # seconds of audio to check for wake word


@dataclass
class ListenResult:
    ok: bool
    text: str = ""
    reason: str = ""


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
        return MicStatus(True, f"{len(inputs)} input device(s) available.", inputs)
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
    other = "he" if lang == "en" else "en"
    return any(w.lower() in low for w in WAKE_WORDS.get(other, ()))


# ---------------------------------------------------------------------------
# VAD helpers
# ---------------------------------------------------------------------------

def _build_vad():
    """Return a (vad, mode) tuple using webrtcvad if available, else None."""
    try:
        import webrtcvad  # type: ignore[import]
        vad = webrtcvad.Vad(_VAD_MODE)
        return vad
    except ImportError:
        return None


def _frame_is_speech_webrtc(vad, pcm_bytes: bytes) -> bool:
    """Ask webrtcvad whether a 16-bit PCM frame contains speech."""
    try:
        return vad.is_speech(pcm_bytes, _SAMPLE_RATE)
    except Exception:
        return False


def _frame_is_speech_energy(frame_f32, threshold: float = 0.002) -> bool:
    """Pure-Python energy-based VAD fallback (no dependency)."""
    try:
        import numpy as np
        rms = float(np.sqrt(np.mean(frame_f32 ** 2)))
        return rms > threshold
    except Exception:
        return False


# ---------------------------------------------------------------------------
# In-memory transcription (no temp file)
# ---------------------------------------------------------------------------

def _transcribe_array(audio, stt) -> str:
    """Transcribe a numpy float32 audio array via faster-whisper.

    Passes the array directly to the model — no temp WAV file on disk.
    Returns empty string on any failure.
    """
    if audio is None or stt is None or not getattr(stt, "available", False):
        return ""
    try:
        import numpy as np
        arr = np.asarray(audio, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.reshape(-1)
        if arr.size == 0:
            return ""
        # faster-whisper accepts a numpy array directly (no file path needed)
        segments, _ = stt._model.transcribe(arr, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
    except Exception as exc:  # noqa: BLE001
        _log.warning("transcription failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Streaming VAD capture — the core new primitive
# ---------------------------------------------------------------------------

def _capture_utterance_streaming(
    *,
    stt=None,
    on_partial: Callable[[bytes], None] | None = None,
    stop_event: threading.Event | None = None,
    silence_frames: int = _SILENCE_FRAMES,
    max_seconds: float = _MAX_UTTERANCE_S,
) -> "tuple[object | None, bool]":
    """Open a sounddevice InputStream and return (audio_array, got_speech).

    Streams mic frames through VAD; captures from first speech onset to
    `silence_frames` consecutive silent frames (≈600ms default).

    Args:
        on_partial: called with accumulated PCM bytes after each speech frame —
                    lets the pipeline do entity extraction mid-utterance.
        stop_event: set by barge-in or external stop to abort capture early.

    Returns:
        (numpy float32 array, True) on success, or (None, False) on failure/empty.
    """
    try:
        import sounddevice as sd  # type: ignore[import]
        import numpy as np
    except ImportError:
        return None, False

    vad = _build_vad()
    captured_frames: list[bytes] = []   # raw PCM int16 bytes
    pre_roll: deque[bytes] = deque(maxlen=_PRE_ROLL_FRAMES)
    in_speech = False
    silence_count = 0
    max_frames = int(max_seconds * 1000 / _FRAME_MS)
    frame_count = 0
    done_event = threading.Event()
    result_frames: list[bytes] = []

    def callback(indata, frames, time_info, status):  # noqa: ARG001
        nonlocal in_speech, silence_count, frame_count, result_frames

        if stop_event and stop_event.is_set():
            done_event.set()
            raise sd.CallbackStop()

        # Convert float32 → int16 PCM for VAD
        chunk = indata[:, 0] if indata.ndim > 1 else indata
        pcm16 = (np.clip(chunk, -1.0, 1.0) * 32767).astype("<i2")
        pcm_bytes = pcm16.tobytes()

        # Determine speech vs silence
        if vad is not None:
            speech = _frame_is_speech_webrtc(vad, pcm_bytes)
        else:
            speech = _frame_is_speech_energy(chunk)

        if not in_speech:
            pre_roll.append(pcm_bytes)
            if speech:
                in_speech = True
                silence_count = 0
                captured_frames.extend(list(pre_roll))
                pre_roll.clear()
        else:
            captured_frames.append(pcm_bytes)
            if not speech:
                silence_count += 1
            else:
                silence_count = 0
                if on_partial:
                    # provide accumulated bytes to partial-transcript consumer
                    try:
                        on_partial(b"".join(captured_frames))
                    except Exception:  # noqa: BLE001
                        pass
            if silence_count >= silence_frames or frame_count >= max_frames:
                result_frames = list(captured_frames)
                done_event.set()
                raise sd.CallbackStop()

        frame_count += 1

    try:
        with sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="float32",
            blocksize=_FRAME_SAMPLES,
            callback=callback,
        ):
            done_event.wait(timeout=max_seconds + 2)
    except sd.CallbackStop:
        pass
    except Exception as exc:  # noqa: BLE001
        _log.warning("InputStream error: %s", exc)
        return None, False

    if not result_frames and captured_frames:
        # stopped by stop_event mid-utterance — use what we have
        result_frames = list(captured_frames)

    if not result_frames:
        return None, False

    try:
        pcm_all = b"".join(result_frames)
        arr = np.frombuffer(pcm_all, dtype="<i2").astype(np.float32) / 32768.0
        return arr, True
    except Exception as exc:  # noqa: BLE001
        _log.warning("PCM assembly failed: %s", exc)
        return None, False


# ---------------------------------------------------------------------------
# Push-to-talk (original fixed-duration path — kept as fallback)
# ---------------------------------------------------------------------------

def _record(seconds: float, sample_rate: int = _SAMPLE_RATE):
    """Record `seconds` of mono audio. Returns numpy float32 array or None."""
    try:
        import sounddevice as sd  # type: ignore[import]
        import numpy as np  # noqa: F401
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


def listen_once(seconds: float = 5.0, stt=None) -> ListenResult:
    """PTT fallback: record for `seconds` and return the transcript."""
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
    seconds = max(0.5, min(seconds, _MAX_UTTERANCE_S))
    audio = _record(seconds)
    text = _transcribe_array(audio, stt)
    if not text:
        return ListenResult(False, reason="No speech detected.")
    return ListenResult(True, text=text)


# ---------------------------------------------------------------------------
# Public streaming capture
# ---------------------------------------------------------------------------

def listen_stream(
    stt=None,
    on_partial: Callable[[bytes], None] | None = None,
    stop_event: threading.Event | None = None,
    silence_ms: int = 600,
) -> ListenResult:
    """Capture one VAD-delimited utterance and transcribe it.

    The turn ends automatically when the user stops talking for `silence_ms`
    milliseconds (default 600ms). This is the primary capture path for
    VoicePipeline; `listen_once()` is the PTT fallback.

    Args:
        stt: an STTPipeline instance; created if not provided.
        on_partial: called with raw PCM bytes as speech accumulates —
                    use for mid-turn entity extraction.
        stop_event: set externally (e.g. by barge-in) to abort capture.
        silence_ms: trailing silence (ms) before closing the turn.
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

    silence_frames = max(1, silence_ms // _FRAME_MS)
    audio, got = _capture_utterance_streaming(
        stt=stt,
        on_partial=on_partial,
        stop_event=stop_event,
        silence_frames=silence_frames,
    )
    if not got or audio is None:
        return ListenResult(False, reason="No speech detected.")

    text = _transcribe_array(audio, stt)
    if not text:
        return ListenResult(False, reason="Could not transcribe audio.")
    return ListenResult(True, text=text)


# ---------------------------------------------------------------------------
# Wake-word listener (continuous, streaming)
# ---------------------------------------------------------------------------

class WakeWordListener:
    """Continuously listens for the wake phrase, then captures the following
    utterance and calls `on_instruction` with the transcript.

    Uses streaming VAD so wake detection is no longer a 2s blocking record +
    full transcription on every loop. Instead:
      1. Collect frames until VAD sees speech (cheap).
      2. Transcribe only the speech-containing span.
      3. If it contains a wake word, capture the next VAD-delimited utterance
         and call on_instruction.

    Runs in a background daemon thread.
    """

    def __init__(
        self,
        on_instruction: Callable[[str], None],
        lang: str = "en",
        stt=None,
        utterance_seconds: float = 15.0,
    ) -> None:
        self._on_instruction = on_instruction
        self._lang = lang
        self._stt = stt
        self._utterance_seconds = utterance_seconds
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
            self.last_error = "STT model not ready — run genesis companion --setup"
            return False
        return True

    def start(self) -> bool:
        if not self.available():
            _log.warning("WakeWordListener not started: %s", self.last_error)
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="genesis-wake-listener"
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        """Main loop: VAD-gated wake-word detection then utterance capture."""
        while not self._stop.is_set():
            # Capture a short VAD-delimited span for wake detection.
            # Silence frames set low (~10 frames = 300ms) so we react quickly
            # to a single spoken word without waiting 600ms.
            audio, got = _capture_utterance_streaming(
                stt=self._stt,
                stop_event=self._stop,
                silence_frames=10,           # ~300ms trailing silence for wake check
                max_seconds=_WAKE_WINDOW_S,
            )
            if self._stop.is_set():
                break
            if not got or audio is None:
                time.sleep(0.02)
                continue

            heard = _transcribe_array(audio, self._stt)
            if not heard or not is_wake(heard, self._lang):
                continue

            # Wake phrase detected — capture the instruction that follows.
            after = _strip_wake(heard, self._lang)
            if after:
                instruction = after
            else:
                result = listen_stream(
                    stt=self._stt,
                    stop_event=self._stop,
                    silence_ms=600,
                )
                instruction = result.text if result.ok else ""

            if instruction:
                try:
                    self._on_instruction(instruction)
                except Exception:  # noqa: BLE001
                    _log.exception("wake callback error")


def _strip_wake(text: str, lang: str) -> str:
    """Remove the wake phrase from the front of a transcript."""
    low = text.lower()
    words = list(WAKE_WORDS.get(lang, ())) + list(
        WAKE_WORDS.get("he" if lang == "en" else "en", ())
    )
    for w in sorted(words, key=len, reverse=True):
        idx = low.find(w.lower())
        if idx != -1:
            return text[idx + len(w):].strip(" ,.:—-")
    return ""
