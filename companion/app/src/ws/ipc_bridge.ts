/**
 * Panel → Bubble IPC bridge.
 *
 * The Panel window owns the WebSocket connection. After each inbound event,
 * this module re-emits it via Tauri's event system so the Bubble window can
 * update its Zustand store without holding its own WebSocket connection.
 *
 * Two channels:
 *   genesis://event      { type, payload }  — every decoded WS event
 *   genesis://connection { connected }       — connection state changes
 */

import { emit } from "@tauri-apps/api/event";

const _log = (msg: string) => {
  if (import.meta.env.DEV) console.debug(`[ipc-bridge] ${msg}`);
};

export function bridgeEvent(type: string, payload: unknown): void {
  emit("genesis://event", { type, payload }).catch((err) => {
    _log(`emit genesis://event failed: ${err}`);
  });
}

export function bridgeConnection(connected: boolean): void {
  emit("genesis://connection", { connected }).catch((err) => {
    _log(`emit genesis://connection failed: ${err}`);
  });
}
