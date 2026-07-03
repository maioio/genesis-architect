import { useRef, useState } from "react";
import { useGenesisStore } from "@/store/store";
import { sendVoiceStart, sendVoiceEnd } from "@/actions/approvals";

type RecordState = "idle" | "recording" | "processing";

// Encode raw PCM Float32Array samples to a minimal WAV Blob
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const dataSize = samples.length * 2; // 16-bit samples
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);          // PCM chunk size
  view.setUint16(20, 1, true);           // PCM format
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);

  // Convert Float32 → Int16
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export function VoicePTT() {
  const voiceState = useGenesisStore((s) => s.voiceState);
  const transcript = useGenesisStore((s) => s.voiceTranscript);
  const [recState, setRecState] = useState<RecordState>("idle");
  const [error, setError] = useState<string | null>(null);

  const mediaRef   = useRef<MediaStream | null>(null);
  const ctxRef     = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const chunksRef  = useRef<Float32Array[]>([]);

  const isRecording = recState === "recording";

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext({ sampleRate: 16000 });
      const source = ctx.createMediaStreamSource(stream);
      // ScriptProcessorNode: deprecated but universally supported in WebView
      const processor = ctx.createScriptProcessor(4096, 1, 1);

      chunksRef.current = [];
      processor.onaudioprocess = (ev) => {
        const pcm = ev.inputBuffer.getChannelData(0);
        chunksRef.current.push(new Float32Array(pcm));
      };

      source.connect(processor);
      processor.connect(ctx.destination);

      mediaRef.current = stream;
      ctxRef.current = ctx;
      processorRef.current = processor;

      sendVoiceStart();
      setRecState("recording");
    } catch (err) {
      setError("Microphone access denied");
    }
  }

  async function stopRecording() {
    setRecState("processing");

    // Tear down audio graph
    processorRef.current?.disconnect();
    ctxRef.current?.close();
    mediaRef.current?.getTracks().forEach((t) => t.stop());

    // Combine all PCM chunks into one WAV
    const allChunks = chunksRef.current;
    chunksRef.current = [];
    const totalLen = allChunks.reduce((n, c) => n + c.length, 0);
    const merged = new Float32Array(totalLen);
    let pos = 0;
    for (const c of allChunks) {
      merged.set(c, pos);
      pos += c.length;
    }

    const sampleRate = ctxRef.current?.sampleRate ?? 16000;
    const wavBlob = encodeWav(merged, sampleRate);

    // Convert to base64
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      const b64 = dataUrl.split(",")[1];
      sendVoiceEnd(b64);
      setRecState("idle");
    };
    reader.onerror = () => {
      setError("Failed to encode audio");
      setRecState("idle");
    };
    reader.readAsDataURL(wavBlob);
  }

  function handlePress() {
    if (recState === "idle") startRecording();
    else if (recState === "recording") stopRecording();
  }

  const buttonLabel =
    recState === "recording"   ? "■ Stop"
    : recState === "processing" ? "…"
    : voiceState === "transcribing" ? "Transcribing…"
    : voiceState === "speaking"     ? "Speaking…"
    : "🎤 Speak";

  const buttonColor =
    recState === "recording" ? "var(--danger)"
    : voiceState === "speaking" ? "var(--thinking)"
    : "var(--accent)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <button
        onClick={handlePress}
        disabled={recState === "processing" || voiceState === "transcribing" || voiceState === "speaking"}
        style={{
          background: buttonColor,
          border: "none",
          borderRadius: "var(--r-md)",
          color: "#fff",
          cursor: recState === "processing" ? "wait" : "pointer",
          fontSize: "var(--text-sm)",
          fontWeight: 600,
          padding: "8px 14px",
          transition: "background var(--t-normal)",
          width: "100%",
          opacity: recState === "processing" ? 0.6 : 1,
        }}
        aria-label={isRecording ? "Stop recording" : "Start voice input"}
      >
        {buttonLabel}
      </button>

      {/* Live transcript */}
      {transcript && (
        <p
          style={{
            margin: 0,
            fontSize: "var(--text-xs)",
            color: "var(--text-muted)",
            fontStyle: "italic",
            lineHeight: 1.4,
            padding: "4px 6px",
            background: "var(--surface-raised)",
            borderRadius: "var(--r-sm)",
          }}
        >
          {transcript}
        </p>
      )}

      {/* Recording pulse indicator */}
      {recState === "recording" && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: "var(--text-xs)",
            color: "var(--danger)",
          }}
        >
          <div
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "var(--danger)",
              animation: "pulse-blocked 1s ease-in-out infinite",
            }}
          />
          Recording…
        </div>
      )}

      {error && (
        <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--danger)" }}>
          {error}
        </p>
      )}
    </div>
  );
}
