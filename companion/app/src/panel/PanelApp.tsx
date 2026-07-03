import { useGenesisStore, selectActivityLevel } from "@/store/store";
import { EngineProgress } from "@/components/Panel/EngineProgress";
import { ConfidenceMeter } from "@/components/Panel/ConfidenceMeter";
import { GateStatus } from "@/components/Panel/GateStatus";
import { ResultSummary } from "@/components/Panel/ResultSummary";
import { VoicePTT } from "@/components/Panel/VoicePTT";
import { ApprovalModal } from "@/components/Approval/ApprovalModal";

export function PanelApp() {
  const connected  = useGenesisStore((s) => s.connected);
  const sidecarUp  = useGenesisStore((s) => s.sidecarAlive);
  const activity   = useGenesisStore(selectActivityLevel);
  const pendingGate = useGenesisStore((s) => s.pendingGate);
  const pendingDiff = useGenesisStore((s) => s.pendingDiff);

  const showApproval = pendingGate !== null && pendingDiff?.previewHtml != null;

  return (
    <div
      style={{
        width: "100%",
        height: "100vh",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-xl)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        boxShadow: "var(--shadow-panel)",
        position: "relative",
      }}
    >
      {/* Approval modal overlays everything */}
      {showApproval && <ApprovalModal />}

      {/* Header */}
      <div
        data-tauri-drag-region
        style={{
          padding: "14px 18px 12px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        {/* Activity dot */}
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: connected
              ? activity === "BLOCKED"   ? "var(--danger)"
              : activity === "ATTENTION" ? "var(--attention)"
              : activity === "THINKING"  ? "var(--thinking)"
              :                            "var(--success)"
              : "var(--muted)",
            transition: "background var(--t-normal)",
          }}
        />
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text)", flex: 1 }}>
          Genesis PRO
        </span>
        <span
          style={{
            fontSize: "var(--text-xs)",
            color: connected ? "var(--success)" : "var(--muted)",
          }}
        >
          {connected ? "connected" : sidecarUp ? "connecting…" : "offline"}
        </span>
      </div>

      {/* Body — scrollable */}
      <div style={{ flex: 1, overflow: "auto", padding: "16px 14px", display: "flex", flexDirection: "column", gap: 16 }}>

        {/* Gate banner (compact — full modal if diff exists) */}
        {pendingGate && !showApproval && <GateStatus />}

        {/* Confidence */}
        <ConfidenceMeter />

        {/* Engine progress */}
        <section>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
            Engines
          </div>
          <EngineProgress />
        </section>

        {/* Last result */}
        <ResultSummary />

        {/* Voice PTT */}
        <section>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
            Voice Input
          </div>
          <VoicePTT />
        </section>
      </div>
    </div>
  );
}
