import React from "react";
import ReactDOM from "react-dom/client";
import "@/styles/tokens.css";
import { PanelApp } from "./PanelApp";
import { wsClient } from "@/ws/client";

// Panel owns the WebSocket connection
void wsClient.connect();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PanelApp />
  </React.StrictMode>
);
