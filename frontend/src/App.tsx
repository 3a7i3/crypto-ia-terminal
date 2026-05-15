// ── App.tsx — Layout principal avec navigation par onglets ────────────────────

import React, { useState } from "react";
import "./tokens.css";
import { ModeBadge } from "./components/Badges";
import { GlobalView }     from "./views/GlobalView";
import { MarketLiveView } from "./views/MarketLiveView";
import { DecisionView }   from "./views/DecisionView";
import { PositionsView }  from "./views/PositionsView";
import { ScoresView }     from "./views/ScoresView";

// ── Types d'onglets ───────────────────────────────────────────────────────────

type Tab = "global" | "market" | "decisions" | "positions" | "scores";

const TABS: { id: Tab; label: string; glyph: string }[] = [
  { id: "global",    label: "Global",    glyph: "◉" },
  { id: "market",    label: "Marché",    glyph: "↗" },
  { id: "decisions", label: "Décisions", glyph: "≡" },
  { id: "positions", label: "Positions", glyph: "▣" },
  { id: "scores",    label: "Scores",    glyph: "◈" },
];

// ── Header ────────────────────────────────────────────────────────────────────

const Header: React.FC<{
  mode: "paper" | "testnet" | "live";
  lastUpdate: string;
  activeTab: Tab;
  onTabChange: (t: Tab) => void;
}> = ({ mode, lastUpdate, activeTab, onTabChange }) => (
  <header
    style={{
      background:   "var(--bg-card)",
      borderBottom: "1px solid var(--bg-border)",
      position: "sticky",
      top: 0,
      zIndex: 50,
    }}
  >
    <div className="flex items-center justify-between px-4 py-2.5">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-sm font-bold tracking-wide" style={{ color: "var(--text-pri)" }}>
          CRYPTO<span style={{ color: "var(--accent)" }}>AI</span>
        </span>
        <ModeBadge mode={mode} />
      </div>

      {/* Nav tabs */}
      <nav className="flex items-center gap-1">
        {TABS.map(tab => {
          const active = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 font-mono text-xs transition-colors"
              style={{
                borderRadius: "var(--r-chip)",
                background: active ? "var(--bg-hover)"  : "transparent",
                color:       active ? "var(--text-pri)"  : "var(--text-muted)",
                fontWeight:  active ? 600 : 400,
                border: "none",
                cursor: "pointer",
              }}
              aria-current={active ? "page" : undefined}
            >
              <span aria-hidden="true" style={{ color: active ? "var(--accent)" : undefined }}>
                {tab.glyph}
              </span>
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Last update */}
      <span className="font-mono text-[10px] hidden md:block" style={{ color: "var(--text-muted)" }}>
        {lastUpdate}
      </span>
    </div>
  </header>
);

// ── App ───────────────────────────────────────────────────────────────────────

const App: React.FC = () => {
  const [tab, setTab] = useState<Tab>("market");

  // Dans un vrai contexte, ces données viennent d'une API / websocket
  const mode: "paper" | "testnet" | "live" = "testnet";
  const lastUpdate = new Date().toLocaleTimeString("fr-FR");

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-dark)" }}>
      <Header mode={mode} lastUpdate={lastUpdate} activeTab={tab} onTabChange={setTab} />

      <main className="px-4 py-4">
        {tab === "global"    && <GlobalView />}
        {tab === "market"    && <MarketLiveView />}
        {tab === "decisions" && <DecisionView />}
        {tab === "positions" && <PositionsView />}
      </main>
    </div>
  );
};

export default App;
