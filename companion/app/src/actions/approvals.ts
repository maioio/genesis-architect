import { wsClient } from "@/ws/client";
import { useGenesisStore } from "@/store/store";

export type ApprovalDecision = "approve" | "reject" | "defer";

export function sendApproval(gateId: string, decision: ApprovalDecision): void {
  wsClient.send({
    type: "user.approval",
    payload: { gate_id: gateId, decision },
  });
  useGenesisStore.getState().clearGate();
}

export function sendIntent(instruction: string): void {
  wsClient.send({
    type: "user.intent",
    payload: { instruction },
  });
}

export function sendVoiceStart(): void {
  wsClient.send({ type: "user.voice_start", payload: {} });
}

export function sendVoiceEnd(audioB64: string): void {
  wsClient.send({ type: "user.voice_end", payload: { audio_b64: audioB64 } });
}
