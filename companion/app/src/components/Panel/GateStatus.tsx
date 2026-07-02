import { useGenesisStore } from "@/store/store";
import { sendApproval } from "@/actions/approvals";

export function GateStatus() {
  const gate = useGenesisStore((s) => s.pendingGate);

  if (!gate) return null;

  return (
    <div
      style={{
        background: "rgba(239,68,68,0.08)",
        border: "1px solid rgba(239,68,68,0.3)",
        borderRadius: "var(--r-md)",
        padding: "14px 16px",
        animation: "fade-in 0.2s ease",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ color: "var(--danger)", fontSize: 14 }}>⊘</span>
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--danger)" }}>
          Gate: {gate.gateId}
        </span>
        {gate.overridable && (
          <span
            style={{
              fontSize: "var(--text-xs)",
              color: "var(--warn)",
              background: "rgba(245,158,11,0.1)",
              padding: "1px 6px",
              borderRadius: "var(--r-sm)",
              marginLeft: "auto",
            }}
          >
            overridable
          </span>
        )}
      </div>

      <p style={{ fontSize: "var(--text-sm)", color: "var(--text2)", marginBottom: 12 }}>
        {gate.description}
      </p>

      {/* Buttons */}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={() => sendApproval(gate.gateId, "approve")}
          style={btnStyle("var(--success)")}
        >
          Approve
        </button>
        <button
          onClick={() => sendApproval(gate.gateId, "reject")}
          style={btnStyle("var(--danger)")}
        >
          Reject
        </button>
        <button
          onClick={() => sendApproval(gate.gateId, "defer")}
          style={btnStyle("var(--muted)")}
        >
          Defer
        </button>
      </div>
    </div>
  );
}

function btnStyle(color: string): React.CSSProperties {
  return {
    padding: "6px 16px",
    borderRadius: "var(--r-sm)",
    border: `1px solid ${color}`,
    background: `${color}18`,
    color,
    fontSize: "var(--text-sm)",
    fontWeight: 600,
    cursor: "pointer",
    transition: "background var(--t-fast)",
  };
}
