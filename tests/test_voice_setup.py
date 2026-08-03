"""Tests for the voice setup / readiness module.

These verify the honesty contract: readiness never fabricates success, reports
the exact fix for each missing component, and end_to_end_ready is True only when
a real round-trip is genuinely possible.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from genesis_architect.pro.voice import setup as vsetup
from genesis_architect.pro.voice import readiness, run_setup, VoiceReadiness


# ---------------------------------------------------------------------------
# readiness()
# ---------------------------------------------------------------------------


def _pkg_map(**present: bool):
    """Return a fake _pkg_available that answers from `present` (default False)."""
    def fake(pkg: str) -> bool:
        return present.get(pkg, False)
    return fake


def test_readiness_returns_all_components():
    r = readiness()
    names = {c.name for c in r.components}
    assert names == {"stt", "tts_english", "tts_hebrew", "fallback"}


def test_readiness_missing_everything_gives_fixes():
    with patch.object(vsetup, "_pkg_available", _pkg_map()), \
         patch.object(vsetup.shutil, "which", return_value=None):
        r = readiness()
    assert not r.end_to_end_ready
    # every not-ready component (except fallback) carries a fix command
    for c in r.components:
        if not c.ready and c.name != "fallback":
            assert c.fix, f"{c.name} should carry a fix"


def test_readiness_stt_needs_both_package_and_model():
    # package present but model file missing → still not ready, fix points to --setup
    with patch.object(vsetup, "_pkg_available", _pkg_map(faster_whisper=True)), \
         patch.object(Path, "exists", return_value=False):
        r = readiness()
    stt = next(c for c in r.components if c.name == "stt")
    assert not stt.ready
    assert "--setup" in stt.fix


def test_end_to_end_requires_stt_plus_real_tts():
    # STT ready + Kokoro ready → end-to-end True (fallback irrelevant)
    with patch.object(vsetup, "_pkg_available",
                      _pkg_map(faster_whisper=True, kokoro=True)), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(vsetup.shutil, "which", return_value=None):
        r = readiness()
    assert r.stt_ready
    assert r.tts_english_ready
    assert r.end_to_end_ready


def test_espeak_fallback_alone_is_not_end_to_end():
    # only eSpeak present → NOT end-to-end (fallback is a last resort, not the feature)
    with patch.object(vsetup, "_pkg_available", _pkg_map()), \
         patch.object(vsetup.shutil, "which", return_value="/usr/bin/espeak-ng"):
        r = readiness()
    assert r.fallback_ready
    assert not r.end_to_end_ready


# ---------------------------------------------------------------------------
# run_setup()
# ---------------------------------------------------------------------------


def test_setup_reports_failure_when_package_missing(tmp_path):
    with patch.object(vsetup, "_pkg_available", _pkg_map()):
        result = run_setup(models_dir=tmp_path)
    assert not result.ok
    # honest: names the missing STT package and the install command
    assert any("faster-whisper" in f for f in result.failed)


def test_setup_skips_present_models(tmp_path):
    # pre-create both model artifacts so setup treats them as present
    (tmp_path / vsetup.WHISPER_LOCAL.name).mkdir()
    (tmp_path / vsetup.MMS_HEB_MODEL.name).write_text("fake onnx")
    with patch.object(vsetup, "_pkg_available",
                      _pkg_map(faster_whisper=True, kokoro=True)):
        result = run_setup(models_dir=tmp_path)
    assert any("already present" in s for s in result.skipped)
    # nothing re-downloaded for the present ones
    assert not any("STT:" in d for d in result.downloaded)


def test_setup_result_ok_property():
    r = vsetup.SetupResult()
    assert r.ok
    r.failed.append("boom")
    assert not r.ok


def test_readiness_summary_is_honest():
    r = VoiceReadiness()
    # empty → not ready
    assert "NOT ready" in r.summary()
