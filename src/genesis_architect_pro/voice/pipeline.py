"""Genesis Companion — Voice Pipeline (STT/TTS).

Wraps faster-whisper (STT) + Piper/MMS (TTS) with a clean interface.
All models run locally — no cloud, no API keys.

Model selection (from STT_TTS_DECISION_MATRIX.md):
  STT:  faster-whisper + ivrit-ai/faster-whisper-v2-d4  (Hebrew+English, Apache 2.0)
  TTS:  Kokoro-82M for English, Meta MMS ONNX for Hebrew, eSpeak NG fallback

Graceful degradation: if models are not installed, all methods are no-ops
and warn once. Use `genesis companion --setup` to download models.
"""

from __future__ import annotations

import logging
import os
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
    """Streaming speech-to-text using faster-whisper.

    Args:
        model_path: HuggingFace model ID or local path.
        device: 'auto' | 'cpu' | 'cuda' | 'mps'
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
        self._warned = False
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
                "Run: pip install genesis-architect-pro[voice]"
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

    def transcribe_stream(self, audio_bytes: bytes) -> Iterator[str]:
        """Transcribe streaming audio chunks. Yields partial text."""
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
# TTS
# ---------------------------------------------------------------------------

class TTSPipeline:
    """Text-to-speech with language routing.

      Hebrew → Meta MMS TTS (ONNX via sherpa-onnx)
      English → Kokoro-82M
      Fallback → eSpeak NG (always available if installed)
    """

    def __init__(self) -> None:
        self._kokoro = None
        self._mms = None
        self._espeak = None
        self._lock = threading.Lock()
        self._load_espeak()  # fast; load others lazily

    def _load_espeak(self) -> None:
        try:
            import subprocess
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
            self._kokoro = KPipeline(lang_code="a")  # American English
            _log.info("TTS: Kokoro-82M loaded (English)")
        except ImportError:
            _log.warning("Kokoro TTS not installed. Run: pip install kokoro>=0.9")
        except Exception as exc:
            _log.warning("Kokoro load error: %s", exc)

    def _load_mms(self) -> None:
        if self._mms is not None:
            return
        try:
            import sherpa_onnx  # type: ignore[import]
            mms_model = _MODELS_DIR / "mms-tts-heb.onnx"
            if mms_model.exists():
                self._mms = sherpa_onnx.OfflineTts(
                    sherpa_onnx.OfflineTtsConfig(
                        model=sherpa_onnx.OfflineTtsModelConfig(
                            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(mms_model))
                        )
                    )
                )
                _log.info("TTS: Meta MMS Hebrew loaded")
            else:
                _log.warning("Hebrew TTS model not found at %s. Run: genesis companion --setup", mms_model)
        except ImportError:
            _log.warning("sherpa-onnx not installed — Hebrew TTS unavailable.")
        except Exception as exc:
            _log.warning("MMS load error: %s", exc)

    def speak(self, text: str, urgency: Urgency = Urgency.NORMAL) -> None:
        """Synthesize and play text. Non-blocking for NORMAL; interrupts for CRITICAL."""
        if urgency == Urgency.CRITICAL:
            self._speak_sync(text)
        else:
            threading.Thread(target=self._speak_sync, args=(text,), daemon=True).start()

    def _speak_sync(self, text: str) -> None:
        lang = detect_lang(text)
        with self._lock:
            if lang == "he":
                self._load_mms()
                if self._mms:
                    self._play_mms(text)
                    return
            else:
                self._load_kokoro()
                if self._kokoro:
                    self._play_kokoro(text)
                    return
            # Fallback: eSpeak NG
            self._play_espeak(text, lang)

    def _play_kokoro(self, text: str) -> None:
        try:
            import sounddevice as sd  # type: ignore[import]
            generator = self._kokoro(text, voice="af_heart", speed=1.0)
            for _, _, audio in generator:
                sd.play(audio, samplerate=24000, blocking=True)
        except Exception as exc:
            _log.warning("Kokoro playback error: %s", exc)
            self._play_espeak(text, "en")

    def _play_mms(self, text: str) -> None:
        try:
            import sounddevice as sd  # type: ignore[import]
            import numpy as np
            audio = self._mms.generate(text, sid=0, speed=1.0)
            arr = np.array(audio.samples, dtype=np.float32)
            sd.play(arr, samplerate=audio.sample_rate, blocking=True)
        except Exception as exc:
            _log.warning("MMS playback error: %s", exc)
            self._play_espeak(text, "he")

    def _play_espeak(self, text: str, lang: str) -> None:
        if not self._espeak:
            _log.warning("TTS: no engine available for '%s'", text[:40])
            return
        try:
            import subprocess
            voice = "he" if lang == "he" else "en"
            subprocess.run(
                ["espeak-ng", "-v", voice, text],
                timeout=10,
                capture_output=True,
            )
        except Exception as exc:
            _log.warning("eSpeak error: %s", exc)


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
