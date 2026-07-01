# Genesis PRO Companion — Architecture Specification

> **Status:** Architecture design (implementation pending). Extends and supersedes
> where it overlaps with `FLOATING_ASSISTANT_SPEC.md`.
>
> **One sentence:** Genesis PRO Companion is a proactive, voice-capable, IDE-aware
> engineering partner that surfaces the full GDE + Committee intelligence as a
> standalone application — talking to the user in their language, watching their
> code in real time, and never committing a byte without a visual diff approval.

---

## 1. Committee Engine — Core Primitive

### 1.1 Current state
The Committee engine exists as a GDE mode (`COMMITTEE`) with 5 wired engines:
import_graph → architecture_scorer → antipattern_detector → fragility_classifier →
committee_analysis. It synthesizes multi-perspective findings and detects divergence.

**The problem:** Committee is currently a GDE *mode*, not a *primitive*. It cannot
be invoked mid-session by other modes, and its output is not routed back into the
GDE confidence model.

### 1.2 Committee as a first-class primitive

Promote `committee_analysis` to a callable primitive available in **every mode**:

```python
class CommitteeEngine:
    """
    Multi-perspective synthesis primitive. Callable from any GDE mode.
    Not a mode — a capability that any mode can invoke.
    """
    def run(self, ctx: SessionContext, perspectives: list[EngineResult]) -> CommitteeReport:
        ...
```

**Routing rule:** The GDE calls Committee automatically when:
- Session confidence drops below 0.55 mid-execution
- Two required engines return divergent scores (>0.25 delta)
- The user instruction contains ambiguity signals

### 1.3 Transparency Profiles

| Profile | What the user sees | What Committee does |
|---------|-------------------|---------------------|
| **Genesis Free** | Final recommendation only ("Use approach A") | Full discussion hidden |
| **Genesis PRO** | Full discussion panel: all perspectives, divergence map, voting record, confidence per engine | Streamed live into Companion side panel |

Implementation: `CommitteeReport` carries a `full_record: list[Perspective]` and a
`summary: str`. Free exposes only `summary`. Pro exposes `full_record` streamed via
WebSocket to the Companion panel.

```python
@dataclass
class CommitteeReport:
    summary: str                        # always available
    recommendation: str                 # always available
    full_record: list[Perspective]      # Pro only
    divergence_zones: list[str]         # Pro only
    confidence: float
    consensus_reached: bool
```

### 1.4 GDE routing — version-aware

```python
def _should_run_committee(ctx: SessionContext, report: SessionReport) -> bool:
    if report.overall_confidence < 0.55:
        return True
    if _has_divergence(report.engine_results):
        return True
    return False

def _committee_output(report: CommitteeReport, license_tier: str) -> dict:
    if license_tier == "pro":
        return dataclasses.asdict(report)
    return {"summary": report.summary, "recommendation": report.recommendation}
```

---

## 2. Application Shell — Standalone

### 2.1 Technology decision

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Tauri v2 (Rust + WebView)** | Native perf, small binary (~8MB), OS integration, always-on-top, global hotkeys, tray icon, IPC to Python | Rust build toolchain | ✅ **Selected** |
| Electron | Familiar | 150MB+ binary, high RAM | ❌ |
| PyQt6 | Pure Python | Limited WebView, ugly on Mac | ❌ |
| Web-only (browser) | Zero install | No global hotkeys, no tray, no IDE read | ❌ for companion (keep for Canvas) |

### 2.2 Process architecture

```
┌─────────────────────────────────────────────────┐
│              Tauri Shell (Rust)                  │
│  - Window management (bubble / panel / canvas)  │
│  - Global hotkey listener                       │
│  - System tray                                  │
│  - Always-on-top enforcement                    │
│  - IPC bridge                                   │
└──────────────┬──────────────────────────────────┘
               │ WebView (localhost:3000)
               │ Tauri IPC commands
               ▼
┌─────────────────────────────────────────────────┐
│           React Frontend (Vite + TS)            │
│  - Bubble / Panel / Canvas surfaces             │
│  - WebSocket client → GDE stream               │
│  - Visual diff viewer                           │
│  - RTL/LTR switcher                             │
│  - Committee panel (Pro)                        │
└──────────────┬──────────────────────────────────┘
               │ WebSocket (port 8765)
               ▼
┌─────────────────────────────────────────────────┐
│        Genesis PRO Server (Python)              │
│  - GenesisDecisionEngine                        │
│  - CommitteeEngine primitive                    │
│  - VoiceOrchestrator                            │
│  - IDEContextBridge                             │
│  - WebSocket server (asyncio)                   │
└─────────────────────────────────────────────────┘
```

### 2.3 Technical roadmap

**Phase 0 — Foundation (weeks 1–2)**
- Tauri v2 project scaffolded with Python sidecar
- WebSocket server in `genesis_architect_pro/companion_server.py`
- Bubble renders, draggable, snaps to edge
- Global hotkey registered (Push-to-talk)
- GDE session streamed to panel in real time

**Phase 1 — Voice (weeks 3–5)**
- STT pipeline: microphone → VAD → Whisper.cpp (local)
- TTS pipeline: text → Kokoro/Piper (local)
- Hebrew/English language detection + switching
- Push-to-talk + wake-word ("Genesis, start" / "ג'נסיס, תתחיל")
- Critical alert vocalizations

**Phase 2 — IDE Bridge (weeks 6–8)**
- LSP-style read-only sidecar for VS Code / JetBrains
- Line-level context: active file + cursor position → IDEContextBridge
- Pattern detection on active file (God Class, etc.) → proactive notification
- "Run Committee on this?" prompt on critical pattern

**Phase 3 — Visual Diff + Commit (weeks 9–10)**
- Diff viewer in Canvas surface (unified diff, syntax-highlighted)
- Approval: APPROVE / REQUEST CHANGES / DENY
- On approval: GDE commit() called atomically
- Committee full record streamed to panel (Pro)

**Phase 4 — Polish (weeks 11–12)**
- Multi-monitor position persistence
- Activity levels: Quiet / Balanced / Active / Expert
- WCAG 2.2 AA accessibility
- Onboarding flow

---

## 3. Voice & Interaction Layer

### 3.1 Dual-trigger model

```
Trigger 1: Push-to-talk (PTT)
  - Global hotkey: Alt+Space (configurable)
  - Hold to speak, release to send
  - Visual indicator: bubble pulses while recording

Trigger 2: Wake word
  - Always-on VAD (Voice Activity Detection)
  - Wake phrases: "Genesis, start" / "ג'נסיס, תתחיל"
  - Supported: English, Hebrew, Arabic, French, Spanish, German
  - Privacy: VAD runs local (Silero VAD), no audio sent until wake word confirmed
```

### 3.2 STT/TTS Decision Matrix

#### STT (Speech-to-Text)

| Model | Hebrew | English | Latency | Privacy | License | Decision |
|-------|--------|---------|---------|---------|---------|----------|
| **Whisper.cpp (large-v3-turbo)** | Excellent | Excellent | ~300ms (GPU) / ~800ms (CPU) | 100% local | MIT | ✅ Primary |
| Whisper.cpp (medium) | Good | Excellent | ~200ms | 100% local | MIT | ✅ Fallback (low-end hardware) |
| OpenAI Whisper API | Excellent | Excellent | ~400ms (network) | Cloud | Paid | ⚠️ Optional cloud fallback |
| Azure Speech | Good | Excellent | ~300ms | Cloud | Paid | ❌ vendor lock |
| Google STT | Poor Hebrew | Excellent | ~250ms | Cloud | Paid | ❌ Hebrew quality |

**Recommendation:** Whisper.cpp large-v3-turbo via llama.cpp server. Ships as an
optional dependency: `pip install genesis-architect-pro[voice]` downloads the model
once (1.5GB). Falls back to `medium` on hardware with <4GB VRAM.

#### TTS (Text-to-Speech)

| Model | Hebrew | English | Latency | Voice quality | License | Decision |
|-------|--------|---------|---------|---------------|---------|----------|
| **Kokoro-82M** | No | Excellent | ~50ms | Studio quality | Apache 2.0 | ✅ English TTS |
| **Piper TTS (he_IL)** | Yes | Good | ~80ms | Good | MIT | ✅ Hebrew TTS |
| Coqui XTTS-v2 | Via finetune | Excellent | ~200ms | Excellent | CPML | ⚠️ Backup |
| ElevenLabs API | Yes | Excellent | ~300ms net | Best | Paid | ❌ cloud-only |
| Azure Neural TTS | Yes (he-IL) | Excellent | ~200ms net | Excellent | Paid | ⚠️ Opt-in cloud |

**Recommendation:** Kokoro for English (fastest, highest quality) + Piper he_IL for
Hebrew. Auto-switch by detected language. Voice selection configurable in settings.

### 3.3 Streaming pipeline

```
Microphone (16kHz, mono)
  → Silero VAD (local, ~5ms)  — gate: only forward speech frames
  → Whisper.cpp server (local WebSocket)
  → Transcript text
  → GDE intent_classifier (sub-ms)
  → GDE.run() → streaming results via asyncio.Queue
  → WebSocket → Companion panel (word-by-word streaming)
  → Kokoro/Piper TTS → PCM audio → speaker
```

Latency budget (GPU path):
- VAD: 5ms
- STT: 300ms
- GDE classify: <1ms
- First token to panel: <350ms
- TTS first chunk: <100ms after text arrives
- **Total to first audio:** ~500ms

### 3.4 RTL/LTR handling

The Companion detects the active language (from STT transcript or user input) and
switches layout dynamically:

```typescript
const direction = detectLanguage(text) === 'he' ? 'rtl' : 'ltr';
document.documentElement.setAttribute('dir', direction);
```

All panel text elements use `logical` CSS properties (`margin-inline-start`, etc.)
so layout mirrors correctly. The bubble itself is direction-neutral (icon only).

### 3.5 Proactive voice notifications

Critical alerts are vocalized automatically (no PTT needed):

```python
VOCALIZE_GATES = {
    GateStatus.HARD_BLOCK: "Critical gate triggered — {gate_name}. Action required.",
    "drift_critical": "Critical architecture drift detected in {module}.",
    "volatile_module": "Volatile module detected: {name}. Committee analysis recommended.",
}
```

Alert level configurable: Off / Warnings only / All (default: Warnings only).

---

## 4. IDE Context Bridge

### 4.1 Architecture

The IDE Bridge is a **read-only** sidecar — it never writes to the IDE, only reads:

```
VS Code Extension (TypeScript)
  - Listens for: active file change, cursor move, save event
  - Sends: { file_path, cursor_line, file_content_hash, language }
  - Transport: Local Unix socket / named pipe (platform-specific)
  - Never sends: full file content (only hash + metadata)

JetBrains Plugin (Kotlin)
  - Same contract, same transport
  - IntelliJ Platform SDK: FileEditorManagerListener
```

Full file content is only fetched when the user explicitly says "analyze this file"
or a pattern is detected and the user accepts the "Run Committee on this?" prompt.

### 4.2 Line-level pattern detection

```python
class IDEContextBridge:
    def on_cursor_move(self, file_path: str, line: int):
        # Load the import graph for this file if cached
        node = self._graph.get_node(file_path)
        if node and node.fan_out > 15:
            self._notify("God Class pattern detected — this file imports 15+ modules. "
                         "Run Committee analysis?")

    def on_file_save(self, file_path: str):
        # Check if this file is VOLATILE in the fragility map
        fragility = self._fragility_map.get(file_path)
        if fragility == "VOLATILE":
            self._notify(f"Saved a VOLATILE module: {Path(file_path).name}. "
                         "Fragility risk. Run recovery scan?")
```

Notifications appear as non-blocking corner toasts (3s auto-dismiss, action button).

### 4.3 Context Engine (Scryer-style)

When the GDE needs codebase context for an LLM call, the Context Engine fetches
only high-relevance snippets from the Knowledge Graph — not the whole file:

```python
class ContextEngine:
    def fetch_relevant(self, instruction: str, max_tokens: int = 4000) -> list[Snippet]:
        # 1. Parse instruction for file/function references
        # 2. Query knowledge graph: find nodes within 2 hops of mentioned entities
        # 3. Score by relevance (BM25 over docstrings + node labels)
        # 4. Trim to max_tokens, prioritizing high-confidence edges
        ...
```

This is the "Scryer-style" context awareness: the LLM sees only what matters,
token budget managed by the graph, not by blind chunking.

---

## 5. Visual Diff Approval

All GDE write operations are presented as a visual diff before commit:

```
┌─────────────────────────────────────────────────────────────┐
│  Pending writes — RECOVERY session  (confidence: 0.82)      │
├─────────────────────────────────────────────────────────────┤
│  FRAGILITY_MAP.md         +47 / -3 lines      [modified]    │
│  PROJECT_RECOVERY_REPORT.md  +124 lines       [new file]    │
│  .genesis/score_history.jsonl  +1 line        [append]      │
├──────────────────┬──────────────────┬───────────────────────┤
│  [APPROVE ALL]   │  [APPROVE SOME]  │       [DENY]          │
└──────────────────┴──────────────────┴───────────────────────┘
```

"Approve Some" opens a file-by-file checklist. Only approved operations are passed
to `gde.commit()`. The GDE atomic write guarantee (tmp → rename) remains.

---

## 6. STT/TTS Summary — Final Recommendation

| Component | Choice | Reason |
|-----------|--------|--------|
| Wake word / VAD | Silero VAD | Local, MIT, 5ms latency |
| STT — primary | Whisper.cpp large-v3-turbo | Hebrew+English best-in-class local |
| STT — low-end fallback | Whisper.cpp medium | 4× faster, still good quality |
| STT — cloud opt-in | OpenAI Whisper API | For users without local GPU |
| TTS — English | Kokoro-82M | 50ms, studio quality, Apache 2.0 |
| TTS — Hebrew | Piper he_IL | 80ms, MIT, good quality |
| TTS — cloud opt-in | Azure he-IL Neural | For users needing best Hebrew voice |
| Language detection | langdetect + script heuristic | Hebrew script = he, else detect |

Install path:
```bash
pip install genesis-architect-pro[voice]   # downloads Whisper + Piper + Kokoro
```
Models download once to `~/.genesis/models/`. No server, no Docker.

---

## 7. Open questions (to be decided with Reddit/field research)

1. **Wake word sensitivity:** developers who work in noisy environments — how
   critical is PTT vs wake-word? (Reddit research pending)
2. **Hebrew voice quality bar:** is Piper he_IL good enough or will users
   immediately switch to cloud? (Field data pending)
3. **IDE bridge permission model:** VS Code extension requires user install — is
   that acceptable friction? (Field data pending)
4. **Activity levels:** what is "Quiet" to a professional developer — no audio,
   or no proactive notifications at all? (Reddit research pending)

*Question 4 will be updated when Reddit Answers research completes.*

---

---

## 8. Instagram Reel Research — Vercel AI SDK 7 Voice Gateway

> **Source:** instagram.com/reel/DaOKXPogqku — creator: `eliron.giny` (June 30, 2026)

**What was demonstrated:** Vercel's AI Gateway (AI SDK 7, beta) now supports a
single model receiving audio and returning audio — eliminating the manual STT →
LLM → TTS wiring. Supported at launch: OpenAI + xAI voice models.

**Key capabilities highlighted:**
- Automatic end-of-speech detection (no manual VAD configuration)
- Barge-in handling (mutes mid-sentence on interruption)
- Mid-conversation tool calls (action triggers during generation)
- No browser-exposed API keys (gateway proxies all calls)

**Skeptic note (comment in reel):** This is an abstraction layer, not complexity
elimination — the three failure points (STT, LLM, TTS) still exist inside Vercel.
You are trading orchestration control for convenience.

**Verdict for Genesis Companion:**

| Aspect | Assessment |
|--------|-----------|
| Barge-in + tool calls | High-value. Required for natural dev companion UX |
| Vercel gateway dependency | Rejected — Genesis uses local-first architecture |
| Architecture inspiration | Valuable. Single-pipeline audio model is the right UX goal |
| Local equivalent | Whisper.cpp → GDE → Kokoro/Piper achieves the same single-pipeline feel, fully local |
| Claude voice support | Not yet in Vercel gateway. When it ships, evaluate as cloud opt-in |

**Decision:** Genesis implements the same *UX pattern* (audio in → audio out,
barge-in, tool calls mid-conversation) but through the local Whisper + Kokoro/Piper
stack, not the Vercel gateway. The gateway approach is noted as a future opt-in for
users who prefer cloud and already use Vercel.

---

*Created: 2026-07-01 | Genesis Architect PRO v6.4.0 | Status: Architecture design*
*See also: `FLOATING_ASSISTANT_SPEC.md` (UX), `PHASE_v2_CLOSURE.md` (v2 scope)*
