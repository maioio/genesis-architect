import { useGenesisStore } from "@/store/store";
import { sendApproval } from "@/actions/approvals";

export function ApprovalModal() {
  const gate = useGenesisStore((s) => s.pendingGate);
  const diff = useGenesisStore((s) => s.pendingDiff);
  const clearDiff = useGenesisStore((s) => s.clearDiff);

  // Show when there's both a gate AND a diff with preview HTML
  if (!gate || !diff?.previewHtml) return null;

  function handleApprove() {
    sendApproval(gate!.gateId, "approve");
    clearDiff();
  }

  function handleReject() {
    sendApproval(gate!.gateId, "reject");
    clearDiff();
  }

  function handleDefer() {
    sendApproval(gate!.gateId, "defer");
    clearDiff();
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(13,15,20,0.95)",
        display: "flex",
        flexDirection: "column",
        zIndex: 9999,
        animation: "fade-in 0.15s ease",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "18px 20px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <span style={{ color: "var(--danger)", fontSize: 16 }}>⊘</span>
        <div>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--danger)" }}>
            Approval Required — {gate.gateId}
          </div>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--muted)", marginTop: 2 }}>
            {diff.filesChanged} file{diff.filesChanged !== 1 ? "s" : ""} changed
          </div>
        </div>
      </div>

      {/* Description */}
      <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)" }}>
        <p style={{ fontSize: "var(--text-sm)", color: "var(--text2)" }}>{gate.description}</p>
      </div>

      {/* Diff preview — trusted local HTML from GDE */}
      <div
        style={{ flex: 1, overflow: "auto", padding: "0 4px" }}
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: diff.previewHtml }}
      />

      {/* Action buttons */}
      <div
        style={{
          padding: "16px 20px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          gap: 10,
          justifyContent: "flex-end",
        }}
      >
        <button onClick={handleDefer} style={btn("var(--muted)")}>Defer</button>
        <button onClick={handleReject} style={btn("var(--danger)")}>Reject</button>
        <button onClick={handleApprove} style={btn("var(--success)", true)}>Approve</button>
      </div>
    </div>
  );
}

function btn(color: string, primary = false): React.CSSProperties {
  return {
    padding: "8px 22px",
    borderRadius: "var(--r-sm)",
    border: `1px solid ${color}`,
    background: primary ? color : `${color}18`,
    color: primary ? "#fff" : color,
    fontSize: "var(--text-sm)",
    fontWeight: 700,
    cursor: "pointer",
    transition: "opacity var(--t-fast)",
  };
}
