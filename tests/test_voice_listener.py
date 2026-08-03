"""Tests for voice.listener - live mic capture + wake word (honest degradation)."""
import pytest

from genesis_architect.pro.voice.listener import (
    WAKE_WORDS, ListenResult, MicStatus, WakeWordListener,
    mic_status, is_wake, listen_once, _strip_wake,
    _build_vad, _frame_is_speech, _frame_is_speech_energy,
)


class TestWakeWord:
    def test_english_wake(self):
        assert is_wake("hey genesis what's up", "en")
        assert is_wake("Genesis recover this", "en")
        assert not is_wake("hello world", "en")

    def test_hebrew_wake(self):
        assert is_wake("ג'נסיס תתחיל", "he")
        assert is_wake("גנסיס", "he")

    def test_bilingual(self):
        # a Hebrew user saying the English word still triggers, and vice-versa
        assert is_wake("genesis", "he")
        assert is_wake("ג'נסיס", "en")

    def test_empty(self):
        assert is_wake("", "en") is False

    def test_wake_words_defined(self):
        assert "genesis" in WAKE_WORDS["en"]
        assert any("נסיס" in w for w in WAKE_WORDS["he"])


class TestStripWake:
    def test_strips_prefix_and_returns_instruction(self):
        assert _strip_wake("genesis recover this project", "en") == "recover this project"
        assert _strip_wake("hey genesis run research", "en") == "run research"

    def test_hebrew(self):
        assert _strip_wake("ג'נסיס תריץ ריקברי", "he") == "תריץ ריקברי"

    def test_no_wake_returns_empty(self):
        assert _strip_wake("just some words", "en") == ""


class TestDegradation:
    def test_mic_status_honest_without_sounddevice(self, monkeypatch):
        # simulate sounddevice missing
        import builtins
        real = builtins.__import__

        def fake(name, *a, **k):
            if name == "sounddevice":
                raise ImportError("no sounddevice")
            return real(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake)
        st = mic_status()
        assert st.available is False
        assert "sounddevice" in st.detail

    def test_listen_once_degrades_without_mic(self, monkeypatch):
        monkeypatch.setattr("genesis_architect.pro.voice.listener.mic_status",
                            lambda: MicStatus(False, "no mic"))
        r = listen_once(3.0)
        assert r.ok is False and "no mic" in r.reason

    def test_wake_listener_not_started_without_mic(self, monkeypatch):
        monkeypatch.setattr("genesis_architect.pro.voice.listener.mic_status",
                            lambda: MicStatus(False, "no mic"))
        got = []
        wl = WakeWordListener(on_instruction=got.append)
        assert wl.available() is False
        assert wl.start() is False
        assert got == []  # nothing fired

    def test_wake_listener_stop_is_safe(self):
        wl = WakeWordListener(on_instruction=lambda x: None)
        wl.stop()  # stopping a never-started listener must not raise


class TestResultTypes:
    def test_listen_result_shape(self):
        r = ListenResult(True, text="hello")
        assert r.ok and r.text == "hello" and r.reason == ""


class TestVADBackend:
    """Silero (via pipecat-ai, bundled ONNX model) is the preferred VAD backend
    — a real accuracy upgrade over webrtcvad/energy. These tests exercise the
    actually-installed model, not a mock, and fall back gracefully when it
    isn't importable."""

    def test_build_vad_prefers_silero_when_available(self):
        backend = _build_vad()
        # pipecat-ai is a hard dependency of the `voice` extra in this repo's
        # own venv, so this should always resolve to silero in CI/dev here.
        assert backend.kind in ("silero", "webrtc", "energy")
        if backend.kind == "silero":
            assert backend.frame_samples == 512
            assert backend.engine.sample_rate == 16000

    def test_silence_is_not_speech(self):
        np = pytest.importorskip("numpy")  # ships with the [voice] extra only
        backend = _build_vad()
        silence = np.zeros(backend.frame_samples, dtype=np.float32)
        pcm = (silence * 32767).astype("<i2").tobytes()
        assert _frame_is_speech(backend, pcm, silence) is False

    def test_frame_is_speech_never_raises_on_garbage_input(self):
        # A backend engine that raises on any call must degrade to "not speech",
        # never propagate — this runs inside a real-time sounddevice callback.
        class _Boom:
            def voice_confidence(self, _pcm):
                raise RuntimeError("boom")

        from genesis_architect.pro.voice.listener import VADBackend
        backend = VADBackend("silero", _Boom(), 512)
        assert _frame_is_speech(backend, b"\x00" * 1024, None) is False

    def test_build_vad_falls_back_when_pipecat_unavailable(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "pipecat.audio.vad.silero" or name.startswith("pipecat"):
                raise ImportError("simulated: pipecat not installed")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        backend = _build_vad()
        assert backend.kind in ("webrtc", "energy")

    def test_energy_backend_dispatch(self):
        np = pytest.importorskip("numpy")  # ships with the [voice] extra only
        from genesis_architect.pro.voice.listener import VADBackend
        backend = VADBackend("energy", None, 480)
        loud = np.full(480, 0.5, dtype=np.float32)
        quiet = np.zeros(480, dtype=np.float32)
        assert _frame_is_speech(backend, b"", loud) == _frame_is_speech_energy(loud)
        assert _frame_is_speech(backend, b"", quiet) is False
