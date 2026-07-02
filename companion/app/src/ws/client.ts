import { invoke } from "@tauri-apps/api/core";
import { EnvelopeSchema, PAYLOAD_SCHEMAS } from "./schema";
import { useGenesisStore } from "@/store/store";
import { bridgeEvent, bridgeConnection } from "./ipc_bridge";

type ConnectionState = "disconnected" | "connecting" | "authing" | "open" | "reconnecting";

interface WsCredentials {
  port: number;
  token: string;
}

const log = (msg: string, ...args: unknown[]) => {
  if (import.meta.env.DEV) console.debug(`[ws] ${msg}`, ...args);
};

class GenesisWSClient {
  private state: ConnectionState = "disconnected";
  private ws: WebSocket | null = null;
  private token = "";
  private port = 47291;
  private backoffMs = 250;
  private watchdogTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;

  async connect(): Promise<void> {
    if (this.state !== "disconnected" && this.state !== "reconnecting") return;
    this.state = "connecting";

    try {
      const creds = await invoke<WsCredentials>("get_ws_credentials");
      if (!creds) {
        log("no credentials — sidecar not ready");
        this.scheduleReconnect();
        return;
      }
      this.token = creds.token;
      this.port = creds.port;
    } catch {
      log("failed to get credentials");
      this.scheduleReconnect();
      return;
    }

    const url = `ws://127.0.0.1:${this.port}`;
    log("connecting to", url);

    try {
      this.ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      log("open — sending auth");
      this.state = "authing";
      this.ws!.send(JSON.stringify({ type: "auth", token: this.token }));
      this.startWatchdog();
    };

    this.ws.onmessage = (ev) => {
      this.resetWatchdog();
      this.onMessage(ev.data as string);
    };

    this.ws.onclose = () => {
      log("closed");
      this.clearWatchdog();
      if (!this.destroyed) {
        this.state = "reconnecting";
        useGenesisStore.getState().setConnected(false);
        bridgeConnection(false);
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      log("error");
    };
  }

  disconnect(): void {
    this.destroyed = true;
    this.clearWatchdog();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
    this.state = "disconnected";
  }

  send(msg: object): void {
    if (this.state !== "open" || !this.ws) {
      log("send skipped — not connected", msg);
      return;
    }
    this.ws.send(JSON.stringify(msg));
  }

  private onMessage(raw: string): void {
    const parsed = EnvelopeSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) {
      log("invalid envelope", raw);
      return;
    }
    const env = parsed.data;

    // Auth ack
    if (env.type === "auth.ok") {
      log("authenticated");
      this.state = "open";
      this.backoffMs = 250;
      useGenesisStore.getState().setConnected(true);
      bridgeConnection(true);
      // Reconcile missed events after reconnect
      void this.reconcileSession();
      return;
    }

    if (env.type === "auth.fail") {
      log("auth failed — token mismatch");
      this.ws?.close();
      return;
    }

    // Validate payload against known schema
    const schema = PAYLOAD_SCHEMAS[env.type];
    if (schema) {
      const payloadResult = schema.safeParse(env.payload);
      if (!payloadResult.success) {
        log("invalid payload for", env.type, payloadResult.error);
        return;
      }
      useGenesisStore.getState().handleEvent(env.type, payloadResult.data);
      // Mirror to Bubble via Tauri IPC (Bubble has no direct WS)
      bridgeEvent(env.type, payloadResult.data);
    } else {
      log("unknown event type (ignored):", env.type);
    }
  }

  private async reconcileSession(): Promise<void> {
    try {
      const state = await invoke<Record<string, unknown>>("read_session_state", {
        projectDir: ".",
      });
      if (state) {
        // Hydrate store from session file — catches missed events during disconnect
        const store = useGenesisStore.getState();
        if (typeof state.overall_confidence === "number") {
          store.handleEvent("session.confidence", {
            session_id: state.session_id ?? "",
            confidence: state.overall_confidence,
            risk_level: state.project_risk_level ?? "UNKNOWN",
          });
        }
      }
    } catch {
      log("session reconcile failed");
    }
  }

  private scheduleReconnect(): void {
    if (this.destroyed) return;
    const jitter = Math.random() * 0.3;
    const delay = this.backoffMs * (1 + jitter);
    log(`reconnecting in ${Math.round(delay)}ms`);
    this.reconnectTimer = setTimeout(() => {
      this.backoffMs = Math.min(this.backoffMs * 2, 8000);
      void this.connect();
    }, delay);
  }

  private startWatchdog(): void {
    this.resetWatchdog();
  }

  private resetWatchdog(): void {
    if (this.watchdogTimer) clearTimeout(this.watchdogTimer);
    this.watchdogTimer = setTimeout(() => {
      log("watchdog timeout — forcing reconnect");
      this.ws?.close();
    }, 30_000);
  }

  private clearWatchdog(): void {
    if (this.watchdogTimer) {
      clearTimeout(this.watchdogTimer);
      this.watchdogTimer = null;
    }
  }
}

export const wsClient = new GenesisWSClient();
