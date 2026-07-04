import React from "react";
import ReactDOM from "react-dom/client";
import "@/styles/tokens.css";
import { DockApp } from "./DockApp";

// Set document direction from UI language so RTL (Hebrew) lays out correctly.
const lang = (navigator.language || "en").toLowerCase();
document.documentElement.lang = lang.startsWith("he") ? "he" : "en";
document.documentElement.dir = lang.startsWith("he") ? "rtl" : "ltr";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DockApp />
  </React.StrictMode>
);
