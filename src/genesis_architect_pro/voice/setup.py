"""Genesis Companion — voice model setup + readiness check.

`genesis companion --setup` calls `run_setup()` to download the local STT/TTS
models into ``~/.genesis/models/``. Everything is local — no cloud, no API keys.

Design contract (honest by construction):
- Nothing here fabricates success. If a Python package is missing, we say exactly
  which ``pip install`` unlocks it and return a NOT-READY status — never a fake OK.
- Downloads are idempotent: an already-present model is reported as ``present`` and
  skipped, never re-fetched.
- ``readiness()`` is the single source of truth the CLI and the Customer-Readiness
  matrix rely on to decide whether voice actually works end-to-end.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger("genesis.voice.setup")

MODELS_DIR = Path.home() / ".genesis" / "models"

# STT — faster-whisper Hebrew+English (Apache 2.0)
WHISPER_MODEL_ID = "ivrit-ai/faster-whisper-v2-d4"
WHISPER_LOCAL = MODELS_DIR / "faster-whisper-v2-d4"

# Hebrew TTS — Meta MMS VITS ONNX for sherpa-onnx
MMS_HEB_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "tts-models/vits-mms-heb.tar.bz2"
)
MMS_HEB_MODEL = MODELS_DIR / "mms-tts-heb.onnx"


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


@dataclass
class ComponentStatus:
    name: str
    ready: bool
    detail: str
    fix: str = ""  # the exact command that unlocks it, if not ready


@dataclass
class VoiceReadiness:
    components: list[ComponentStatus] = field(default_factory=list)

    @property
    def stt_ready(self) -> bool:
        return any(c.name == "stt" and c.ready for c in self.components)

    @property
    def tts_english_ready(self) -> bool:
        return any(c.name == "tts_english" and c.ready for c in self.components)

    @property
    def tts_hebrew_ready(self) -> bool:
        return any(c.name == "tts_hebrew" and c.ready for c in self.components)

    @property
    def fallback_ready(self) -> bool:
        return any(c.name == "fallback" and c.ready for c in self.components)

    @property
    def end_to_end_ready(self) -> bool:
        """True only if a real round-trip works: STT + at least one real TTS voice.

        eSpeak fallback alone does NOT count as end-to-end — it is a last resort,
        not the shipped experience.
        """
        return self.stt_ready and (self.tts_english_ready or self.tts_hebrew_ready)

    def summary(self) -> str:
        if self.end_to_end_ready:
            return "Voice is ready end-to-end."
        missing = [c.name for c in self.components if not c.ready and c.name != "fallback"]
        return "Voice NOT ready. Missing: " + ", ".join(missing) if missing else \
            "Voice NOT ready."


def _pkg_available(pkg: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(pkg) is not None


def readiness() -> VoiceReadiness:
    """Inspect what is actually installed/downloaded. No side effects."""
    r = VoiceReadiness()

    # STT: needs faster-whisper package + the model on disk
    if not _pkg_available("faster_whisper"):
        r.components.append(ComponentStatus(
            "stt", False, "faster-whisper not installed",
            "pip install genesis-architect-pro[voice]"))
    elif not WHISPER_LOCAL.exists():
        r.components.append(ComponentStatus(
            "stt", False, f"model not downloaded ({WHISPER_MODEL_ID})",
            "genesis companion --setup"))
    else:
        r.components.append(ComponentStatus(
            "stt", True, f"faster-whisper + {WHISPER_MODEL_ID}"))

    # English TTS: Kokoro package (model auto-downloads on first use)
    if _pkg_available("kokoro"):
        r.components.append(ComponentStatus("tts_english", True, "Kokoro-82M"))
    else:
        r.components.append(ComponentStatus(
            "tts_english", False, "kokoro not installed",
            "pip install kokoro>=0.9 soundfile"))

    # Hebrew TTS: sherpa-onnx package + the MMS model on disk
    if not _pkg_available("sherpa_onnx"):
        r.components.append(ComponentStatus(
            "tts_hebrew", False, "sherpa-onnx not installed",
            "pip install sherpa-onnx"))
    elif not MMS_HEB_MODEL.exists():
        r.components.append(ComponentStatus(
            "tts_hebrew", False, "Hebrew MMS model not downloaded",
            "genesis companion --setup"))
    else:
        r.components.append(ComponentStatus("tts_hebrew", True, "Meta MMS Hebrew"))

    # Fallback: eSpeak NG binary on PATH
    if shutil.which("espeak-ng"):
        r.components.append(ComponentStatus("fallback", True, "eSpeak NG on PATH"))
    else:
        r.components.append(ComponentStatus(
            "fallback", False, "espeak-ng not on PATH",
            "install eSpeak NG (apt/brew/choco install espeak-ng)"))

    return r


# ---------------------------------------------------------------------------
# Setup (download)
# ---------------------------------------------------------------------------


@dataclass
class SetupResult:
    steps: list[str] = field(default_factory=list)
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def run_setup(models_dir: Path | None = None) -> SetupResult:
    """Download STT/TTS models into models_dir (default ~/.genesis/models).

    Idempotent: present models are skipped. Missing packages are reported as
    failures with the exact install command — never silently swallowed.
    """
    target = models_dir or MODELS_DIR
    target.mkdir(parents=True, exist_ok=True)
    result = SetupResult()

    whisper_local = target / WHISPER_LOCAL.name
    mms_local = target / MMS_HEB_MODEL.name

    # 1. STT model via huggingface_hub (comes with faster-whisper)
    if whisper_local.exists():
        result.skipped.append(f"STT model already present: {whisper_local.name}")
    elif not _pkg_available("faster_whisper"):
        result.failed.append(
            "STT: faster-whisper not installed — "
            "run `pip install genesis-architect-pro[voice]` then re-run --setup")
    else:
        try:
            from huggingface_hub import snapshot_download  # type: ignore[import]
            result.steps.append(f"Downloading STT model {WHISPER_MODEL_ID} …")
            snapshot_download(repo_id=WHISPER_MODEL_ID, local_dir=str(whisper_local))
            result.downloaded.append(f"STT: {WHISPER_MODEL_ID}")
        except Exception as exc:  # network, auth, disk — report honestly
            result.failed.append(f"STT download failed: {exc}")

    # 2. Hebrew MMS TTS model (sherpa-onnx release tarball)
    if mms_local.exists():
        result.skipped.append(f"Hebrew TTS model already present: {mms_local.name}")
    else:
        try:
            result.steps.append("Downloading Hebrew MMS TTS model …")
            _download_and_extract_mms(target, mms_local)
            if mms_local.exists():
                result.downloaded.append("TTS (Hebrew): Meta MMS")
            else:
                result.failed.append(
                    "Hebrew TTS: archive downloaded but model file not found after extract")
        except Exception as exc:
            result.failed.append(f"Hebrew TTS download failed: {exc}")

    # 3. English Kokoro — package downloads its own weights on first synthesis;
    #    nothing to pre-fetch, just report whether the package is importable.
    if _pkg_available("kokoro"):
        result.skipped.append("English TTS (Kokoro): package present, weights lazy-load on first use")
    else:
        result.failed.append(
            "English TTS: kokoro not installed — run `pip install kokoro>=0.9 soundfile`")

    return result


def _download_and_extract_mms(target: Path, model_out: Path) -> None:
    """Fetch the sherpa-onnx MMS Hebrew tarball and place the .onnx at model_out."""
    import tarfile
    import tempfile
    import urllib.request

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "mms-heb.tar.bz2"
        urllib.request.urlretrieve(MMS_HEB_URL, tar_path)  # noqa: S310 (fixed https URL)
        with tarfile.open(tar_path, "r:bz2") as tf:
            tf.extractall(tmp)  # noqa: S202 (trusted sherpa-onnx release)
        # Find the model.onnx inside the extracted tree and copy it out.
        for onnx in Path(tmp).rglob("*.onnx"):
            shutil.copy(onnx, model_out)
            break
