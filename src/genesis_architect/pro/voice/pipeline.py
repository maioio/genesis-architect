"""Genesis Companion — Voice Pipeline (STT/TTS).

Wraps faster-whisper (STT) + Kokoro/MMS/eSpeak (TTS) with a clean interface.
All models run locally — no cloud, no API keys.

Model selection (from STT_TTS_DECISION_MATRIX.md):
  STT:  faster-whisper + ivrit-ai/faster-whisper-v2-d4  (Hebrew+English, Apache 2.0)
  TTS:  Kokoro-82M for English, Meta MMS ONNX for Hebrew, eSpeak NG fallback

New in this version:
  - TTSPipeline.stop() — cancels any active playback immediately via a shared
    threading.Event cancel token. All three play methods (_play_kokoro,
    _play_sherpa, _play_espeak) check the token between chunks/sentences.
  - Full-duplex design: the cancel token is set externally (by VoicePipeline)
    when VAD detects new speech onset during playback (barge-in).
  - Blocking playback is replaced by a chunk-by-chunk loop that checks the
    token after each audio chunk, so interruption latency is ≤ one chunk
    (~100ms for Kokoro, one espeak sentence for eSpeak).

Graceful degradation: if models are not installed, all methods are no-ops
and warn once. Use `genesis companion --setup` to download models.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from enum import Enum
from pathlib import Path
from typing import Iterator

_log = logging.getLogger("genesis.voice")

_MODELS_DIR = Path.home() / ".genesis" / "models"
_WHISPER_MODEL = "ivrit-ai/faster-whisper-v2-d4"
_WHISPER_LOCAL = _MODELS_DIR / "faster-whisper-v2-d4"

HEBREW_CODEPOINT_RANGE = range(0x0590, 0x05FF)


class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    BACKGROUND = "background"


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_lang(text: str) -> str:
    """Return 'he' if >15% of chars are Hebrew, else 'en'."""
    if not text:
        return "en"
    hebrew = sum(1 for c in text if ord(c) in HEBREW_CODEPOINT_RANGE)
    return "he" if hebrew / len(text) > 0.15 else "en"


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

class STTPipeline:
    """Speech-to-text using faster-whisper.

    Accepts both file paths and numpy float32 arrays. Using arrays avoids
    writing temp WAV files to disk for every utterance.
    """

    def __init__(
        self,
        model_path: str = _WHISPER_MODEL,
        device: str = "auto",
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._model = None
        self._available = False
        self._load()

    def _load(self) -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import]
            device = self._device
            if device == "auto":
                device = self._detect_device()
            self._model = WhisperModel(
                str(self._model_path),
                device=device,
                compute_type="int8",
            )
            self._available = True
            _log.info("STT: faster-whisper loaded on %s", device)
        except ImportError:
            _log.warning(
                "STT unavailable: faster-whisper not installed. "
                "Run: pip install genesis-architect[voice]"
            )
        except Exception as exc:
            _log.warning("STT unavailable: %s", exc)

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch  # type: ignore[import]
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    @property
    def available(self) -> bool:
        return self._available

    def transcribe(self, audio_path: str | Path) -> str:
        """Transcribe a WAV/MP3 file. Returns plain text."""
        if not self._available:
            return ""
        try:
            segments, _ = self._model.transcribe(str(audio_path), vad_filter=True)
            return " ".join(s.text.strip() for s in segments)
        except Exception as exc:
            _log.warning("STT transcribe error: %s", exc)
            return ""

    def transcribe_array(self, audio) -> str:
        """Transcribe a numpy float32 array. No temp file written."""
        if not self._available or audio is None:
            return ""
        try:
            import numpy as np
            arr = np.asarray(audio, dtype=np.float32)
            if arr.ndim > 1:
                arr = arr.reshape(-1)
            if arr.size == 0:
                return ""
            segments, _ = self._model.transcribe(arr, vad_filter=True)
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:
            _log.warning("STT transcribe_array error: %s", exc)
            return ""

    def transcribe_stream(self, audio_bytes: bytes) -> Iterator[str]:
        """Transcribe streaming audio chunks. Yields partial text.
        Uses a temp file because the bytes path is for streaming ingest only.
        """
        if not self._available:
            return
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name
        try:
            text = self.transcribe(tmp)
            if text:
                yield text
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# TTS — with barge-in support
# ---------------------------------------------------------------------------

class TTSPipeline:
    """Text-to-speech with language routing and barge-in cancel support.

      Hebrew → Meta MMS TTS (ONNX via sherpa-onnx)
      English → Kokoro-82M
      Fallback → eSpeak NG (always available if installed)

    Barge-in: call stop() from any thread to cancel the current utterance.
    All play methods check self._cancel between audio chunks, so interruption
    latency is bounded by chunk size (≤100ms for Kokoro, ≤1 sentence for eSpeak).
    """

    def __init__(self) -> None:
        self._kokoro = None
        self._mms = None
        self._piper = None
        self._espeak = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()   # set → stop playback ASAP
        self._playing = threading.Event()  # set while audio is playing
        self._load_espeak()

    # -- setup ---------------------------------------------------------------

    def _load_espeak(self) -> None:
        try:
            result = subprocess.run(
                ["espeak-ng", "--version"], capture_output=True, timeout=3
            )
            if result.returncode == 0:
                self._espeak = "espeak-ng"
                _log.info("TTS fallback: eSpeak NG available")
        except Exception:
            pass

    def _load_kokoro(self) -> None:
        if self._kokoro is not None:
            return
        try:
            from kokoro import KPipeline  # type: ignore[import]
            self._kokoro = KPipeline(lang_code="a")
            _log.info("TTS: Kokoro-82M loaded (English)")
        except ImportError:
            # Expected on Python >=3.13 (kokoro's spacy dep has no wheels there);
            # English falls through to Piper via sherpa-onnx.
            _log.debug("Kokoro not installed — using Piper English fallback")
        except Exception as exc:
            _log.warning("Kokoro load error: %s", exc)

    @staticmethod
    def _sherpa_vits(model: "Path", tokens: "Path | None",
                     data_dir: "Path | None" = None):
        """Build a sherpa-onnx OfflineTts for a VITS model directory."""
        import sherpa_onnx  # type: ignore[import]
        vits_kwargs = {"model": str(model)}
        if tokens is not None and tokens.exists():
            vits_kwargs["tokens"] = str(tokens)
        if data_dir is not None and data_dir.exists():
            vits_kwargs["data_dir"] = str(data_dir)
        return sherpa_onnx.OfflineTts(
            sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(**vits_kwargs)
                )
            )
        )

    def _load_mms(self) -> None:
        if self._mms is not None:
            return
        try:
            mms_dir = _MODELS_DIR / "vits-mms-heb"
            legacy = _MODELS_DIR / "mms-tts-heb.onnx"
            if (mms_dir / "model.onnx").exists():
                self._mms = self._sherpa_vits(mms_dir / "model.onnx",
                                              mms_dir / "tokens.txt")
                _log.info("TTS: Meta MMS Hebrew loaded")
            elif legacy.exists():  # pre-7.2 layout (onnx only, no tokens)
                self._mms = self._sherpa_vits(legacy, None)
                _log.info("TTS: Meta MMS Hebrew loaded (legacy layout)")
            else:
                _log.warning(
                    "Hebrew TTS model not found at %s. "
                    "Run: genesis companion --setup", mms_dir
                )
        except ImportError:
            _log.warning("sherpa-onnx not installed — Hebrew TTS unavailable.")
        except Exception as exc:
            _log.warning("MMS load error: %s", exc)

    def _load_piper_en(self) -> None:
        """English VITS through sherpa-onnx — the path taken when Kokoro is
        not installable (its spacy dependency has no wheels on Python >=3.13)."""
        if self._piper is not None:
            return
        try:
            piper_dir = _MODELS_DIR / "vits-piper-en_US-amy-low"
            onnx = next(iter(piper_dir.glob("*.onnx")), None) if piper_dir.exists() else None
            if onnx is None:
                _log.warning(
                    "English Piper model not found at %s. "
                    "Run: genesis companion --setup", piper_dir
                )
                return
            self._piper = self._sherpa_vits(onnx, piper_dir / "tokens.txt",
                                            piper_dir / "espeak-ng-data")
            _log.info("TTS: Piper en_US loaded (sherpa-onnx)")
        except ImportError:
            _log.warning("sherpa-onnx not installed — English Piper TTS unavailable.")
        except Exception as exc:
            _log.warning("Piper load error: %s", exc)

    # -- public API ----------------------------------------------------------

    def speak(self, text: str, urgency: Urgency = Urgency.NORMAL) -> None:
        """Synthesize and play text. Non-blocking except for CRITICAL urgency."""
        self._cancel.clear()
        if urgency == Urgency.CRITICAL:
            self._speak_sync(text)
        else:
            threading.Thread(
                target=self._speak_sync, args=(text,), daemon=True
            ).start()

    def stop(self) -> None:
        """Cancel any active playback immediately (barge-in entry point).

        Sets the cancel token; the current play method sees it between chunks
        and stops. Also calls sounddevice.stop() as a hard cutoff.
        """
        self._cancel.set()
        try:
            import sounddevice as sd  # type: ignore[import]
            sd.stop()
        except Exception:
            pass
        # Give the play thread a moment to exit cleanly
        self._playing.wait(timeout=0.15)

    @property
    def is_speaking(self) -> bool:
        return self._playing.is_set()

    # -- internal playback ---------------------------------------------------

    def _speak_sync(self, text: str) -> None:
        lang = detect_lang(text)
        self._playing.set()
        try:
            with self._lock:
                if self._cancel.is_set():
                    return
                if lang == "he":
                    self._load_mms()
                    if self._mms:
                        self._play_sherpa(self._mms, text)
                        return
                else:
                    self._load_kokoro()
                    if self._kokoro:
                        self._play_kokoro(text)
                        return
                    self._load_piper_en()
                    if self._piper:
                        self._play_sherpa(self._piper, text)
                        return
                self._play_espeak(text, lang)
        finally:
            self._playing.clear()

    def _play_kokoro(self, text: str) -> None:
        """Play Kokoro TTS audio chunk-by-chunk; checks cancel between chunks."""
        try:
            import sounddevice as sd  # type: ignore[import]

            generator = self._kokoro(text, voice="af_heart", speed=1.0)
            for _, _, audio in generator:
                if self._cancel.is_set():
                    sd.stop()
                    return
                # Non-blocking play + wait so we can re-check cancel after each chunk
                sd.play(audio, samplerate=24000, blocking=False)
                # Wait for this chunk to finish, checking cancel every 50ms
                chunk_dur = len(audio) / 24000
                elapsed = 0.0
                while elapsed < chunk_dur:
                    if self._cancel.is_set():
                        sd.stop()
                        return
                    time_slice = min(0.05, chunk_dur - elapsed)
                    threading.Event().wait(time_slice)
                    elapsed += time_slice
        except Exception as exc:
            _log.warning("Kokoro playback error: %s", exc)
            if not self._cancel.is_set():
                self._play_espeak(text, "en")

    def _play_sherpa(self, tts, text: str) -> None:
        """Play sherpa-onnx VITS audio (MMS Hebrew / Piper English);
        checks cancel before and during playback."""
        try:
            import sounddevice as sd  # type: ignore[import]
            import numpy as np

            if self._cancel.is_set():
                return
            audio = tts.generate(text, sid=0, speed=1.0)
            arr = np.array(audio.samples, dtype=np.float32)
            if self._cancel.is_set():
                return
            # Split into ~200ms chunks so cancel is responsive
            sr = audio.sample_rate
            chunk_size = sr // 5  # 200ms
            for start in range(0, len(arr), chunk_size):
                if self._cancel.is_set():
                    sd.stop()
                    return
                chunk = arr[start:start + chunk_size]
                sd.play(chunk, samplerate=sr, blocking=True)
        except Exception as exc:
            _log.warning("sherpa TTS playback error: %s", exc)
            if not self._cancel.is_set():
                self._play_espeak(text, detect_lang(text))

    def _play_espeak(self, text: str, lang: str) -> None:
        """Play via eSpeak NG; cancellable between sentences."""
        if not self._espeak:
            _log.warning("TTS: no engine available for '%s'", text[:40])
            return
        voice = "he" if lang == "he" else "en"
        # Split on sentence boundaries for per-sentence cancellation
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text.strip()) or [text]
        for sentence in sentences:
            if self._cancel.is_set():
                return
            try:
                subprocess.run(
                    ["espeak-ng", "-v", voice, sentence],
                    timeout=10,
                    capture_output=True,
                )
            except Exception as exc:
                _log.warning("eSpeak error: %s", exc)
                return


# ---------------------------------------------------------------------------
# Proactive notification phrases
# ---------------------------------------------------------------------------

CRITICAL_NOTIFICATIONS = {
    "en": {
        "drift":      "Critical architecture drift detected — approval required",
        "god_class":  "God Class pattern detected — run Committee analysis?",
        "confidence": "Session confidence dropped — check the panel",
        "done":       "Genesis task complete — changes staged for approval",
        "volatile":   "Volatile module detected — high risk of regression",
    },
    "he": {
        "drift":      "זוהה סחף ארכיטקטורי קריטי — נדרש אישור",
        "god_class":  "זוהה תבנית God Class — להריץ ניתוח Committee?",
        "confidence": "רמת הביטחון ירדה — בדוק את הפאנל",
        "done":       "משימת Genesis הסתיימה — שינויים ממתינים לאישור",
        "volatile":   "מודול תנודתי זוהה — סיכון גבוה לרגרסיה",
    },
}


def notify(key: str, lang: str = "en", tts: TTSPipeline | None = None) -> str:
    """Return the notification text for key/lang and optionally speak it."""
    text = CRITICAL_NOTIFICATIONS.get(lang, CRITICAL_NOTIFICATIONS["en"]).get(key, "")
    if text and tts:
        tts.speak(text, urgency=Urgency.CRITICAL)
    return text
