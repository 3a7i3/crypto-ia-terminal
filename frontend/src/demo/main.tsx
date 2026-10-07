import React from "react";
import { createRoot } from "react-dom/client";
import App from "../App";
import { DemoContext } from "../components/DemoContext";
import { DemoCharts } from "./DemoCharts";
import "./demo.css";

// This entry is never imported by main.tsx; no PWA/cache or runtime connection.
const selected = document.cookie.match(/(?:^|; )ux-demo-scenario=([^;]+)/)?.[1] ?? "synthetic";
createRoot(document.getElementById("root")!).render(<React.StrictMode>
  <aside className="demo-banner" role="status">
    <strong>DÉMONSTRATION · DONNÉES FICTIVES</strong>
    <label>Scénario <select aria-label="Scénario de démonstration" value={selected} onChange={(event) => {
      document.cookie = `ux-demo-scenario=${event.target.value}; path=/; SameSite=Strict`;
      window.location.reload();
    }}><option value="synthetic">Publication synthétique</option><option value="stale">Sources anciennes</option><option value="missing">Sources indisponibles</option></select></label>
    <span>Aucune observation du VPS · courbes indépendantes des snapshots.</span>
  </aside>
  <DemoContext.Provider value={<DemoCharts />}><App /></DemoContext.Provider>
</React.StrictMode>);
