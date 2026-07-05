import { create } from "zustand";
import type {
  EngineDone,
  EngineStart,
  EngineFailed,
  GateApproval,
  SessionConfidence,
  SessionStart,
  SessionReply,
  SessionDone,
  CommitteeSynthesis,
  VoiceTranscript,
  DiffReady,
} from "@/ws/schema";

export interface EngineState {
  id: string;
  phase: number;
  status: "running" | "done" | "failed" | "skipped";
  confidence?: number;
  summary?: string;
}

export interface PendingGate {
  gateId: string;
  description: string;
  diffPreviewHtml?: string;
  overridable: boolean;
}

export interface PendingDiff {
  diffId: string;
  filesChanged: number;
  previewHtml: string;
}

export interface CommitteeSynthesisState {
  verdict: string;
  confidence: number;
  consensusType: string;
  minorityView?: string;
}

export type VoiceState = "idle" | "listening" | "transcribing" | "thinking" | "speaking";
export type ActivityLevel = "IDLE" | "THINKING" | "ATTENTION" | "BLOCKED";
export type DockSide = "left" | "right";

export interface Turn {
  id: string;
  role: "user" | "genesis";
  text: string;
  streaming?: boolean;
}

interface GenesisStore {
  // Connection
  connected: boolean;
  sidecarAlive: boolean;
  sidecarError: string | null;  // set when genesis is not found / fails to start

  // Session
  sessionId: string | null;
  sessionMode: string | null;
  confidence: number;
  riskLevel: string;

  // Engines — Map serialized as plain object for Zustand compatibility
  engines: Record<string, EngineState>;

  // Gate
  pendingGate: PendingGate | null;

  // Diff
  pendingDiff: PendingDiff | null;

  // Committee
  committeeSynthesis: CommitteeSynthesisState | null;

  // Voice
  voiceState: VoiceState;
  voiceTranscript: string;

  // Dock + conversation
  expanded: boolean;
  hidden: boolean;
  dockSide: DockSide;
  conversation: Turn[];

  // Actions
  setConnected: (v: boolean) => void;
  setSidecarAlive: (v: boolean) => void;
  setSidecarError: (msg: string | null) => void;
  setExpanded: (v: boolean) => void;
  setHidden: (v: boolean) => void;
  setDockSide: (s: DockSide) => void;
  setVoiceState: (v: VoiceState) => void;
  addTurn: (t: Turn) => void;
  appendToLastGenesisTurn: (chunk: string) => void;
  clearGate: () => void;
  clearDiff: () => void;
  handleEvent: (type: string, payload: unknown) => void;
}

export const useGenesisStore = create<GenesisStore>((set) => ({
  connected: false,
  sidecarAlive: false,
  sidecarError: null,
  sessionId: null,
  sessionMode: null,
  confidence: 1.0,
  riskLevel: "UNKNOWN",
  engines: {},
  pendingGate: null,
  pendingDiff: null,
  committeeSynthesis: null,
  voiceState: "idle",
  voiceTranscript: "",
  expanded: false,
  hidden: false,
  dockSide: "right",
  conversation: [],

  setConnected: (v) => set({ connected: v }),
  setSidecarAlive: (v) => set({ sidecarAlive: v }),
  setSidecarError: (msg) => set({ sidecarError: msg }),
  setExpanded: (v) => set({ expanded: v }),
  setHidden: (v) => set({ hidden: v }),
  setDockSide: (s) => set({ dockSide: s }),
  setVoiceState: (v) => set({ voiceState: v }),
  addTurn: (t) => set((s) => ({ conversation: [...s.conversation, t] })),
  appendToLastGenesisTurn: (chunk) =>
    set((s) => {
      const conv = [...s.conversation];
      const last = conv[conv.length - 1];
      if (last && last.role === "genesis" && last.streaming) {
        conv[conv.length - 1] = { ...last, text: last.text + chunk };
      } else {
        conv.push({ id: crypto.randomUUID(), role: "genesis", text: chunk, streaming: true });
      }
      return { conversation: conv };
    }),
  clearGate: () => set({ pendingGate: null }),
  clearDiff: () => set({ pendingDiff: null }),

  handleEvent: (type, payload) => {
    switch (type) {
      case "engine.start": {
        const p = payload as EngineStart;
        set((s) => ({
          engines: {
            ...s.engines,
            [p.engine]: {
              id: p.engine,
              phase: p.phase ?? 0,
              status: "running",
            },
          },
        }));
        break;
      }
      case "engine.done": {
        // The backend only emits engine.done for successful engines;
        // failures arrive as engine.failed.
        const p = payload as EngineDone;
        set((s) => ({
          engines: {
            ...s.engines,
            [p.engine]: {
              ...s.engines[p.engine],
              id: p.engine,
              status: "done",
              confidence: p.confidence,
              summary: p.result_summary,
            },
          },
        }));
        break;
      }
      case "engine.failed": {
        const p = payload as EngineFailed;
        set((s) => ({
          engines: {
            ...s.engines,
            [p.engine]: {
              ...s.engines[p.engine],
              id: p.engine,
              status: "failed",
              summary: p.error,
            },
          },
        }));
        break;
      }
      case "gate.approval_required": {
        const p = payload as GateApproval;
        set({
          pendingGate: {
            gateId: p.gate_name,
            description: p.description,
            diffPreviewHtml: p.diff_preview,
            overridable: true,
          },
        });
        break;
      }
      case "session.confidence": {
        const p = payload as SessionConfidence;
        set((s) => ({
          confidence: p.confidence ?? s.confidence,
          riskLevel: p.risk_level ?? s.riskLevel,
        }));
        break;
      }
      case "session.start": {
        const p = payload as SessionStart;
        set({
          sessionMode: p.mode || null,
          engines: {},
          pendingGate: null,
          pendingDiff: null,
          committeeSynthesis: null,
          voiceState: "thinking",
        });
        break;
      }
      case "session.reply": {
        // The assistant's real answer — the backend composed it from the
        // actual findings and speaks it aloud in parallel.
        const p = payload as SessionReply;
        set((s) => ({
          voiceState: "speaking",
          conversation: [
            ...s.conversation,
            { id: crypto.randomUUID(), role: "genesis" as const, text: p.text },
          ],
        }));
        break;
      }
      case "session.done": {
        // The conversational answer arrives separately as session.reply
        // (composed by the backend from real findings) — here we just settle.
        const p = payload as SessionDone;
        set((s) => ({
          voiceState: "idle",
          voiceTranscript: "",
          sessionMode: p.mode ?? s.sessionMode,
          confidence: p.confidence ?? s.confidence,
        }));
        break;
      }
      case "committee.synthesis": {
        const p = payload as CommitteeSynthesis;
        set((s) => ({
          committeeSynthesis: {
            verdict: p.verdict,
            confidence: s.confidence,
            consensusType: p.consensus_type,
            minorityView: p.minority_view ?? undefined,
          },
        }));
        break;
      }
      case "voice.transcript": {
        const p = payload as VoiceTranscript;
        if (p.is_final && p.text.trim()) {
          // Commit the recognized speech as a user turn and kick off thinking.
          set((s) => ({
            voiceTranscript: "",
            voiceState: "thinking",
            conversation: [
              ...s.conversation,
              { id: crypto.randomUUID(), role: "user" as const, text: p.text.trim() },
            ],
          }));
        } else {
          set({ voiceTranscript: p.text, voiceState: "transcribing" });
        }
        break;
      }
      case "voice.tts_chunk": {
        set({ voiceState: "speaking" });
        break;
      }
      case "diff.ready": {
        const p = payload as DiffReady;
        set({
          pendingDiff: {
            diffId: p.diff_id,
            filesChanged: p.files_changed,
            previewHtml: p.preview_html ?? "",
          },
        });
        break;
      }
      case "sidecar.down": {
        set({ connected: false, sidecarAlive: false });
        break;
      }
    }
  },
}));

// Derived selector — not stored, computed on read
export const selectActivityLevel = (state: GenesisStore): ActivityLevel => {
  if (state.pendingGate) return "BLOCKED";
  if (state.pendingDiff) return "ATTENTION";
  const hasRunning = Object.values(state.engines).some((e) => e.status === "running");
  if (hasRunning) return "THINKING";
  return "IDLE";
};
