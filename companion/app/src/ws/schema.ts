import { z } from "zod";

// Base envelope from events.py: {id, type, ts, session_id, payload}
export const EnvelopeSchema = z.object({
  id:         z.string(),
  type:       z.string(),
  ts:         z.number(),
  session_id: z.string().optional(),
  payload:    z.record(z.unknown()).optional().default({}),
});
export type Envelope = z.infer<typeof EnvelopeSchema>;

// ── Payload schemas ──────────────────────────────────────────────────────────

export const EngineStartPayload = z.object({
  engine_id: z.string(),
  phase:     z.number().optional(),
});

export const EngineDonePayload = z.object({
  engine_id:  z.string(),
  status:     z.enum(["SUCCESS", "DEGRADED", "FAILED", "SKIPPED"]),
  confidence: z.number().optional(),
  summary:    z.string().optional(),
});

export const EngineFailedPayload = z.object({
  engine_id: z.string(),
  error:     z.string(),
});

export const GateFiredPayload = z.object({
  gate_id:    z.string(),
  outcome:    z.enum(["PASS", "WARN", "BLOCK", "HARD_BLOCK"]),
  reason:     z.string(),
  overridable: z.boolean().optional(),
});

export const GateApprovalPayload = z.object({
  gate_id:          z.string(),
  description:      z.string(),
  diff_preview_html: z.string().optional(),
  overridable:      z.boolean(),
});

export const SessionConfidencePayload = z.object({
  session_id:  z.string(),
  confidence:  z.number(),
  risk_level:  z.string(),
});

export const SessionStartPayload = z.object({
  session_id:  z.string(),
  mode:        z.string(),
  instruction: z.string().optional(),
});

export const SessionDonePayload = z.object({
  session_id:   z.string(),
  confidence:   z.number(),
  engine_count: z.number().optional(),
});

export const CommitteeSynthesisPayload = z.object({
  verdict:        z.string(),
  confidence:     z.number(),
  consensus_type: z.string(),
  minority_view:  z.string().optional(),
});

export const VoiceTranscriptPayload = z.object({
  text:     z.string(),
  is_final: z.boolean(),
});

export const VoiceTtsChunkPayload = z.object({
  audio_b64: z.string(),
  is_final:  z.boolean(),
});

export const IdeLineEventPayload = z.object({
  file:       z.string(),
  line:       z.number(),
  pattern:    z.string(),
  severity:   z.string(),
  suggestion: z.string(),
});

export const DiffReadyPayload = z.object({
  diff_id:       z.string(),
  files_changed: z.number(),
  preview_html:  z.string(),
});

// Map type → payload schema
export const PAYLOAD_SCHEMAS: Record<string, z.ZodTypeAny> = {
  "engine.start":           EngineStartPayload,
  "engine.done":            EngineDonePayload,
  "engine.failed":          EngineFailedPayload,
  "gate.fired":             GateFiredPayload,
  "gate.approval_required": GateApprovalPayload,
  "session.confidence":     SessionConfidencePayload,
  "session.start":          SessionStartPayload,
  "session.done":           SessionDonePayload,
  "committee.synthesis":    CommitteeSynthesisPayload,
  "voice.transcript":       VoiceTranscriptPayload,
  "voice.tts_chunk":        VoiceTtsChunkPayload,
  "ide.line_event":         IdeLineEventPayload,
  "diff.ready":             DiffReadyPayload,
};

export type EngineStart       = z.infer<typeof EngineStartPayload>;
export type EngineDone        = z.infer<typeof EngineDonePayload>;
export type EngineFailed      = z.infer<typeof EngineFailedPayload>;
export type GateFired         = z.infer<typeof GateFiredPayload>;
export type GateApproval      = z.infer<typeof GateApprovalPayload>;
export type SessionConfidence = z.infer<typeof SessionConfidencePayload>;
export type SessionStart      = z.infer<typeof SessionStartPayload>;
export type SessionDone       = z.infer<typeof SessionDonePayload>;
export type CommitteeSynthesis = z.infer<typeof CommitteeSynthesisPayload>;
export type VoiceTranscript   = z.infer<typeof VoiceTranscriptPayload>;
export type VoiceTtsChunk     = z.infer<typeof VoiceTtsChunkPayload>;
export type IdeLineEvent      = z.infer<typeof IdeLineEventPayload>;
export type DiffReady         = z.infer<typeof DiffReadyPayload>;
