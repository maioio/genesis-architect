import { useGenesisStore, type EngineState } from "@/store/store";

const STATUS_COLOR: Record<EngineState["status"], string> = {
  running: "var(--accent)",
  done:    "var(--success)",
  failed:  "var(--danger)",
  skipped: "var(--muted)",
};

const STATUS_LABEL: Record<EngineState["status"], string> = {
  running: "⟳",
  done:    "✓",
  failed:  "✗",
  skipped: "–",
};

export function EngineProgress() {
  const engines = useGenesisStore((s) => s.engines);
  const entries = Object.values(engines);

  if (entries.length === 0) {
    return (
      <div style={{ padding: "16px", color: "var(--muted)", fontSize: "var(--text-sm)" }}>
        Waiting for session…
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {entries.map((engine) => (
        <div
          key={engine.id}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "8px 14px",
            background: "var(--surface2)",
            borderRadius: "var(--r-md)",
            animation: engine.status === "running" ? "fade-in 0.15s ease" : "none",
          }}
        >
          {/* Status icon */}
          <span
            style={{
              width: 20,
              height: 20,
              borderRadius: "50%",
              background: `${STATUS_COLOR[engine.status]}22`,
              color: STATUS_COLOR[engine.status],
              fontSize: 11,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              animation: engine.status === "running" ? "spin 1.2s linear infinite" : "none",
            }}
          >
            {STATUS_LABEL[engine.status]}
          </span>

          {/* Name */}
          <span
            style={{
              flex: 1,
              fontSize: "var(--text-sm)",
              color: engine.status === "skipped" ? "var(--muted)" : "var(--text)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {engine.id}
          </span>

          {/* Confidence badge */}
          {engine.confidence !== undefined && (
            <span
              style={{
                fontSize: "var(--text-xs)",
                color: engine.confidence >= 0.7
                  ? "var(--success)"
                  : engine.confidence >= 0.4
                  ? "var(--warn)"
                  : "var(--danger)",
                fontWeight: 600,
              }}
            >
              {Math.round(engine.confidence * 100)}%
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
