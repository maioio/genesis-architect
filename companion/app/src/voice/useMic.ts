import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Microphone access + live amplitude metering for the voice orb.
 *
 * The heavy lifting — speech-to-text, VAD end-of-turn, barge-in — runs in the
 * Python backend (faster-whisper + webrtcvad). This hook's job is the UI side:
 * open the mic so the OS shows the "in use" indicator, publish a smoothed 0..1
 * level so the orb reacts to the user's voice, and expose start/stop.
 */
export function useMic() {
  const [level, setLevel] = useState(0);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number>(0);

  const stop = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
    setLevel(0);
    setActive(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);

      let smooth = 0;
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / data.length); // 0..~1
        smooth = smooth * 0.8 + Math.min(1, rms * 3) * 0.2;
        setLevel(smooth);
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
      setActive(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "microphone unavailable");
      setActive(false);
    }
  }, []);

  useEffect(() => () => stop(), [stop]);

  return { level, active, error, start, stop };
}
