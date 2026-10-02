import { useEffect, useRef } from "react";
import type { VoiceState } from "@/store/store";

/**
 * A living voice orb — the emotional center of the assistant, in the spirit of
 * the Gemini / ChatGPT voice UI. It renders on a canvas so the motion is smooth
 * and cheap: concentric rings that breathe when idle, ripple outward while
 * listening, swirl while thinking, and pulse in time while speaking.
 *
 * `level` (0..1) is the live mic amplitude while listening — it drives the
 * ripple radius so the orb reacts to your actual voice.
 */
export function VoiceOrb({
  state,
  level = 0,
  size = 132,
}: {
  state: VoiceState;
  level?: number;
  size?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const stateRef = useRef(state);
  const levelRef = useRef(level);
  const reduced = useRef(
    typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { levelRef.current = level; }, [level]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const baseR = size * 0.26;

    // Palette per state — hue drives the whole orb's mood.
    const palette: Record<VoiceState, [string, string]> = {
      idle:         ["#6c63ff", "#4a43cc"],
      listening:    ["#00d4aa", "#00a884"],
      transcribing: ["#00d4aa", "#00a884"],
      thinking:     ["#6c63ff", "#8b7dff"],
      speaking:     ["#38bdf8", "#6c63ff"],
    };

    let t = 0;
    const draw = () => {
      const s = stateRef.current;
      const lvl = levelRef.current;
      const [c1, c2] = palette[s];
      ctx.clearRect(0, 0, size, size);

      // --- outer aura ---
      const auraR =
        s === "listening" || s === "transcribing"
          ? baseR * (1.7 + lvl * 1.1 + Math.sin(t * 3) * 0.08)
          : s === "speaking"
          ? baseR * (1.55 + Math.abs(Math.sin(t * 6)) * 0.35)
          : s === "thinking"
          ? baseR * (1.6 + Math.sin(t * 2) * 0.12)
          : baseR * (1.45 + Math.sin(t * 1.2) * 0.06);

      const aura = ctx.createRadialGradient(cx, cy, baseR * 0.5, cx, cy, auraR);
      aura.addColorStop(0, hexA(c1, 0.28));
      aura.addColorStop(1, hexA(c1, 0));
      ctx.fillStyle = aura;
      ctx.beginPath();
      ctx.arc(cx, cy, auraR, 0, Math.PI * 2);
      ctx.fill();

      // --- thinking: rotating arc ---
      if (s === "thinking") {
        ctx.save();
        ctx.strokeStyle = hexA(c2, 0.8);
        ctx.lineWidth = 3;
        ctx.lineCap = "round";
        const a0 = t * 3;
        ctx.beginPath();
        ctx.arc(cx, cy, baseR * 1.32, a0, a0 + Math.PI * 1.1);
        ctx.stroke();
        ctx.restore();
      }

      // --- core sphere ---
      const coreR = baseR * (s === "speaking" ? 1 + Math.abs(Math.sin(t * 6)) * 0.12 : 1);
      const core = ctx.createRadialGradient(
        cx - baseR * 0.3,
        cy - baseR * 0.3,
        baseR * 0.1,
        cx,
        cy,
        coreR
      );
      core.addColorStop(0, c1);
      core.addColorStop(1, c2);
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
      ctx.fill();

      // --- specular highlight ---
      const hi = ctx.createRadialGradient(
        cx - coreR * 0.35,
        cy - coreR * 0.4,
        1,
        cx - coreR * 0.35,
        cy - coreR * 0.4,
        coreR * 0.7
      );
      hi.addColorStop(0, "rgba(255,255,255,0.5)");
      hi.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = hi;
      ctx.beginPath();
      ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
      ctx.fill();

      if (!reduced.current) t += 0.016;
      rafRef.current = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(rafRef.current);
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size, display: "block" }}
      aria-hidden="true"
    />
  );
}

function hexA(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${a})`;
}
