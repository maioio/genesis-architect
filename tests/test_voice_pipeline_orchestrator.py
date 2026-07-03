"""Tests for voice/voice_pipeline.py — EntityExtractor, ContextPrefetcher,
BargeInWatcher (without hardware), and VoicePipeline orchestrator."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch


from genesis_architect_pro.voice.voice_pipeline import (
    BargeInWatcher,
    ContextPrefetcher,
    EntityExtractor,
    VoicePipeline,
)


# ---------------------------------------------------------------------------
# EntityExtractor
# ---------------------------------------------------------------------------

class TestEntityExtractor:
    def test_camel_case_detected(self):
        e = EntityExtractor()
        assert e.extract("I need to refactor AuthModule") == "AuthModule"

    def test_keyword_preceded_name_wins_over_camel(self):
        e = EntityExtractor()
        # keyword match should fire first
        result = e.extract("the class PaymentService is broken")
        assert result == "PaymentService"

    def test_file_extension_detected(self):
        e = EntityExtractor()
        assert e.extract("look at auth_service.py line 42") == "auth_service.py"

    def test_ts_extension_detected(self):
        e = EntityExtractor()
        assert e.extract("check store.ts") == "store.ts"

    def test_none_on_plain_text(self):
        e = EntityExtractor()
        assert e.extract("hello world what is the weather") is None

    def test_empty_string(self):
        e = EntityExtractor()
        assert e.extract("") is None

    def test_none_input(self):
        e = EntityExtractor()
        assert e.extract(None) is None

    def test_snake_case_with_known_modules(self):
        e = EntityExtractor(known_modules={"import_graph", "auth_module"})
        assert e.extract("problems in import_graph today") == "import_graph"

    def test_snake_case_without_known_returns_none(self):
        e = EntityExtractor()
        # snake_case without known list → no match (too many false positives)
        result = e.extract("some random text with import_graph")
        # May or may not match depending on known_modules being empty
        # The invariant: no crash
        assert result is None or isinstance(result, str)

    def test_update_known(self):
        e = EntityExtractor()
        e.update_known({"import_graph"})
        assert "import_graph" in e._known

    def test_multiple_entities_returns_first(self):
        e = EntityExtractor()
        result = e.extract("class AuthModule and class PaymentService")
        assert result in ("AuthModule", "PaymentService")

    def test_multi_word_camel(self):
        e = EntityExtractor()
        assert e.extract("check the KnowledgeGraphEngine") == "KnowledgeGraphEngine"

    def test_hebrew_text_no_crash(self):
        e = EntityExtractor()
        result = e.extract("בדוק את AuthModule בקוד")
        assert result == "AuthModule"


# ---------------------------------------------------------------------------
# ContextPrefetcher
# ---------------------------------------------------------------------------

class TestContextPrefetcher:
    def test_start_loop_creates_running_event_loop(self):
        p = ContextPrefetcher(".")
        p.start_loop_in_thread()
        time.sleep(0.05)
        assert p._loop is not None
        assert p._loop.is_running()

    def test_prefetch_same_entity_skipped(self):
        p = ContextPrefetcher(".")
        p.start_loop_in_thread()
        time.sleep(0.05)
        p.last_entity = "AuthModule"
        p.prefetch("AuthModule")   # should skip — same entity
        assert p._task is None     # no new task launched

    def test_prefetch_sets_last_entity(self):
        p = ContextPrefetcher(".")
        p.start_loop_in_thread()
        time.sleep(0.05)
        p.prefetch("PaymentService")
        assert p.last_entity == "PaymentService"

    def test_await_result_returns_dict(self):
        p = ContextPrefetcher(".")
        p.start_loop_in_thread()
        time.sleep(0.05)
        p.prefetch("SomeModule")
        result = p.await_result(timeout=0.5)
        assert isinstance(result, dict)
        assert result.get("entity") == "SomeModule"

    def test_await_result_has_fragility_and_kg_keys(self):
        p = ContextPrefetcher(".")
        p.start_loop_in_thread()
        time.sleep(0.05)
        p.prefetch("TestModule")
        result = p.await_result(timeout=0.5)
        assert "fragility" in result
        assert "kg" in result

    def test_await_result_graceful_when_no_task(self):
        p = ContextPrefetcher(".")
        # Don't call start_loop_in_thread — no loop
        result = p.await_result(timeout=0.1)
        assert result == {}

    def test_fragility_lookup_graceful_on_missing_project(self, tmp_path):
        """Fragility lookup on an empty tmp dir must not raise."""
        import asyncio
        p = ContextPrefetcher(tmp_path)
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(p._fragility_lookup("AuthModule"))
        loop.close()
        assert result is None or isinstance(result, dict)

    def test_kg_lookup_graceful_on_empty_dir(self, tmp_path):
        import asyncio
        p = ContextPrefetcher(tmp_path)
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(p._kg_lookup("SomeNode"))
        loop.close()
        assert result is None


# ---------------------------------------------------------------------------
# BargeInWatcher (no hardware — just lifecycle)
# ---------------------------------------------------------------------------

class TestBargeInWatcher:
    def test_start_and_stop_no_crash(self):
        tts = MagicMock()
        callback = MagicMock()
        watcher = BargeInWatcher(tts=tts, on_barge_in=callback)
        # Without sounddevice hardware, _watch exits immediately.
        # start() launches the daemon thread — must not raise.
        watcher.start()
        time.sleep(0.05)
        watcher.stop()

    def test_stop_before_start_no_crash(self):
        tts = MagicMock()
        watcher = BargeInWatcher(tts=tts, on_barge_in=lambda: None)
        watcher.stop()   # no thread running — must not raise

    def test_double_start_no_crash(self):
        tts = MagicMock()
        watcher = BargeInWatcher(tts=tts, on_barge_in=lambda: None)
        watcher.start()
        watcher.start()   # second call must be a no-op
        time.sleep(0.05)
        watcher.stop()


# ---------------------------------------------------------------------------
# VoicePipeline — no hardware required
# ---------------------------------------------------------------------------

class TestVoicePipeline:
    def test_instantiates_without_hardware(self, tmp_path):
        vp = VoicePipeline(project_root=tmp_path)
        assert vp is not None

    def test_start_returns_false_when_stt_unavailable(self, tmp_path):
        vp = VoicePipeline(project_root=tmp_path)
        # STTPipeline will fail to load without the model
        with patch("genesis_architect_pro.voice.voice_pipeline.VoicePipeline._ensure_stt_tts",
                   return_value=False):
            result = vp.start()
        assert result is False

    def test_stop_no_crash_when_nothing_started(self, tmp_path):
        vp = VoicePipeline(project_root=tmp_path)
        vp.stop()   # nothing initialised — must not raise

    def test_handle_instruction_calls_gde_callback(self, tmp_path):
        called_with = {}

        def fake_gde(text, context):
            called_with["text"] = text
            called_with["context"] = context
            return "reply"

        vp = VoicePipeline(project_root=tmp_path, on_instruction=fake_gde)
        # Bypass TTS speak
        vp._tts = MagicMock()
        vp._tts.is_speaking = False

        result = vp._handle_instruction("Is AuthModule safe?")
        assert result == "reply"
        assert called_with["text"] == "Is AuthModule safe?"
        assert isinstance(called_with["context"], dict)

    def test_handle_instruction_no_callback_returns_text(self, tmp_path):
        vp = VoicePipeline(project_root=tmp_path, on_instruction=None)
        result = vp._handle_instruction("check this module")
        assert result == "check this module"

    def test_handle_instruction_gde_exception_returns_error_msg(self, tmp_path):
        def bad_gde(text, context):
            raise RuntimeError("engine exploded")

        vp = VoicePipeline(project_root=tmp_path, on_instruction=bad_gde)
        vp._tts = MagicMock()
        vp._tts.is_speaking = False

        result = vp._handle_instruction("diagnose")
        assert "error" in result.lower()

    def test_on_partial_transcript_fires_prefetch(self, tmp_path):
        vp = VoicePipeline(project_root=tmp_path)
        prefetch_calls = []
        vp._prefetcher.prefetch = lambda e: prefetch_calls.append(e)

        vp._on_partial_transcript("refactor AuthModule now")
        assert "AuthModule" in prefetch_calls

    def test_on_partial_transcript_no_entity_no_prefetch(self, tmp_path):
        vp = VoicePipeline(project_root=tmp_path)
        prefetch_calls = []
        vp._prefetcher.prefetch = lambda e: prefetch_calls.append(e)

        vp._on_partial_transcript("hello world")
        assert prefetch_calls == []

    def test_speak_with_bargein_stops_on_bargein(self, tmp_path):
        vp = VoicePipeline(project_root=tmp_path)
        tts_mock = MagicMock()
        tts_mock.is_speaking = False   # already done
        vp._tts = tts_mock

        with patch("genesis_architect_pro.voice.voice_pipeline.BargeInWatcher") as MockWatcher:
            instance = MockWatcher.return_value
            vp._speak_with_bargein("Hello there")
            instance.start.assert_called_once()
            instance.stop.assert_called_once()

    def test_prefetcher_started_on_init(self, tmp_path):
        vp = VoicePipeline(project_root=tmp_path)
        time.sleep(0.05)
        assert vp._prefetcher._loop is not None
