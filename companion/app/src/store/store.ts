import { create } from "zustand";
import type {
  EngineDone,
  EngineStart,
  EngineFailed,
  GateApproval,
  SessionConfidence,
  SessionStart,
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

export type VoiceState = "idle" | "listening" | "transcribing" | "speaking";
export type ActivityLevel = "IDLE" | "THINKING" | "ATTENTION" | "BLOCKED";

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

  // Actions
  setConnected: (v: boolean) => void;
  setSidecarAlive: (v: boolean) => void;
  setSidecarError: (msg: string | null) => void;
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

  setConnected: (v) => set({ connected: v }),
  setSidecarAlive: (v) => set({ sidecarAlive: v }),
  setSidecarError: (msg) => set({ sidecarError: msg }),
  clearGate: () => set({ pendingGate: null }),
  clearDiff: () => set({ pendingDiff: null }),

  handleEvent: (type, payload) => {
    switch (type) {
      case "engine.start": {
        const p = payload as EngineStart;
        set((s) => ({
          engines: {
            ...s.engines,
            [p.engine_id]: {
              id: p.engine_id,
              phase: p.phase ?? 0,
              status: "running",
            },
          },
        }));
        break;
      }
      case "engine.done": {
        const p = payload as EngineDone;
        set((s) => ({
          engines: {
            ...s.engines,
            [p.engine_id]: {
              ...s.engines[p.engine_id],
              status: p.status === "SUCCESS" ? "done" :
                      p.status === "FAILED"  ? "failed" : "skipped",
              confidence: p.confidence,
              summary: p.summary,
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
            [p.engine_id]: {
              ...s.engines[p.engine_id],
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
            gateId: p.gate_id,
            description: p.description,
            diffPreviewHtml: p.diff_preview_html,
            overridable: p.overridable,
          },
        });
        break;
      }
      case "session.confidence": {
        const p = payload as SessionConfidence;
        set({ confidence: p.confidence, riskLevel: p.risk_level });
        break;
      }
      case "session.start": {
        const p = payload as SessionStart;
        set({
          sessionId: p.session_id,
          sessionMode: p.mode,
          engines: {},
          pendingGate: null,
          pendingDiff: null,
          committeeSynthesis: null,
        });
        break;
      }
      case "session.done": {
        // engines stay visible; clear voice state
        set({ voiceState: "idle", voiceTranscript: "" });
        break;
      }
      case "committee.synthesis": {
        const p = payload as CommitteeSynthesis;
        set({
          committeeSynthesis: {
            verdict: p.verdict,
            confidence: p.confidence,
            consensusType: p.consensus_type,
            minorityView: p.minority_view,
          },
        });
        break;
      }
      case "voice.transcript": {
        const p = payload as VoiceTranscript;
        set({ voiceTranscript: p.text, voiceState: p.is_final ? "idle" : "transcribing" });
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
            previewHtml: p.preview_html,
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
