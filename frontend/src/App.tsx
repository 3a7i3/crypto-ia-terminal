// ── App.tsx — read-only operator cockpit ───────────────────────────────────
// Overview/Portfolio/Decisions/System share one coherent canonical advisor
// snapshot. WEB-01-MARKET is the explicit O-02W-B §12 cross-process exception:
// MarketView consumes only the separate read-only CryptoRadar MARKET artifact.

import React, { useState } from "react";
import "./tokens.css";
import "./operator.css";
import { ModeBadge } from "./components/ModeBadge";
import { SnapshotStatusBanner } from "./components/SnapshotStatusBanner";
import { useOperatorSnapshot, type SnapshotState } from "./lib/snapshotClient";
import { OverviewView } from "./views/OverviewView";
import { PortfolioView } from "./views/PortfolioView";
import { DecisionsView } from "./views/DecisionsView";
import { SystemView } from "./views/SystemView";
import { MarketView } from "./views/MarketView";
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
  <header className="operator-header">
    <div className="operator-header-row">
      <div className="operator-brand-group">
        <span className="operator-brand">
          CRYPTO<span className="operator-brand-accent">AI</span>
        </span>
        {activeTab === "market" ? (
          <span className="domain-badge domain-badge-market" data-testid="market-domain-badge">
            <span className="domain-dot" aria-hidden="true" />
            MARKET
          </span>
        ) : (
          <ModeBadge mode={mode} />
        )}
      </div>

      <nav className="operator-nav" aria-label="Operator views">
        {TABS.map((tab) => {
          const active = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`operator-tab${active ? " operator-tab-active" : ""}`}
              aria-current={active ? "page" : undefined}
              data-testid={`tab-${tab.id}`}
            >
              <span className="operator-tab-glyph" aria-hidden="true">
                {tab.glyph}
              </span>
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>

      <span className="operator-last-fetch" data-testid="last-fetch">
        {lastFetchedAt ? new Date(lastFetchedAt).toLocaleTimeString() : "—"}
      </span>
    </div>
  </header>
);

const MarketCanonicalContext: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "success") return null;

  if (state.status === "loading") {
    return (
      <div className="market-domain-context" data-testid="market-canonical-context">
        Canonical advisor context loading · MARKET telemetry is sourced independently.
      </div>
    );
  }

  const summary = state.status === "api_error"
    ? state.error.error_code === "SNAPSHOT_MISSING"
      ? "Canonical advisor: UNRESOLVED · SNAPSHOT_MISSING"
      : `Canonical advisor API error · ${state.error.error_code ?? "UNKNOWN_ERROR"}`
    : "Canonical advisor: DISCONNECTED";
  const detail = state.status === "api_error"
    ? state.error.error_message ?? "no error message supplied"
    : state.message;

  return (
    <details className="market-domain-context" data-testid="market-canonical-context">
      <summary>{summary} · MARKET remains a separate observational domain</summary>
      <div className="market-domain-context-detail">{detail}</div>
    </details>
  );
};

const App: React.FC = () => {
  const [tab, setTab] = useState<Tab>("overview");
  const snapshotState = useOperatorSnapshot();

  const activeSnapshot = snapshotState.status === "success" ? snapshotState.snapshot : null;
  const lastFetchedAt = snapshotState.status === "success" ? snapshotState.fetchedAt : snapshotState.lastSuccess?.fetchedAt ?? null;
  const mode = activeSnapshot?.portfolio.mode;
  const marketActive = tab === "market";

  return (
    <div className="operator-shell">
      <Header mode={mode} lastFetchedAt={lastFetchedAt} activeTab={tab} onTabChange={setTab} />
      {!marketActive && <SnapshotStatusBanner state={snapshotState} />}

      <main className="operator-main">
        {marketActive ? (
          <>
            <MarketCanonicalContext state={snapshotState} />
            <MarketView />
          </>
        ) : !activeSnapshot ? (
          <div
            className="canonical-unresolved"
            data-testid="no-snapshot"
          >
            Canonical snapshot unavailable — this domain is UNRESOLVED until a validated snapshot is available.
          </div>
        ) : (
          <>
            {tab === "overview" && <OverviewView snapshot={activeSnapshot} />}
            {tab === "portfolio" && <PortfolioView snapshot={activeSnapshot} />}
            {tab === "decisions" && <DecisionsView snapshot={activeSnapshot} />}
            {tab === "system" && <SystemView snapshot={activeSnapshot} />}
            {tab === "scores" && <NotExposedView title="Scores" />}
          </>
        )}
      </main>
    </div>
  );
};

export default App;
