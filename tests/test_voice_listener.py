"""Tests for voice.listener - live mic capture + wake word (honest degradation)."""
from genesis_architect_pro.voice.listener import (
    WAKE_WORDS, ListenResult, MicStatus, WakeWordListener,
    mic_status, is_wake, listen_once, _strip_wake,
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
        monkeypatch.setattr("genesis_architect_pro.voice.listener.mic_status",
                            lambda: MicStatus(False, "no mic"))
        r = listen_once(3.0)
        assert r.ok is False and "no mic" in r.reason

    def test_wake_listener_not_started_without_mic(self, monkeypatch):
        monkeypatch.setattr("genesis_architect_pro.voice.listener.mic_status",
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
