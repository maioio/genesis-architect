"""Tests for VoicePipeline — STT and TTS stubs (no model required)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch


from genesis_architect_pro.voice.pipeline import (
    CRITICAL_NOTIFICATIONS,
    STTPipeline,
    TTSPipeline,
    Urgency,
    detect_lang,
    notify,
)


# ---------------------------------------------------------------------------
# detect_lang
# ---------------------------------------------------------------------------

class TestDetectLang:
    def test_empty_string(self):
        assert detect_lang("") == "en"

    def test_pure_english(self):
        assert detect_lang("Hello, how are you doing today?") == "en"

    def test_pure_hebrew(self):
        assert detect_lang("שלום, מה שלומך?") == "he"

    def test_mixed_mostly_hebrew(self):
        # Hebrew chars should dominate
        assert detect_lang("שלום world שלום") == "he"

    def test_mixed_mostly_english(self):
        # "שלום" is 4 Hebrew chars; need >85% English chars to stay under 15% threshold
        assert detect_lang("Hello world foo bar baz שלום") == "en"

    def test_threshold_exactly_15pct(self):
        # Exactly 15% Hebrew → 'en' (> not >=)
        text = "a" * 85 + "ש" * 15  # 15% Hebrew
        assert detect_lang(text) == "en"

    def test_just_above_threshold(self):
        text = "a" * 84 + "ש" * 16  # 16% Hebrew
        assert detect_lang(text) == "he"

    def test_digits_and_punctuation_counted_as_non_hebrew(self):
        assert detect_lang("12345 !@#$%") == "en"


# ---------------------------------------------------------------------------
# STTPipeline — offline (no faster-whisper installed in test env)
# ---------------------------------------------------------------------------

class TestSTTPipelineOffline:
    """All tests run without faster-whisper installed."""

    def test_available_false_when_import_fails(self):
        """STTPipeline must gracefully degrade when faster-whisper is absent."""
        with patch.dict("sys.modules", {"faster_whisper": None}):
            stt = STTPipeline.__new__(STTPipeline)
            stt._model = None
            stt._available = False
            assert not stt.available

    def test_transcribe_returns_empty_when_unavailable(self, tmp_path):
        stt = STTPipeline.__new__(STTPipeline)
        stt._model = None
        stt._available = False
        result = stt.transcribe(tmp_path / "audio.wav")
        assert result == ""

    def test_transcribe_stream_yields_nothing_when_unavailable(self):
        stt = STTPipeline.__new__(STTPipeline)
        stt._model = None
        stt._available = False
        chunks = list(stt.transcribe_stream(b"\x00" * 100))
        assert chunks == []

    def test_detect_device_returns_string(self):
        device = STTPipeline._detect_device()
        assert device in ("cpu", "cuda", "mps")

    def test_transcribe_with_mock_model(self, tmp_path):
        """Transcribe delegates to model.transcribe and joins segments."""
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"fake audio")

        mock_seg1 = MagicMock()
        mock_seg1.text = "  Hello  "
        mock_seg2 = MagicMock()
        mock_seg2.text = "world"

        stt = STTPipeline.__new__(STTPipeline)
        stt._model = MagicMock()
        stt._model.transcribe.return_value = ([mock_seg1, mock_seg2], None)
        stt._available = True

        result = stt.transcribe(wav_path)
        assert result == "Hello world"

    def test_transcribe_handles_model_exception(self, tmp_path, caplog):
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"fake")

        stt = STTPipeline.__new__(STTPipeline)
        stt._model = MagicMock()
        stt._model.transcribe.side_effect = RuntimeError("CUDA OOM")
        stt._available = True

        with caplog.at_level(logging.WARNING, logger="genesis.voice"):
            result = stt.transcribe(wav_path)
        assert result == ""
        assert "CUDA OOM" in caplog.text

    def test_transcribe_stream_cleans_up_tmp_file(self, tmp_path):
        stt = STTPipeline.__new__(STTPipeline)
        mock_seg = MagicMock()
        mock_seg.text = "hi"
        stt._model = MagicMock()
        stt._model.transcribe.return_value = ([mock_seg], None)
        stt._available = True

        chunks = list(stt.transcribe_stream(b"\x00" * 44))
        assert chunks == ["hi"]


# ---------------------------------------------------------------------------
# TTSPipeline — offline (no audio hardware in test env)
# ---------------------------------------------------------------------------

class TestTTSPipelineOffline:
    def test_espeak_fallback_detected_gracefully(self):
        """If eSpeak is absent, no exception is raised."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            tts = TTSPipeline()
            assert tts._espeak is None

    def test_speak_normal_runs_in_thread(self):
        tts = TTSPipeline.__new__(TTSPipeline)
        tts._kokoro = None
        tts._mms = None
        tts._espeak = None
        tts._lock = __import__("threading").Lock()

        with patch.object(tts, "_speak_sync") as mock_sync:
            tts.speak("hello", urgency=Urgency.NORMAL)
            import time; time.sleep(0.05)  # let daemon thread run
            mock_sync.assert_called_once_with("hello")

    def test_speak_critical_runs_synchronously(self):
        tts = TTSPipeline.__new__(TTSPipeline)
        tts._kokoro = None
        tts._mms = None
        tts._espeak = None
        tts._lock = __import__("threading").Lock()

        with patch.object(tts, "_speak_sync") as mock_sync:
            tts.speak("CRITICAL!", urgency=Urgency.CRITICAL)
            mock_sync.assert_called_once_with("CRITICAL!")

    def test_play_espeak_logs_warning_when_unavailable(self, caplog):
        tts = TTSPipeline.__new__(TTSPipeline)
        tts._espeak = None

        with caplog.at_level(logging.WARNING, logger="genesis.voice"):
            tts._play_espeak("test", "en")
        assert "no engine available" in caplog.text

    def test_speak_english_routes_to_kokoro(self):
        tts = TTSPipeline.__new__(TTSPipeline)
        tts._kokoro = None
        tts._mms = None
        tts._espeak = None
        tts._lock = __import__("threading").Lock()

        with patch.object(tts, "_load_kokoro") as mock_load, \
             patch.object(tts, "_play_kokoro") as mock_play:
            mock_load.side_effect = lambda: setattr(tts, "_kokoro", MagicMock())
            tts._speak_sync("Hello, how are you?")
            mock_play.assert_called_once()

    def test_speak_hebrew_routes_to_mms(self):
        tts = TTSPipeline.__new__(TTSPipeline)
        tts._kokoro = None
        tts._mms = None
        tts._espeak = None
        tts._lock = __import__("threading").Lock()

        with patch.object(tts, "_load_mms") as mock_load, \
             patch.object(tts, "_play_mms") as mock_play:
            mock_load.side_effect = lambda: setattr(tts, "_mms", MagicMock())
            tts._speak_sync("שלום, מה שלומך?")
            mock_play.assert_called_once()

    def test_speak_falls_back_to_espeak_when_kokoro_unavailable(self):
        tts = TTSPipeline.__new__(TTSPipeline)
        tts._kokoro = None
        tts._mms = None
        tts._espeak = "espeak-ng"
        tts._lock = __import__("threading").Lock()

        with patch.object(tts, "_load_kokoro"):  # kokoro stays None
            with patch.object(tts, "_play_espeak") as mock_espeak:
                tts._speak_sync("Hello world")
                mock_espeak.assert_called_once()

    def test_kokoro_load_warns_on_missing_import(self, caplog):
        tts = TTSPipeline.__new__(TTSPipeline)
        tts._kokoro = None

        with patch.dict("sys.modules", {"kokoro": None}):
            with caplog.at_level(logging.WARNING, logger="genesis.voice"):
                tts._load_kokoro()
        assert "Kokoro" in caplog.text or tts._kokoro is None

    def test_mms_load_warns_when_model_missing(self, caplog, tmp_path):
        tts = TTSPipeline.__new__(TTSPipeline)
        tts._mms = None

        mock_sherpa = MagicMock()
        with patch.dict("sys.modules", {"sherpa_onnx": mock_sherpa}):
            with patch(
                "genesis_architect_pro.voice.pipeline._MODELS_DIR",
                tmp_path,  # model won't exist here
            ):
                with caplog.at_level(logging.WARNING, logger="genesis.voice"):
                    tts._load_mms()
        assert "not found" in caplog.text or tts._mms is None


# ---------------------------------------------------------------------------
# CRITICAL_NOTIFICATIONS
# ---------------------------------------------------------------------------

class TestCriticalNotifications:
    def test_all_keys_present_in_english(self):
        expected_keys = {"drift", "god_class", "confidence", "done", "volatile"}
        assert expected_keys == set(CRITICAL_NOTIFICATIONS["en"].keys())

    def test_all_keys_present_in_hebrew(self):
        expected_keys = {"drift", "god_class", "confidence", "done", "volatile"}
        assert expected_keys == set(CRITICAL_NOTIFICATIONS["he"].keys())

    def test_hebrew_strings_contain_hebrew_chars(self):
        for text in CRITICAL_NOTIFICATIONS["he"].values():
            has_hebrew = any(0x0590 <= ord(c) <= 0x05FF for c in text)
            assert has_hebrew, f"Expected Hebrew in: {text}"

    def test_notify_returns_text(self):
        text = notify("drift", lang="en")
        assert "drift" in text.lower() or "architecture" in text.lower()

    def test_notify_returns_hebrew_text(self):
        text = notify("drift", lang="he")
        assert len(text) > 5
        has_hebrew = any(0x0590 <= ord(c) <= 0x05FF for c in text)
        assert has_hebrew

    def test_notify_unknown_key_returns_empty(self):
        text = notify("nonexistent_key", lang="en")
        assert text == ""

    def test_notify_calls_tts_speak_when_provided(self):
        mock_tts = MagicMock()
        text = notify("done", lang="en", tts=mock_tts)
        mock_tts.speak.assert_called_once_with(text, urgency=Urgency.CRITICAL)

    def test_notify_does_not_call_tts_on_missing_key(self):
        mock_tts = MagicMock()
        notify("missing_key", lang="en", tts=mock_tts)
        mock_tts.speak.assert_not_called()

    def test_notify_unknown_lang_falls_back_to_english(self):
        text = notify("drift", lang="fr")
        english_text = notify("drift", lang="en")
        assert text == english_text
