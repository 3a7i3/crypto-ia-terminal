// ── App.tsx — read-only operator cockpit ───────────────────────────────────
// WEB-RL-01 separates five navigation surfaces and three scientific domains:
// MARKET OBSERVATORY / PAPER SCIENCE / RESEARCH LAB.
// Existing producer authority remains unchanged.

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
import { PplComparisonView } from "./views/PplComparisonView";
import { FinancialReconciliationView } from "./views/FinancialReconciliationView";
import { ResearchLabView } from "./views/ResearchLabView";
import { NotExposedView } from "./views/NotExposedView";

type Domain = "overview" | "market" | "paper" | "research" | "system";
type PaperView = "portfolio" | "decisions" | "ppl" | "finance";
type SystemSubview = "health" | "scores";

const DOMAINS: { id: Domain; label: string; glyph: string; testId: string }[] = [
  { id: "overview", label: "Overview", glyph: "◉", testId: "tab-overview" },
  { id: "market", label: "Market Observatory", glyph: "↗", testId: "tab-market" },
  { id: "paper", label: "Paper Science", glyph: "▣", testId: "tab-paper" },
  { id: "research", label: "Research Lab", glyph: "◇", testId: "tab-research" },
  { id: "system", label: "System / Governance", glyph: "⚙", testId: "tab-system" },
];

const PAPER_VIEWS: { id: PaperView; label: string; glyph: string; testId: string }[] = [
  { id: "portfolio", label: "Portfolio", glyph: "▣", testId: "tab-portfolio" },
  { id: "decisions", label: "Decisions", glyph: "≡", testId: "tab-decisions" },
  { id: "ppl", label: "PPL Compare", glyph: "⇄", testId: "tab-ppl" },
  { id: "finance", label: "Financial", glyph: "¤", testId: "tab-finance" },
];

const Header: React.FC<{
  mode: string | null | undefined;
  lastFetchedAt: number | null;
  activeDomain: Domain;
  onDomainChange: (domain: Domain) => void;
}> = ({ mode, lastFetchedAt, activeDomain, onDomainChange }) => (
  <header className="operator-header">
    <div className="operator-header-row">
      <div className="operator-brand-group">
        <span className="operator-brand">
          CRYPTO<span className="operator-brand-accent">AI</span>
        </span>
        {activeDomain === "market" ? (
          <span className="domain-badge domain-badge-market" data-testid="market-domain-badge">
            <span className="domain-dot" aria-hidden="true" />
            MARKET OBSERVATORY
          </span>
        ) : activeDomain === "paper" ? (
          <span className="domain-badge domain-badge-paper" data-testid="paper-domain-badge">
            <span className="domain-dot" aria-hidden="true" />
            PAPER SCIENCE
          </span>
        ) : activeDomain === "research" ? (
          <span className="domain-badge domain-badge-research" data-testid="research-header-domain-badge">
            <span className="domain-dot" aria-hidden="true" />
            RESEARCH LAB
          </span>
        ) : activeDomain === "system" ? (
          <span className="domain-badge domain-badge-system" data-testid="system-domain-badge">
            <span className="domain-dot" aria-hidden="true" />
            SYSTEM
          </span>
        ) : (
          <ModeBadge mode={mode} />
        )}
      </div>

      <nav className="operator-nav" aria-label="Operator domains">
        {DOMAINS.map((domain) => {
          const active = domain.id === activeDomain;
          return (
            <button
              key={domain.id}
              onClick={() => onDomainChange(domain.id)}
              className={`operator-tab${active ? " operator-tab-active" : ""}`}
              aria-current={active ? "page" : undefined}
              data-testid={domain.testId}
            >
              <span className="operator-tab-glyph" aria-hidden="true">{domain.glyph}</span>
              <span>{domain.label}</span>
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

const PaperSubnav: React.FC<{
  active: PaperView;
  onChange: (view: PaperView) => void;
}> = ({ active, onChange }) => (
  <nav className="operator-subnav" aria-label="Paper Science views" data-testid="paper-subnav">
    {PAPER_VIEWS.map((view) => (
      <button
        key={view.id}
        onClick={() => onChange(view.id)}
        className={`operator-subtab${active === view.id ? " operator-subtab-active" : ""}`}
        data-testid={view.testId}
      >
        <span aria-hidden="true">{view.glyph}</span>
        <span>{view.label}</span>
      </button>
    ))}
  </nav>
);

const PaperBanner: React.FC = () => (
  <div className="paper-domain-banner" data-testid="paper-domain-banner">
    PAPER SCIENCE · ACTIVE EXPERIMENT · NOT REAL MONEY
  </div>
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

const PplCanonicalContext: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "success") return null;
  const summary = state.status === "loading"
    ? "Canonical advisor context loading"
    : state.status === "api_error"
      ? `Canonical advisor: ${state.error.error_code ?? "UNRESOLVED"}`
      : "Canonical advisor: DISCONNECTED";

  return (
    <div className="market-domain-context" data-testid="ppl-canonical-context">
      {summary} · PPL comparison remains an independent observational domain.
    </div>
  );
};

const App: React.FC = () => {
  const [domain, setDomain] = useState<Domain>("overview");
  const [paperView, setPaperView] = useState<PaperView>("portfolio");
  const [systemSubview, setSystemSubview] = useState<SystemSubview>("health");
  const snapshotState = useOperatorSnapshot();

  const activeSnapshot = snapshotState.status === "success" ? snapshotState.snapshot : null;
  const lastFetchedAt = snapshotState.status === "success"
    ? snapshotState.fetchedAt
    : snapshotState.lastSuccess?.fetchedAt ?? null;
  const mode = activeSnapshot?.portfolio.mode;

  const independentDomainActive =
    domain === "market" ||
    domain === "research" ||
    (domain === "paper" && (paperView === "ppl" || paperView === "finance"));

  const canonicalRequired =
    domain === "overview" ||
    domain === "system" ||
    (domain === "paper" && (paperView === "portfolio" || paperView === "decisions"));

  return (
    <div className="operator-shell">
      <Header
        mode={mode}
        lastFetchedAt={lastFetchedAt}
        activeDomain={domain}
        onDomainChange={setDomain}
      />
      {!independentDomainActive && <SnapshotStatusBanner state={snapshotState} />}

      <main className="operator-main">
        {domain === "market" ? (
          <>
            <MarketCanonicalContext state={snapshotState} />
            <MarketView />
          </>
        ) : domain === "research" ? (
          <ResearchLabView />
        ) : domain === "paper" ? (
          <>
            <PaperBanner />
            <PaperSubnav active={paperView} onChange={setPaperView} />
            {paperView === "ppl" ? (
              <>
                <PplCanonicalContext state={snapshotState} />
                <PplComparisonView />
              </>
            ) : paperView === "finance" ? (
              <FinancialReconciliationView />
            ) : !activeSnapshot ? (
              <div className="canonical-unresolved" data-testid="no-snapshot">
                Canonical snapshot unavailable — PAPER SCIENCE is UNRESOLVED until a validated snapshot is available.
              </div>
            ) : paperView === "portfolio" ? (
              <PortfolioView snapshot={activeSnapshot} />
            ) : (
              <DecisionsView snapshot={activeSnapshot} />
            )}
          </>
        ) : canonicalRequired && !activeSnapshot ? (
          <div className="canonical-unresolved" data-testid="no-snapshot">
            Canonical snapshot unavailable — this domain is UNRESOLVED until a validated snapshot is available.
          </div>
        ) : domain === "overview" && activeSnapshot ? (
          <OverviewView snapshot={activeSnapshot} />
        ) : domain === "system" && activeSnapshot ? (
          <>
            <nav className="operator-subnav" aria-label="System / Governance views">
              <button
                className={`operator-subtab${systemSubview === "health" ? " operator-subtab-active" : ""}`}
                onClick={() => setSystemSubview("health")}
                data-testid="tab-system-health"
              >
                System Health
              </button>
              <button
                className={`operator-subtab${systemSubview === "scores" ? " operator-subtab-active" : ""}`}
                onClick={() => setSystemSubview("scores")}
                data-testid="tab-scores"
              >
                Scores
              </button>
            </nav>
            {systemSubview === "health" ? (
              <SystemView snapshot={activeSnapshot} />
            ) : (
              <NotExposedView title="Scores" />
            )}
          </>
        ) : null}
      </main>
    </div>
  );
};

export default App;
