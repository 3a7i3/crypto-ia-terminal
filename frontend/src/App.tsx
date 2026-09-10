// ── App.tsx — read-only operator cockpit, single coherent snapshot source ──

import React, { useState } from "react";
import "./tokens.css";
import { ModeBadge } from "./components/ModeBadge";
import { SnapshotStatusBanner } from "./components/SnapshotStatusBanner";
import { useOperatorSnapshot } from "./lib/snapshotClient";
import { OverviewView } from "./views/OverviewView";
import { PortfolioView } from "./views/PortfolioView";
import { DecisionsView } from "./views/DecisionsView";
import { SystemView } from "./views/SystemView";
import { NotExposedView } from "./views/NotExposedView";

type Tab = "overview" | "portfolio" | "decisions" | "system" | "market" | "scores";

const TABS: { id: Tab; label: string; glyph: string }[] = [
  { id: "overview", label: "Overview", glyph: "◉" },
  { id: "portfolio", label: "Portfolio", glyph: "▣" },
  { id: "decisions", label: "Decisions", glyph: "≡" },
  { id: "system", label: "System", glyph: "⚙" },
  { id: "market", label: "Market", glyph: "↗" },
  { id: "scores", label: "Scores", glyph: "◈" },
];

const Header: React.FC<{
  mode: string | null | undefined;
  lastFetchedAt: number | null;
  activeTab: Tab;
  onTabChange: (t: Tab) => void;
}> = ({ mode, lastFetchedAt, activeTab, onTabChange }) => (
  <header
    style={{ background: "var(--bg-card)", borderBottom: "1px solid var(--bg-border)", position: "sticky", top: 0, zIndex: 50 }}
  >
    <div className="flex items-center justify-between px-4 py-2.5">
      <div className="flex items-center gap-3">
        <span className="font-mono text-sm font-bold tracking-wide" style={{ color: "var(--text-pri)" }}>
          CRYPTO<span style={{ color: "var(--accent)" }}>AI</span>
        </span>
        <ModeBadge mode={mode} />
      </div>

      <nav className="flex items-center gap-1">
        {TABS.map((tab) => {
          const active = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 font-mono text-xs transition-colors"
              style={{
                borderRadius: "var(--r-chip)",
                background: active ? "var(--bg-hover)" : "transparent",
                color: active ? "var(--text-pri)" : "var(--text-muted)",
                fontWeight: active ? 600 : 400,
                border: "none",
                cursor: "pointer",
              }}
              aria-current={active ? "page" : undefined}
              data-testid={`tab-${tab.id}`}
            >
              <span aria-hidden="true" style={{ color: active ? "var(--accent)" : undefined }}>
                {tab.glyph}
              </span>
              {tab.label}
            </button>
          );
        })}
      </nav>

      <span className="font-mono text-[10px] hidden md:block" style={{ color: "var(--text-muted)" }} data-testid="last-fetch">
        {lastFetchedAt ? new Date(lastFetchedAt).toLocaleTimeString() : "—"}
      </span>
    </div>
  </header>
);

const App: React.FC = () => {
  const [tab, setTab] = useState<Tab>("overview");
  const snapshotState = useOperatorSnapshot();

  const activeSnapshot = snapshotState.status === "success" ? snapshotState.snapshot : null;
  const lastFetchedAt = snapshotState.status === "success" ? snapshotState.fetchedAt : snapshotState.lastSuccess?.fetchedAt ?? null;
  const mode = activeSnapshot?.portfolio.mode;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-dark)" }}>
      <Header mode={mode} lastFetchedAt={lastFetchedAt} activeTab={tab} onTabChange={setTab} />
      <SnapshotStatusBanner state={snapshotState} />

      <main className="px-4 py-4">
        {!activeSnapshot ? (
          <div className="font-mono text-xs px-2 py-6" style={{ color: "var(--text-muted)" }} data-testid="no-snapshot">
            No successful snapshot available yet — panels render only from a validated canonical snapshot.
          </div>
        ) : (
          <>
            {tab === "overview" && <OverviewView snapshot={activeSnapshot} />}
            {tab === "portfolio" && <PortfolioView snapshot={activeSnapshot} />}
            {tab === "decisions" && <DecisionsView snapshot={activeSnapshot} />}
            {tab === "system" && <SystemView snapshot={activeSnapshot} />}
            {tab === "market" && <NotExposedView title="Market" />}
            {tab === "scores" && <NotExposedView title="Scores" />}
          </>
        )}
      </main>
    </div>
  );
};

export default App;
