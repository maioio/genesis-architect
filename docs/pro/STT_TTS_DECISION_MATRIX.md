# STT/TTS Decision Matrix — Genesis PRO Companion Voice Layer

> **Research date:** 2026-07-01  
> **Scope:** Local-first, privacy-safe, Hebrew + English, low-latency  
> **Sources:** Whisper benchmarks (Picovoice, PromptQuorum, Northflank), ivrit.ai Hebrew research,
> WhisperPipe arXiv 2604.25611, OpenWakeWord docs, MMS Hugging Face, sherpa-onnx TTS docs.

---

## STT Decision Matrix

| Model | Latency | Hebrew Quality | Size | License | Streaming | Verdict |
|-------|---------|---------------|------|---------|-----------|---------|
| **faster-whisper + ivrit.ai v2-d4** | 200–300ms (streaming, GPU); ~1s CPU | **Excellent** — 350h Hebrew training (crowd + professional); best open WER | large-v2: 3GB; v3-turbo: 1.5GB | Apache 2.0 | ✅ via whisper_streaming / WhisperPipe | ✅ **PRIMARY PICK** |
| **whisper.cpp** | 0.5–3s (model-dependent); Metal/CUDA/BLAS | Good — base multilingual; can convert ivrit.ai weights | small: 460MB; large: 3GB | MIT | ✅ (stream example) | ✅ Fallback for C++ embedding |
| **WhisperPipe / whisper_streaming** | **229ms** end-to-commit (GPU) | Inherits base model — use with ivrit.ai | No extra size (wrapper) | MIT | ✅ Native design | ✅ Streaming layer on top of faster-whisper |
| **Moonshine v2** | Sub-200ms CPU; 5× faster than Whisper large-v3 | ❌ No Hebrew (8 languages, HE absent) | 26MB–245MB | Apache 2.0 | ✅ | ❌ Hebrew blocker |
| **vosk** | 50–100ms first word | ❌ No Hebrew model exists | ~50MB | Apache 2.0 | ✅ | ❌ No Hebrew |
| **Meta MMS ASR** | Slow — batch PyTorch, no streaming | ⚠️ Hebrew covered but Biblical-corpus only (narrow domain) | ~1GB | CC-BY-NC 4.0 | ❌ | ⚠️ Last resort only |

### Wake Word Detection

| Model | Detection Latency | Hebrew Phrases | Size | License | Notes |
|-------|------------------|---------------|------|---------|-------|
| **OpenWakeWord** | ~80ms (per audio frame) | ⚠️ Requires custom ONNX model training with Hebrew TTS synthetic data | 5–20MB per model | Apache 2.0 | Train "ג'נסיס תתחיל" via Hebrew TTS → OpenWakeWord trainer |

**STT Recommendation:**  
Use `faster-whisper` with **ivrit.ai `faster-whisper-v2-d4`** weights as the primary engine —
the only combination delivering production-quality Hebrew ASR + streaming + Python bindings +
Apache 2.0. Wrap with `whisper_streaming` (229ms end-to-commit on GPU). For wake word,
train a custom OpenWakeWord ONNX model using Meta MMS TTS-generated Hebrew synthetic audio.

---

## TTS Decision Matrix

| Model | Latency (short phrase) | Hebrew | Size | License | Streaming | Verdict |
|-------|----------------------|--------|------|---------|-----------|---------|
| **Meta MMS TTS → ONNX (sherpa-onnx)** | ~700ms Python; ~500ms ONNX | ✅ 1,107 languages including Hebrew | ~500MB base + adapter | CC-BY-NC 4.0 | ❌ | ✅ **PRIMARY for Hebrew** (only viable option) |
| **Kokoro TTS (82M)** | **Sub-300ms CPU** | ❌ No Hebrew (EN/ES/FR/HI/IT/JA/PT/ZH) | ~330MB | Apache 2.0 | ⚠️ Partial | ✅ **PRIMARY for English** |
| **Piper TTS** | Sub-100ms CPU | ❌ No Hebrew (~30 European languages) | 30–60MB/voice | MIT / GPL-3.0 (active fork) | ❌ | ✅ English fallback; watch GPL-3.0 on active fork |
| **eSpeak NG** | Sub-50ms | ✅ Hebrew phoneme support | <10MB | GPL-3.0 | ✅ | ✅ Zero-latency fallback + system alerts |
| **Coqui XTTS-v2** | 1–3s (GPU) | ❌ No Hebrew | ~1.8GB | Coqui Public (non-commercial) | ⚠️ | ❌ No Hebrew + no commercial license |
| **Bark** | 5–30s CPU | ❌ | ~5GB | MIT | ❌ | ❌ Too slow |
| **F5-TTS** | ~300ms (GPU) | ❌ | ~900MB | CC-BY-NC (weights) | ❌ | ❌ No Hebrew |

**TTS Recommendation:**  
Route by detected output language: **Hebrew → Meta MMS TTS (ONNX via sherpa-onnx)**,
**English → Kokoro-82M** (Apache 2.0, sub-300ms, natural quality). Use **eSpeak NG** as
zero-latency fallback for UI feedback sounds and sub-3-word system alerts. Accept that
Hebrew TTS quality is functional rather than natural — no better option exists locally.

---

## Implementation Plan

```python
class VoicePipeline:
    def __init__(self, license: LicenseTier):
        # STT: always faster-whisper + ivrit.ai weights
        self.stt = FasterWhisperSTT(
            model_path="ivrit-ai/faster-whisper-v2-d4",
            device="auto",   # CUDA → MPS → CPU
            streaming=True,
        )
        # Wake word: custom ONNX (Hebrew + English phrases)
        self.wakeword = OpenWakeWordDetector(
            models=["genesis_start_en.onnx", "genesis_start_he.onnx"],
            threshold=0.7,
        )
        # TTS: language-routed
        self.tts_he = MMSTTSOnnx(lang="heb")    # Hebrew
        self.tts_en = KokoroTTS(voice="en_US-lessac-medium")  # English
        self.tts_fallback = ESpeakNG()           # <50ms alerts
    
    def speak(self, text: str, urgency: Urgency = Urgency.NORMAL):
        lang = detect_lang(text)
        engine = self.tts_he if lang == "he" else self.tts_en
        if urgency == Urgency.CRITICAL:
            self._interrupt_and_play(self.tts_fallback.synthesize(text))
        else:
            self._queue(engine.synthesize(text))
```

---

## Model Download Sizes & First-Run UX

| Component | Download | Notes |
|-----------|----------|-------|
| faster-whisper v2-d4 (ivrit) | ~1.5 GB | One-time; cached in `~/.genesis/models/` |
| OpenWakeWord custom model | ~10 MB | Bundled with Companion installer |
| Meta MMS TTS (Hebrew) | ~500 MB | Downloaded on first Hebrew TTS use |
| Kokoro-82M (English) | ~330 MB | Downloaded on first English TTS use |
| **Total first-run** | **~2.3 GB** | Progressive: STT first, TTS on first use |

`genesis companion --setup` runs the download + verification with a progress bar.
All models stored in `~/.genesis/models/`; `genesis companion --offline` verifies they exist.
