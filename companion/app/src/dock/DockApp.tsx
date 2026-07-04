import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useGenesisStore, selectActivityLevel } from "@/store/store";
import { wsClient } from "@/ws/client";
import { VoiceOrb } from "@/components/VoiceOrb";
import { useMic } from "@/voice/useMic";
import "./dock.css";

const RAIL_W = 64;
const RAIL_H = 340;
const PANEL_W = 400;
const PANEL_H = 640;

type DockSide = "left" | "right";

/** Detect UI language from the browser; Hebrew docks right, everything else left. */
function detectSide(): DockSide {
  const lang = (navigator.language || "en").toLowerCase();
  return lang.startsWith("he") ? "right" : "left";
}

export function DockApp() {
  const side = useGenesisStore((s) => s.dockSide);
  const setDockSide = useGenesisStore((s) => s.setDockSide);
  const expanded = useGenesisStore((s) => s.expanded);
  const setExpanded = useGenesisStore((s) => s.setExpanded);
  const connected = useGenesisStore((s) => s.connected);
  const sidecarError = useGenesisStore((s) => s.sidecarError);
  const setSidecarError = useGenesisStore((s) => s.setSidecarError);
  const voiceState = useGenesisStore((s) => s.voiceState);
  const setVoiceState = useGenesisStore((s) => s.setVoiceState);
  const activity = useGenesisStore(selectActivityLevel);
  const conversation = useGenesisStore((s) => s.conversation);
  const addTurn = useGenesisStore((s) => s.addTurn);
  const engines = useGenesisStore((s) => s.engines);
  const pendingGate = useGenesisStore((s) => s.pendingGate);
  const voiceTranscript = useGenesisStore((s) => s.voiceTranscript);

  const mic = useMic();
  const [text, setText] = useState("");
  const [continuous, setContinuous] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // ── Dock geometry: snap to the correct edge whenever side/expanded changes ──
  const applyDock = useCallback(
    (nextSide: DockSide, nextExpanded: boolean) => {
      const w = nextExpanded ? PANEL_W : RAIL_W;
      const h = nextExpanded ? PANEL_H : RAIL_H;
      invoke("dock_to_edge", { side: nextSide, width: w, height: h }).catch(() => {});
    },
    []
  );

  useEffect(() => {
    const initial = detectSide();
    setDockSide(initial);
    applyDock(initial, false);
    void wsClient.connect();
    return () => wsClient.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { applyDock(side, expanded); }, [side, expanded, applyDock]);

  // Sidecar-not-found → auto-expand so the user sees the fix.
  useEffect(() => {
    const un = listen<{ message: string }>("genesis://sidecar-error", (ev) => {
      setSidecarError(ev.payload.message);
      setExpanded(true);
    });
    return () => { un.then((f) => f()); };
  }, [setSidecarError, setExpanded]);

  // Auto-scroll conversation to the newest turn.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [conversation, voiceTranscript]);

  // ── Voice control ──
  const startListening = useCallback(async () => {
    if (!expanded) setExpanded(true);
    await mic.start();
    setVoiceState("listening");
    wsClient.send({ type: "user.voice_start", payload: {} });
  }, [expanded, mic, setExpanded, setVoiceState]);

  const stopListening = useCallback(() => {
    mic.stop();
    setVoiceState("idle");
    wsClient.send({ type: "user.voice_end", payload: {} });
  }, [mic, setVoiceState]);

  const toggleContinuous = useCallback(() => {
    if (continuous) { setContinuous(false); stopListening(); }
    else { setContinuous(true); void startListening(); }
  }, [continuous, startListening, stopListening]);

  // ── Text send ──
  const sendText = useCallback(() => {
    const instruction = text.trim();
    if (!instruction) return;
    addTurn({ id: crypto.randomUUID(), role: "user", text: instruction });
    wsClient.send({ type: "user.intent", payload: { instruction } });
    setVoiceState("thinking");
    setText("");
  }, [text, addTurn, setVoiceState]);

  const runningCount = useMemo(
    () => Object.values(engines).filter((e) => e.status === "running").length,
    [engines]
  );

  const statusLabel: Record<string, string> = {
    idle: connected ? "Ready" : "Connecting…",
    listening: "Listening…",
    transcribing: "…",
    thinking: runningCount ? `${runningCount} engines running` : "Thinking…",
    speaking: "Speaking…",
  };

  const activityClass = `activity-${activity.toLowerCase()}`;

  // ── Collapsed rail ──
  if (!expanded) {
    return (
      <div className={`rail ${side} ${activityClass}`} data-tauri-drag-region>
        <button
          className="rail-orb"
          onClick={() => setExpanded(true)}
          aria-label="Open Genesis Companion"
          title="Genesis Companion"
        >
          <VoiceOrb state={voiceState} level={mic.level} size={48} />
        </button>
        {pendingGate && <span className="rail-badge" aria-label="Approval needed">1</span>}
        <button
          className="rail-mic"
          onClick={(e) => { e.stopPropagation(); void startListening(); }}
          aria-label="Talk to Genesis"
          title="Talk"
        >
          <MicIcon />
        </button>
        <span className={`rail-status-dot ${connected ? "on" : "off"}`} />
      </div>
    );
  }

  // ── Expanded panel ──
  return (
    <div className={`panel ${side} ${activityClass}`}>
      <header className="panel-head" data-tauri-drag-region>
        <div className="panel-title">
          <VoiceOrb state={voiceState} level={mic.level} size={28} />
          <div>
            <div className="panel-name">Genesis</div>
            <div className="panel-status">{statusLabel[voiceState]}</div>
          </div>
        </div>
        <div className="panel-actions">
          <button
            className="ghost-btn"
            onClick={() => setDockSide(side === "right" ? "left" : "right")}
            aria-label="Switch side"
            title="Switch side"
          >
            {side === "right" ? "⇤" : "⇥"}
          </button>
          <button
            className="ghost-btn"
            onClick={() => { if (continuous) toggleContinuous(); setExpanded(false); }}
            aria-label="Collapse"
            title="Collapse"
          >
            ✕
          </button>
        </div>
      </header>

      {sidecarError ? (
        <div className="firstrun">
          <div className="firstrun-title">Genesis backend not found</div>
          <p>Install Genesis Pro, then reopen the Companion:</p>
          <code>pip install genesis-architect-pro</code>
          <button
            className="primary-btn"
            onClick={() => invoke("restart_sidecar").then(() => setSidecarError(null)).catch(() => {})}
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          <div className="convo" ref={scrollRef}>
            {conversation.length === 0 && (
              <div className="empty">
                <VoiceOrb state={voiceState} level={mic.level} size={112} />
                <p className="empty-hint">
                  Ask me anything about this project — or just start talking.
                </p>
                <div className="chips">
                  {["Audit this codebase", "What's the riskiest file?", "Refactor plan"].map((c) => (
                    <button key={c} className="chip" onClick={() => { setText(c); }}>
                      {c}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {conversation.map((turn) => (
              <div key={turn.id} className={`turn ${turn.role}`}>
                <div className="bubble-msg">{turn.text}</div>
              </div>
            ))}
            {voiceState === "listening" && voiceTranscript && (
              <div className="turn user pending">
                <div className="bubble-msg">{voiceTranscript}</div>
              </div>
            )}

            {runningCount > 0 && (
              <div className="engine-strip">
                {Object.values(engines).slice(-6).map((e) => (
                  <span key={e.id} className={`engine-pill ${e.status}`}>{e.id}</span>
                ))}
              </div>
            )}

            {pendingGate && (
              <div className="gate-card">
                <div className="gate-title">Approval needed</div>
                <div className="gate-desc">{pendingGate.description}</div>
                <div className="gate-btns">
                  <button
                    className="primary-btn"
                    onClick={() => { wsClient.send({ type: "user.approval", payload: { gate_id: pendingGate.gateId, decision: "approve" } }); useGenesisStore.getState().clearGate(); }}
                  >Approve</button>
                  <button
                    className="ghost-btn wide"
                    onClick={() => { wsClient.send({ type: "user.approval", payload: { gate_id: pendingGate.gateId, decision: "reject" } }); useGenesisStore.getState().clearGate(); }}
                  >Reject</button>
                </div>
              </div>
            )}
          </div>

          <footer className="composer">
            <button
              className={`mic-btn ${continuous ? "on" : ""}`}
              onClick={toggleContinuous}
              onMouseDown={(e) => { if (!continuous) { e.preventDefault(); void startListening(); } }}
              onMouseUp={() => { if (!continuous) stopListening(); }}
              aria-label={continuous ? "Stop conversation" : "Hold to talk, click to converse"}
              title={continuous ? "Conversation on — click to stop" : "Hold to talk · click for hands-free"}
            >
              <MicIcon />
            </button>
            <input
              className="composer-input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") sendText(); }}
              placeholder="Message Genesis…"
              aria-label="Message Genesis"
            />
            <button className="send-btn" onClick={sendText} disabled={!text.trim()} aria-label="Send">
              →
            </button>
          </footer>
        </>
      )}
    </div>
  );
}

function MicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
      <path d="M6 11a6 6 0 0 0 12 0M12 17v4M8 21h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}
