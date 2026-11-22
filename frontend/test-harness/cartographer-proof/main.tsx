// Harnais synthétique : rend uniquement la vue Système du registre d'agents.
import React from "react";
import { createRoot } from "react-dom/client";
import { AgentRegistryView } from "../../src/views/AgentRegistryView";
import "../../src/tokens.css";
import "../../src/workspace.css";
import { applyTheme, readTheme } from "../../src/lib/theme";

applyTheme(readTheme());

createRoot(document.getElementById("root")!).render(
  <main style={{ padding: "16px" }}>
    <AgentRegistryView />
  </main>,
);
