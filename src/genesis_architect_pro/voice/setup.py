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

# Hebrew TTS — Meta MMS VITS ONNX for sherpa-onnx.
# The k2-fsa tts-models release has no Hebrew asset; this HF repo carries the
# sherpa-exported ONNX + tokens. NOTE: MMS weights are CC-BY-NC-4.0.
MMS_HEB_FILES = {
    "model.onnx": "https://huggingface.co/thewh1teagle/mms-tts-heb/resolve/main/model_sherpa.onnx",
    "tokens.txt": "https://huggingface.co/thewh1teagle/mms-tts-heb/resolve/main/tokens.txt",
}
MMS_HEB_MODEL = MODELS_DIR / "mms-tts-heb.onnx"      # legacy single-file layout
MMS_HEB_DIR = MODELS_DIR / "vits-mms-heb"            # full layout (model + tokens)

# English TTS fallback — Piper VITS for sherpa-onnx. Kokoro requires
# Python <3.13 (its spacy dependency has no wheels beyond that), so on
# newer Pythons English speech runs through sherpa-onnx instead.
PIPER_EN_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "tts-models/vits-piper-en_US-amy-low.tar.bz2"
)
PIPER_EN_DIR = MODELS_DIR / "vits-piper-en_US-amy-low"


def mms_heb_ready() -> bool:
    return (MMS_HEB_DIR / "model.onnx").exists() or MMS_HEB_MODEL.exists()


def piper_en_ready() -> bool:
    return any(PIPER_EN_DIR.glob("*.onnx")) if PIPER_EN_DIR.exists() else False


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

    # English TTS: Kokoro when installable (Python <3.13); otherwise the
    # Piper VITS model through sherpa-onnx.
    if _pkg_available("kokoro"):
        r.components.append(ComponentStatus("tts_english", True, "Kokoro-82M"))
    elif _pkg_available("sherpa_onnx") and piper_en_ready():
        r.components.append(ComponentStatus("tts_english", True, "Piper en_US (sherpa-onnx)"))
    elif _pkg_available("sherpa_onnx"):
        r.components.append(ComponentStatus(
            "tts_english", False, "English Piper model not downloaded",
            "genesis companion --setup"))
    else:
        r.components.append(ComponentStatus(
            "tts_english", False, "kokoro / sherpa-onnx not installed",
            "pip install sherpa-onnx soundfile"))

    # Hebrew TTS: sherpa-onnx package + the MMS model on disk
    if not _pkg_available("sherpa_onnx"):
        r.components.append(ComponentStatus(
            "tts_hebrew", False, "sherpa-onnx not installed",
            "pip install sherpa-onnx"))
    elif not mms_heb_ready():
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
# Package auto-provision (one-command premium install)
# ---------------------------------------------------------------------------

# import name -> pip requirement. Everything the full Companion experience
# needs beyond the base install. webrtcvad-wheels ships prebuilt wheels for
# every platform (plain webrtcvad is sdist-only and fails without a compiler)
# and exposes the same `webrtcvad` module.
COMPANION_PACKAGES: dict[str, str] = {
    "rich": "rich>=13",
    "plyer": "plyer>=2.1",
    "websockets": "websockets>=12",
    "numpy": "numpy>=1.24",
    "sounddevice": "sounddevice>=0.4",
    "webrtcvad": "webrtcvad-wheels>=2.0.10",
    "faster_whisper": "faster-whisper>=1.0",
    "soundfile": "soundfile>=0.12",
    # kokoro >=0.8 pins Python <3.13; 0.7.x is the newest that installs everywhere.
    "kokoro": "kokoro>=0.7",
    "sherpa_onnx": "sherpa-onnx>=1.10",
}


@dataclass
class ProvisionResult:
    installed: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def missing_companion_packages() -> list[str]:
    """Pip requirement strings for Companion packages not importable right now."""
    return [req for mod, req in COMPANION_PACKAGES.items()
            if not _pkg_available(mod)]


def ensure_companion_packages(*, progress=None) -> ProvisionResult:
    """Install any missing Companion packages into the current environment.

    This is what makes `pip install genesis-architect-pro` a one-command
    install: the first `genesis companion --ui` pulls the rest automatically.
    Never raises — failures are reported per requirement with pip's own error.
    """
    import subprocess
    import sys

    result = ProvisionResult()
    result.already_present = [req for mod, req in COMPANION_PACKAGES.items()
                              if _pkg_available(mod)]
    missing = missing_companion_packages()
    if not missing:
        return result

    if progress:
        progress(f"Installing {len(missing)} missing package(s): "
                 + ", ".join(m.split(">=")[0] for m in missing))
    try:
        # encoding+errors are required: pip emits UTF-8, but text=True would
        # otherwise decode with the OS locale (cp1252 on Windows) and crash on
        # any non-Latin-1 byte in pip's progress/output.
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1800,
        )
        if proc.returncode == 0:
            result.installed = missing
        else:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            result.failed = [f"{' '.join(missing)} — pip exited "
                             f"{proc.returncode}: {' / '.join(tail)}"]
    except Exception as exc:
        result.failed = [f"{' '.join(missing)} — {exc}"]

    # Verify by import, not by pip exit code alone.
    if result.installed:
        import importlib
        importlib.invalidate_caches()
        still_missing = missing_companion_packages()
        if still_missing:
            result.failed.extend(still_missing)
            result.installed = [r for r in result.installed
                                if r not in still_missing]
    return result


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

    # 2. Hebrew MMS TTS model — direct files from HF (model.onnx + tokens.txt;
    #    sherpa needs both, so they live together in one dir).
    mms_dir = target / MMS_HEB_DIR.name
    if (mms_dir / "model.onnx").exists():
        result.skipped.append(f"Hebrew TTS model already present: {mms_dir.name}")
    else:
        import urllib.request
        try:
            result.steps.append("Downloading Hebrew MMS TTS model …")
            mms_dir.mkdir(parents=True, exist_ok=True)
            for fname, url in MMS_HEB_FILES.items():
                urllib.request.urlretrieve(url, mms_dir / fname)  # noqa: S310 (fixed https URLs)
            if (mms_dir / "model.onnx").exists():
                result.downloaded.append("TTS (Hebrew): Meta MMS")
            else:
                result.failed.append(
                    "Hebrew TTS: download finished but model file missing")
        except Exception as exc:
            result.failed.append(f"Hebrew TTS download failed: {exc}")

    # 3. English TTS. Kokoro when importable (Python <3.13); otherwise the
    #    Piper VITS model through sherpa-onnx — same engine as Hebrew.
    if _pkg_available("kokoro"):
        result.skipped.append("English TTS (Kokoro): package present, weights lazy-load on first use")
    else:
        piper_dir = target / PIPER_EN_DIR.name
        if any(piper_dir.glob("*.onnx")) if piper_dir.exists() else False:
            result.skipped.append(f"English TTS model already present: {piper_dir.name}")
        elif not _pkg_available("sherpa_onnx"):
            result.failed.append(
                "English TTS: neither kokoro nor sherpa-onnx installed — "
                "run `pip install sherpa-onnx soundfile`")
        else:
            try:
                result.steps.append("Downloading English Piper TTS model …")
                _download_and_extract_tts(PIPER_EN_URL, target, piper_dir.name)
                if any(piper_dir.glob("*.onnx")):
                    result.downloaded.append("TTS (English): Piper en_US via sherpa-onnx")
                else:
                    result.failed.append(
                        "English TTS: archive downloaded but model file not found after extract")
            except Exception as exc:
                result.failed.append(f"English TTS download failed: {exc}")

    return result


def _download_and_extract_tts(url: str, target: Path, dir_name: str) -> None:
    """Fetch a sherpa-onnx TTS tarball and extract its model dir into target/dir_name.

    The k2-fsa release tarballs contain a single top-level directory named like
    the archive; the whole tree (model.onnx, tokens.txt, data dirs) is kept —
    sherpa needs more than just the .onnx.
    """
    import tarfile
    import tempfile
    import urllib.request

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "tts-model.tar.bz2"
        urllib.request.urlretrieve(url, tar_path)  # noqa: S310 (fixed https URL)
        with tarfile.open(tar_path, "r:bz2") as tf:
            tf.extractall(tmp)  # noqa: S202 (trusted sherpa-onnx release)
        extracted = [p for p in Path(tmp).iterdir() if p.is_dir()]
        if not extracted:
            return
        dest = target / dir_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(extracted[0]), str(dest))
