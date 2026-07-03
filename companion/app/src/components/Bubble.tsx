import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect } from "react";
import { useGenesisStore, selectActivityLevel, type ActivityLevel } from "@/store/store";
import type { CSSProperties } from "react";

const RING_COLORS: Record<ActivityLevel, string> = {
  IDLE:      "var(--idle)",
  THINKING:  "var(--thinking)",
  ATTENTION: "var(--attention)",
  BLOCKED:   "var(--blocked)",
};

const ANIMATIONS: Record<ActivityLevel, string> = {
  IDLE:      "none",
  THINKING:  "pulse-thinking 2s ease-in-out infinite",
  ATTENTION: "none",
  BLOCKED:   "pulse-blocked 1.2s ease-in-out infinite",
};

export function Bubble() {
  const activity  = useGenesisStore(selectActivityLevel);
  const connected = useGenesisStore((s) => s.connected);
  const sidecarError = useGenesisStore((s) => s.sidecarError);
  const setSidecarError = useGenesisStore((s) => s.setSidecarError);
  const hasPendingGate = useGenesisStore((s) => s.pendingGate !== null);
  const hasPendingDiff = useGenesisStore((s) => s.pendingDiff !== null);

  // Listen for sidecar startup errors emitted by Rust
  useEffect(() => {
    const unlisten = listen<{ message: string }>("genesis://sidecar-error", (ev) => {
      setSidecarError(ev.payload.message);
      // Expand bubble window to show the setup card (280×160)
      invoke("resize_bubble", { width: 300, height: 170 }).catch(() => {});
    });
    return () => { unlisten.then((f) => f()); };
  }, [setSidecarError]);

  const badgeCount = (hasPendingGate ? 1 : 0) + (hasPendingDiff ? 1 : 0);

  const ringColor = connected ? RING_COLORS[activity] : "var(--muted)";
  const animation = connected ? ANIMATIONS[activity] : "none";

  const bubbleStyle: CSSProperties = {
    width: 64,
    height: 64,
    borderRadius: "50%",
    background: "var(--surface)",
    border: `2px solid ${ringColor}`,
    boxShadow: `var(--shadow-bubble), 0 0 0 0 ${ringColor}`,
    animation,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    position: "relative",
    transition: "border-color var(--t-normal)",
  };

  async function handleClick() {
    try {
      await invoke("toggle_panel");
    } catch {
      // panel might already be shown
    }
  }

  // First-run: genesis not installed or not in PATH
  if (sidecarError) {
    return (
      <div
        data-tauri-drag-region
        style={{
          width: 280,
          padding: "14px 16px",
          background: "var(--surface)",
          border: "1px solid var(--danger)",
          borderRadius: 12,
          fontFamily: "system-ui, sans-serif",
          fontSize: 12,
          color: "var(--text)",
          lineHeight: 1.5,
        }}
      >
        <div style={{ fontWeight: 700, color: "var(--danger)", marginBottom: 6 }}>
          Genesis not found
        </div>
        <div style={{ color: "var(--muted)", marginBottom: 10, fontSize: 11 }}>
          Install Genesis PRO then restart the Companion:
        </div>
        <code style={{
          display: "block",
          background: "var(--bg)",
          padding: "6px 10px",
          borderRadius: 6,
          fontSize: 11,
          color: "var(--accent)",
          marginBottom: 8,
          wordBreak: "break-all",
        }}>
          pip install genesis-architect-pro[companion]
        </code>
        <div style={{ color: "var(--muted)", fontSize: 10 }}>
          After install, right-click this window and choose Restart.
        </div>
      </div>
    );
  }

  return (
    <div
      data-tauri-drag-region
      style={{
        width: 72,
        height: 72,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={bubbleStyle} onClick={handleClick} role="button" aria-label="Toggle Genesis panel">
        {/* Logo mark */}
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <circle cx="14" cy="14" r="10" stroke={ringColor} strokeWidth="2" fill="none" />
          <path d="M14 8 L18 14 L14 20 L10 14 Z" fill={ringColor} opacity="0.9" />
        </svg>

        {/* Badge */}
        {badgeCount > 0 && (
          <div
            style={{
              position: "absolute",
              top: -2,
              right: -2,
              width: 18,
              height: 18,
              borderRadius: "50%",
              background: "var(--danger)",
              color: "#fff",
              fontSize: 10,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "2px solid var(--bg)",
            }}
          >
            {badgeCount}
          </div>
        )}

        {/* Disconnected dot */}
        {!connected && (
          <div
            style={{
              position: "absolute",
              bottom: 2,
              right: 2,
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--muted)",
              border: "2px solid var(--surface)",
            }}
          />
        )}
      </div>
    </div>
  );
}
