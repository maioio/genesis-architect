# Genesis PRO Companion — Standalone Application Architecture

> **Status:** Architecture specification — v1.0 | 2026-07-01  
> **Builds on:** `docs/pro/FLOATING_ASSISTANT_SPEC.md` (UX/window spec)  
> **This document:** Technical implementation architecture, shell, bridges, voice layer, streaming.

---

## 0. North Star

The Companion is the interaction surface the Floating Assistant spec describes — but this document
answers **how it is built**: the application shell, the bridge to IDEs, the voice pipeline,
the WebSocket streaming layer, and the diff-approval flow. The UX posture (bubble → panel → Canvas,
activity levels, notification tiers) is defined in FLOATING_ASSISTANT_SPEC.md and is **not
repeated here**.

**Single constraint:** no setup beyond `pip install genesis-architect-pro[companion]`.
No Node, no Docker, no Rust toolchain required by the user. The Companion runs as a native
desktop application compiled from Python.

---

## 1. Application Shell

### 1.1 Technology Choice

**Tauri v2** is the desktop shell.

Rationale:
- Ships a ~3–8 MB binary; Electron adds 150–200 MB.
- Python → sidecar pattern: the Genesis Core (`genesis_architect_pro`) runs as a Python sidecar
  process, managed by Tauri. The UI is a lightweight React + Vite frontend.
- Tauri's `always_on_top`, `skip_taskbar`, window transparency, and per-monitor position APIs
  all exist and are stable in v2.
- The existing Canvas (`ui_workspace.py`) is a self-contained HTML artifact — it renders in the
  same WebView, no port required.

**Alternative considered and rejected:** PyQt6/PySide6 (heavier, cross-platform inconsistencies
on Windows HiDPI; weaker WebView for Canvas). tkinter (no alpha compositing). CEF (400 MB).

### 1.2 Process Architecture

```
OS
├─ genesis-companion.exe          (Tauri shell — minimal, ~6 MB)
│   ├─ WebView2 / WKWebView       (UI: React + Vite frontend)
│   │   ├─ Bubble component
│   │   ├─ Panel component  
│   │   ├─ Canvas (loads ui_workspace.html)
│   │   └─ Diff Approval view
│   └─ Tauri commands (IPC)       (bridge to sidecar)
│
└─ genesis-core (sidecar)         (Python process, always-running)
    ├─ GenesisDecisionEngine       (existing GDE)
    ├─ All 13 engines              (existing)
    ├─ Committee engine            (new — COMMITTEE_ENGINE_ARCHITECTURE.md)
    ├─ VoicePipeline               (new — §3)
    ├─ IDEBridge                   (new — §4)
    ├─ WebSocket server            (new — localhost:47291, §2)
    └─ Streaming event emitter     (new — §2.3)
```

The WebView communicates to the sidecar exclusively via:
1. Tauri IPC commands (sync, for state queries)
2. WebSocket (async, for streaming events)

---

## 2. WebSocket Streaming Layer

### 2.1 Protocol

Port: `47291` (genesis-companion reserved).
Protocol: JSON-framed messages over `ws://localhost:47291/stream`.
Auth: session token handshake on connect (prevents rogue page from connecting).

```typescript
// Message envelope
interface StreamMessage {
  id: string;           // message UUID
  type: MessageType;    // see §2.2
  ts: number;           // unix ms
  session_id: string;   // GDE session
  payload: unknown;     // type-specific
}
```

### 2.2 Message Types

| Type | Direction | Payload |
|------|-----------|---------|
| `engine.start` | sidecar → UI | `{engine, phase, total_phases}` |
| `engine.progress` | sidecar → UI | `{engine, pct, current_op}` |
| `engine.done` | sidecar → UI | `{engine, confidence, result_summary}` |
| `engine.failed` | sidecar → UI | `{engine, error, confidence_penalty}` |
| `gate.fired` | sidecar → UI | `{gate_name, type, overridable}` |
| `gate.approval_required` | sidecar → UI | `{gate_name, description, diff_preview}` |
| `session.confidence` | sidecar → UI | `{confidence, risk_level}` |
| `committee.advisor_round` | sidecar → UI | PRO only: `{advisor, position, confidence}` |
| `committee.synthesis` | sidecar → UI | `{verdict, consensus_type, minority_view}` |
| `voice.transcript` | sidecar → UI | `{text, lang, confidence, is_final}` |
| `voice.tts_chunk` | sidecar → UI | `{audio_b64, seq}` (PCM chunk) |
| `ide.line_event` | sidecar → UI | `{file, line, pattern, suggestion}` |
| `diff.ready` | sidecar → UI | `{diff_id, files_changed, preview_html}` |
| `user.intent` | UI → sidecar | `{text, voice_input}` |
| `user.approval` | UI → sidecar | `{session_id, choice: APPROVE|REJECT|MODIFY}` |
| `user.voice_start` | UI → sidecar | `{}` (push-to-talk begin) |
| `user.voice_end` | UI → sidecar | `{}` (push-to-talk end) |

### 2.3 Streaming Architecture

```
[user speaks / types]
        │
        ▼
   UI → WebSocket → VoicePipeline.transcribe()     (STT, streaming tokens)
                          │
                          ▼
                   GDE.run(intent)                  (streaming engine events)
                          │
                    ┌─────┴──────────────────────┐
                    │  engine.start/progress/done  │ → WebSocket → UI bubble/panel
                    │  gate.fired / approval       │ → WebSocket → UI (approval card)
                    │  committee.* events          │ → WebSocket → UI (Committee panel)
                    └─────────────────────────────┘
                          │
                   GDE.approve(report)
                          │
                   diff.ready event                 → WebSocket → Diff Approval view
                          │
                   [user approves in Canvas]
                          │
                   GDE.commit(report, decision)     → atomic writes to disk
```

**RTL/LTR handling:** Every text payload carries a `lang` field. The UI switches text direction
(`dir="rtl"` for Hebrew, `dir="ltr"` for English) per message, not per session. A single
conversation can mix RTL and LTR turns.

---

## 3. Voice & Interaction Layer

### 3.1 Dual-Trigger Model

Two independent paths to voice activation:

**Path A — Push-to-Talk (PTT)**
- Global keyboard shortcut: `Ctrl+Shift+G` (configurable)
- Registers OS-level hotkey via Tauri's `global-shortcut` plugin
- On press: UI → `user.voice_start` → STT begins streaming
- On release: UI → `user.voice_end` → STT finalizes → intent sent to GDE
- Visual: bubble pulses red ring while holding

**Path B — Wake Word ("Genesis, start" / "ג'נסיס, תתחיל")**
- Always-on microphone listener at minimal CPU (OpenWakeWord — 2–5 MB model)
- Wake phrase detected → same flow as PTT release
- Multilingual: English and Hebrew phrases both registered
- Privacy: wake word model runs fully locally; audio never buffered beyond the detection window
- User can disable per-project or globally; status shown in bubble

### 3.2 STT Pipeline

```python
class STTPipeline:
    def __init__(self):
        self.wakeword = OpenWakeWordDetector(
            phrases=["genesis start", "genesis help", "ג'נסיס תתחיל"],
            threshold=0.7
        )
        self.transcriber = FasterWhisper(
            model="medium",              # 1.5 GB; best Hebrew/English tradeoff
            device="cpu",               # fallback; auto-detects CUDA/MPS
            language=None,              # auto-detect per utterance
            beam_size=5,
            vad_filter=True,
        )
    
    def stream(self, audio_source: AudioSource) -> Iterator[TranscriptChunk]:
        for chunk in audio_source.stream():
            if self.wakeword.detect(chunk):
                yield TranscriptChunk(type="wakeword", text="", is_final=False)
            for segment in self.transcriber.transcribe_stream(chunk):
                yield TranscriptChunk(
                    type="transcript",
                    text=segment.text,
                    lang=segment.language,
                    confidence=segment.avg_logprob,
                    is_final=segment.no_speech_prob < 0.3
                )
```

**Model selection:** `faster-whisper medium` — 1.5 GB on disk, 300–800ms latency per utterance
on CPU, <100ms on GPU. Hebrew quality: Whisper medium covers 98 languages including Hebrew
(he) at production grade. Auto-language detection handles mid-conversation switching.

### 3.3 TTS Pipeline (Proactive Notifications)

```python
class TTSPipeline:
    def __init__(self):
        self.engine = Piper(
            model="en_US-lessac-medium",     # English
            hebrew_model="he_IL-*-medium",   # Hebrew (if available in Piper catalog)
        )
    
    def speak(self, text: str, lang: str = "auto", urgency: Urgency = Urgency.NORMAL):
        if urgency == Urgency.CRITICAL:
            self._interrupt_current()
        audio = self.engine.synthesize(text, lang=lang)
        self._play(audio)                    # non-blocking; queued for NORMAL urgency
```

**Critical notifications voiced:**
- "Critical architecture drift detected — approval required"
- "God class pattern on line [N] — run Committee analysis?"
- "Session confidence dropped to [X]% — check the panel"
- "Genesis task complete — [N] files staged for approval"

**Volume:** respects OS focus-assist / do-not-disturb state; silent if suppressed.

### 3.4 Language Detection & RTL Switching

```python
HEBREW_RANGE = range(0x0590, 0x05FF)

def detect_lang(text: str) -> str:
    hebrew_chars = sum(1 for c in text if ord(c) in HEBREW_RANGE)
    return "he" if hebrew_chars / max(len(text), 1) > 0.15 else "en"
```

UI receives `lang` on every `voice.transcript` message and sets layout direction immediately.

---

## 4. IDE Bridge — Line-Level Awareness

### 4.1 Architecture

The IDE Bridge provides **read-only** awareness of what the developer is looking at.
It never writes to or modifies the IDE. It never sends file contents off-machine.

```
IDE (VS Code / JetBrains / Neovim)
        │
        │  [Extension / Plugin — lightweight]
        │  Reports: active file path + cursor line number + open file list
        │  Transport: HTTP POST to localhost:47292/ide-event  (local only)
        ▼
genesis-core (IDEBridge)
        │
        ├─ Maps (file, line) → engine data
        │    via Import Graph + Anti-Pattern data + Fragility Map (in-memory index)
        │
        ├─ Emits ide.line_event → WebSocket → Companion UI
        │
        └─ Companion shows: contextual suggestion in panel strip
```

### 4.2 VS Code Extension (MVP)

A minimal VS Code extension (~100 lines):

```typescript
// genesis-companion-vscode/src/extension.ts
import * as vscode from 'vscode';
import axios from 'axios';

export function activate(ctx: vscode.ExtensionContext) {
    vscode.window.onDidChangeTextEditorSelection(async (e) => {
        const file = e.textEditor.document.fileName;
        const line = e.selections[0].active.line + 1;
        await axios.post('http://localhost:47292/ide-event', { file, line, event: 'cursor' })
            .catch(() => {});  // silent if companion not running
    });
}
```

**Data sent:** only `{file_path, line_number, event_type}`. Never file contents.

### 4.3 Line-Level Pattern Matching

```python
class IDEBridge:
    def __init__(self, engine_index: EngineIndex):
        self.index = engine_index   # pre-built from last GDE run
    
    def handle_event(self, file: str, line: int) -> IDELineEvent | None:
        patterns = self.index.query(file=file, line=line)
        if not patterns:
            return None
        
        top = patterns[0]
        return IDELineEvent(
            file=file,
            line=line,
            pattern=top.type,          # e.g. "GOD_CLASS", "CIRCULAR_DEP", "HIGH_CHURN"
            severity=top.severity,
            suggestion=top.suggestion,
            action="run_committee" if top.severity == Severity.CRITICAL else "explain",
        )
```

**What gets surfaced:**
| Pattern detected | Line-level hint |
|-----------------|----------------|
| GOD_CLASS | "Line N: God Class — this file imports 18 modules. Run Committee analysis?" |
| CIRCULAR_DEP | "Line N: Part of circular dependency chain. View in Canvas?" |
| FRAGILE (VOLATILE) | "Line N: VOLATILE module — high churn, no test coverage. See fragility map?" |
| HIGH_CVE_RISK | "Line N: Package has open CVE (via Knowledge Graph). View security report?" |
| DEAD_CODE | "Line N: No importers detected — potential dead code." |

**Rate limiting:** max 1 event per 3 seconds per file; suppressed while user is actively typing.

### 4.4 Visual Diff Approval

When `diff.ready` fires over WebSocket, the Companion opens the **Diff Approval view** in Canvas:

```
┌─────────────────────────────────────────────────────────────┐
│  Genesis — Pending Changes (3 files)                        │
│  Confidence: 0.82  |  Gate: WRITE_SCOPE (soft)             │
├─────────────────────────────────────────────────────────────┤
│  src/auth/AuthModule.py     (+47 / -12)                     │
│  ──────────────────────────────────────────────────────     │
│  - class AuthModule:                    (red)               │
│  + class AuthService:                   (green)             │
│  + class TokenValidator:                (green)             │
│  ...                                                        │
├─────────────────────────────────────────────────────────────┤
│  docs/architecture/C4_ARCHITECTURE.md   (+12 / -0)          │
├─────────────────────────────────────────────────────────────┤
│  .genesis/gde_decision_log.jsonl        (+1 entry)          │
└─────────────────────────────────────────────────────────────┘
│  [ ✓ Approve all ]  [ ✗ Reject ]  [ ✎ Modify scope ]       │
└─────────────────────────────────────────────────────────────┘
```

User action → `user.approval` message → GDE.commit() (APPROVE) or session discarded (REJECT).
"Modify scope" opens a file-level checkbox selector before committing.

---

## 5. Context Engine (Scryer-Style Integration)

### 5.1 Purpose

The Context Engine solves the token budget problem: when the GDE runs an LLM-backed engine
(research, committee synthesis), it must pass relevant code context without dumping the entire
codebase. The Knowledge Graph + Import Graph provide the index.

### 5.2 Relevance Retrieval

```python
class ContextEngine:
    def fetch(self, query: str, budget_tokens: int = 4096) -> ContextBundle:
        # 1. Semantic search over Knowledge Graph nodes
        graph_hits = self.knowledge_graph.search(query, top_k=20)
        
        # 2. Expand to connected modules (1-hop)
        expanded = self.import_graph.expand(graph_hits, hops=1)
        
        # 3. Score by relevance × fragility × recency
        scored = [
            (node, self._score(node, query, graph_hits))
            for node in expanded
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # 4. Pack within token budget
        bundle = ContextBundle()
        for node, score in scored:
            snippet = self._extract_snippet(node, max_lines=30)
            if bundle.tokens + count_tokens(snippet) > budget_tokens:
                break
            bundle.add(node.file, snippet, score)
        
        return bundle
```

**Result:** LLM engines receive only the highest-relevance snippets, not full files.
This mirrors the "Scryer" pattern (context-aware retrieval) but built on Genesis's own
knowledge structures — no external dependency.

---

## 6. Application Roadmap

### MVP (v1.0 — 6–8 weeks)
- [ ] Tauri shell: bubble + panel (no Canvas in MVP)
- [ ] Python sidecar with WebSocket server
- [ ] GDE streaming events → bubble ring + panel strip
- [ ] Push-to-talk voice input (STT only, Whisper medium)
- [ ] Text intent → GDE → streaming results
- [ ] Approval gate: panel card (no visual diff yet)
- [ ] VS Code extension (cursor position only)
- [ ] Line-level God Class / VOLATILE hints
- [ ] macOS + Windows builds

### v1.0 (3 months post-MVP)
- [ ] Wake word activation (OpenWakeWord)
- [ ] TTS notifications (Piper; critical events only)
- [ ] Full Diff Approval view in Canvas
- [ ] RTL/LTR layout switching
- [ ] Activity levels (Quiet / Balanced / Active / Expert)
- [ ] Hebrew language full support (both STT + TTS)
- [ ] Committee panel (PRO: full advisor cards + divergence map)
- [ ] JetBrains plugin
- [ ] Snap-to-edge, multi-monitor, dockable rail

### v2.0 (future)
- [ ] Voice + function calls mid-conversation (per Instagram reel insight — see §7)
- [ ] Vercel AI SDK 7 gateway integration (audio-in → audio-out single model)
- [ ] Neovim LSP bridge
- [ ] iOS companion (status-only, approval notifications)
- [ ] Cross-project learning from voice patterns

---

## 7. Instagram Reel Research — Integration Analysis

**Source:** @eliron.giny (AI Tech), June 30 2026, 49s  
**Topic:** Vercel AI Gateway native voice support (AI SDK 7, beta)

**Key finding:** Vercel collapsed the traditional STT → LLM → TTS chain into a single
audio-in/audio-out model call through their AI Gateway. This eliminates 2 of 3 failure
points and dramatically reduces latency.

### Applicability to Genesis

| Concept | Genesis MVP path | v2.0 integration path |
|---------|-----------------|----------------------|
| Single audio-in/audio-out model | Use STT+TTS pipeline locally (privacy-first) | Replace with Vercel AI Gateway call for cloud-opt-in users |
| Turn detection / interruption handling | Implement via VAD in faster-whisper | Can inherit from AI SDK 7 `generateSpeech` |
| Mid-conversation function calls | Not in MVP (text approval only) | v2.0: voice command → GDE engine call during live voice session |
| Client-side API key security | N/A (fully local) | Relevant if cloud tier is added |

**Verdict:** The Vercel approach is architecturally correct for a cloud-first product.
For Genesis, which is **local-first by design**, the collapsed chain is achieved differently:
faster-whisper + Piper run in-process, eliminating network latency entirely (no HTTP round
trips). If a "cloud tier" is ever introduced, Vercel AI SDK 7 is the integration path.

**Mid-conversation function calls** (most relevant concept): in v2.0, while a user speaks,
the voice pipeline can invoke GDE sub-engines (search Knowledge Graph, check fragility map)
*before* the utterance completes, returning results by the time TTS responds. This mirrors
what Vercel demonstrates but runs locally.

---

## 8. Security & Privacy

| Concern | Mitigation |
|---------|-----------|
| WebSocket on localhost | Session token handshake; no CORS; loopback only |
| Wake word always-on mic | OpenWakeWord is on-device; audio discarded after detection window |
| IDE extension sends file paths | Paths only (no contents); user can disable per-project |
| Voice transcripts | Processed by faster-whisper locally; never logged or sent anywhere |
| Diff content in Canvas | Rendered in local WebView; no external requests |

**Invariant (from FLOATING_ASSISTANT_SPEC.md §3, binding here):**
Code, file contents, secrets, and voice transcripts never leave the machine.
