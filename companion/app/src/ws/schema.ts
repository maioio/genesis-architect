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
// These mirror the *actual* constructors in streaming/events.py — key names
// must match what the backend emits (engine, gate_name, result_summary, …).
// A mismatch here silently drops the event at validation and the UI goes
// blind, which is exactly what happened before v7.2.

export const EngineStartPayload = z.object({
  engine:       z.string(),
  phase:        z.number().optional(),
  total_phases: z.number().optional(),
});

export const EngineDonePayload = z.object({
  engine:         z.string(),
  confidence:     z.number().optional(),
  result_summary: z.string().optional(),
});

export const EngineFailedPayload = z.object({
  engine:             z.string(),
  error:              z.string(),
  confidence_penalty: z.number().optional(),
});

export const GateFiredPayload = z.object({
  gate_name:   z.string(),
  type:        z.string().optional(),
  overridable: z.boolean().optional(),
});

export const GateApprovalPayload = z.object({
  gate_name:    z.string(),
  description:  z.string(),
  diff_preview: z.string().optional(),
});

export const SessionConfidencePayload = z.object({
  confidence: z.number().optional(),
  risk_level: z.string().optional(),
  error:      z.string().optional(), // _emit_error rides this type
});

export const SessionStartPayload = z.object({
  mode:        z.string().optional(),
  instruction: z.string().optional(),
});

export const SessionReplyPayload = z.object({
  text: z.string(),
});

export const SessionDonePayload = z.object({
  confidence: z.number(),
  risk_level: z.string().optional(),
  mode:       z.string().optional(),
});

export const CommitteeSynthesisPayload = z.object({
  verdict:        z.string(),
  consensus_type: z.string(),
  minority_view:  z.string().nullable().optional(),
});

export const VoiceTranscriptPayload = z.object({
  text:     z.string(),
  is_final: z.boolean(),
});

export const VoiceTtsChunkPayload = z.object({
  audio_b64: z.string().optional(),
  is_final:  z.boolean().optional(),
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
  preview_html:  z.string().optional(),
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
  "session.reply":          SessionReplyPayload,
  "session.done":           SessionDonePayload,
  "committee.synthesis":    CommitteeSynthesisPayload,
  "voice.transcript":       VoiceTranscriptPayload,
  "voice.tts_chunk":        VoiceTtsChunkPayload,
  "ide.line_event":         IdeLineEventPayload,
  "diff.ready":             DiffReadyPayload,
};

export type EngineStart        = z.infer<typeof EngineStartPayload>;
export type EngineDone         = z.infer<typeof EngineDonePayload>;
export type EngineFailed       = z.infer<typeof EngineFailedPayload>;
export type GateFired          = z.infer<typeof GateFiredPayload>;
export type GateApproval       = z.infer<typeof GateApprovalPayload>;
export type SessionConfidence  = z.infer<typeof SessionConfidencePayload>;
export type SessionStart       = z.infer<typeof SessionStartPayload>;
export type SessionReply       = z.infer<typeof SessionReplyPayload>;
export type SessionDone        = z.infer<typeof SessionDonePayload>;
export type CommitteeSynthesis = z.infer<typeof CommitteeSynthesisPayload>;
export type VoiceTranscript    = z.infer<typeof VoiceTranscriptPayload>;
export type VoiceTtsChunk      = z.infer<typeof VoiceTtsChunkPayload>;
export type IdeLineEvent       = z.infer<typeof IdeLineEventPayload>;
export type DiffReady          = z.infer<typeof DiffReadyPayload>;
