import { useGenesisStore } from "@/store/store";

export function ResultSummary() {
  const mode      = useGenesisStore((s) => s.sessionMode);
  const sessionId = useGenesisStore((s) => s.sessionId);
  const committee = useGenesisStore((s) => s.committeeSynthesis);
  const confidence = useGenesisStore((s) => s.confidence);

  if (!sessionId) return null;

  return (
    <div style={{ padding: "12px 0", display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Session line */}
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Mode
        </span>
        <span
          style={{
            fontSize: "var(--text-sm)",
            fontWeight: 700,
            color: "var(--accent)",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
          }}
        >
          {mode ?? "—"}
        </span>
        <span style={{ marginLeft: "auto", fontSize: "var(--text-xs)", color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
          {sessionId.slice(0, 10)}…
        </span>
      </div>

      {/* Committee synthesis */}
      {committee && (
        <div
          style={{
            background: "var(--surface2)",
            borderRadius: "var(--r-md)",
            padding: "12px 14px",
            borderLeft: "3px solid var(--accent2)",
            animation: "fade-in 0.2s ease",
          }}
        >
          <div style={{ fontSize: "var(--text-xs)", color: "var(--muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Committee Verdict
          </div>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--text)", fontWeight: 600, marginBottom: 4 }}>
            {committee.verdict}
          </div>
          <div style={{ display: "flex", gap: 12, fontSize: "var(--text-xs)", color: "var(--muted)" }}>
            <span>Confidence: <strong style={{ color: "var(--text2)" }}>{Math.round(committee.confidence * 100)}%</strong></span>
            <span>Consensus: <strong style={{ color: "var(--accent2)" }}>{committee.consensusType}</strong></span>
          </div>
          {committee.minorityView && (
            <div style={{ marginTop: 8, fontSize: "var(--text-xs)", color: "var(--warn)", fontStyle: "italic" }}>
              Minority: {committee.minorityView}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
