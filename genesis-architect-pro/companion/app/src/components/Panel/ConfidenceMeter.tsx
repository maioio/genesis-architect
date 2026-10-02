import { useGenesisStore } from "@/store/store";

export function ConfidenceMeter() {
  const confidence = useGenesisStore((s) => s.confidence);
  const riskLevel  = useGenesisStore((s) => s.riskLevel);

  const pct = Math.round(confidence * 100);
  const color =
    pct >= 70 ? "var(--success)" :
    pct >= 40 ? "var(--warn)"    :
                "var(--danger)";

  // SVG arc
  const R = 36;
  const cx = 48;
  const cy = 48;
  const startAngle = -210;
  const sweep = 240;
  const angle = startAngle + (pct / 100) * sweep;

  function polar(deg: number, r: number) {
    const rad = (deg * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  const start = polar(startAngle, R);
  const end   = polar(angle, R);
  const large = (pct / 100) * sweep > 180 ? 1 : 0;

  const trackEnd = polar(startAngle + sweep, R);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "12px 14px" }}>
      {/* Arc gauge */}
      <svg width="96" height="96" viewBox="0 0 96 96">
        {/* Track */}
        <path
          d={`M ${start.x} ${start.y} A ${R} ${R} 0 1 1 ${trackEnd.x} ${trackEnd.y}`}
          fill="none"
          stroke="var(--border)"
          strokeWidth="6"
          strokeLinecap="round"
        />
        {/* Fill */}
        {pct > 0 && (
          <path
            d={`M ${start.x} ${start.y} A ${R} ${R} 0 ${large} 1 ${end.x} ${end.y}`}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            style={{ transition: "stroke var(--t-normal)" }}
          />
        )}
        {/* Label */}
        <text x={cx} y={cy + 6} textAnchor="middle" fill={color} fontSize="18" fontWeight="700">
          {pct}%
        </text>
      </svg>

      {/* Info */}
      <div>
        <div style={{ fontSize: "var(--text-xs)", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
          Session Confidence
        </div>
        <div style={{ fontSize: "var(--text-sm)", color: "var(--text2)" }}>
          Risk: <span style={{ color: "var(--text)", fontWeight: 600 }}>{riskLevel}</span>
        </div>
      </div>
    </div>
  );
}
