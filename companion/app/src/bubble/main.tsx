import React from "react";
import ReactDOM from "react-dom/client";
import "@/styles/tokens.css";
import { BubbleApp } from "./BubbleApp";
import { listen } from "@tauri-apps/api/event";
import { useGenesisStore } from "@/store/store";

// Bubble does NOT own the WS — it receives state from Panel via Tauri IPC
listen<{ type: string; payload: unknown }>("genesis://event", (ev) => {
  useGenesisStore.getState().handleEvent(ev.payload.type, ev.payload.payload);
}).catch(() => {
  // not fatal — bubble degrades gracefully if IPC fails
});

listen<{ connected: boolean }>("genesis://connection", (ev) => {
  useGenesisStore.getState().setConnected(ev.payload.connected);
}).catch(() => {});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BubbleApp />
  </React.StrictMode>
);
