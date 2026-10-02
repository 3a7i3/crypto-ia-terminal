import React from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { SpaceNavigation } from "../components/SpaceNavigation";
import { ModeBadge } from "../components/ModeBadge";
import { SnapshotStatusBanner } from "../components/SnapshotStatusBanner";
import { useOperatorSnapshot, type SnapshotState } from "../lib/snapshotClient";
import type { OperatorSnapshot } from "../types";

export interface PaperLiveOutletContext {
  snapshotState: SnapshotState;
  activeSnapshot: OperatorSnapshot | null;
}

const mainLinks = [
  { to: "/paper-live", label: "Vue générale", glyph: "◉", testId: "tab-overview", end: true },
  { to: "/paper-live/market", label: "CryptoRadar", glyph: "↗", testId: "tab-market" },
  { to: "/paper-live/portfolio", label: "Portefeuille", glyph: "▣", testId: "tab-paper" },
  { to: "/paper-live/system", label: "Système", glyph: "⚙", testId: "tab-system" },
];

const paperLinks = [
  { to: "/paper-live/portfolio", label: "Portefeuille", testId: "tab-portfolio" },
  { to: "/paper-live/burn-in", label: "Burn-in", testId: "tab-burn-in" },
  { to: "/paper-live/decisions", label: "Décisions", testId: "tab-decisions" },
  { to: "/paper-live/lifecycle", label: "Lifecycle PPL", testId: "tab-ppl" },
  { to: "/paper-live/finance", label: "Finance", testId: "tab-finance" },
  { to: "/paper-live/events", label: "Événements", testId: "tab-events" },
];

const PAPER_PATHS = new Set(paperLinks.map((link) => link.to));

function domain(pathname: string): "market" | "paper" | "system" | "overview" {
  if (pathname === "/paper-live/market") return "market";
  if (pathname === "/paper-live/system" || pathname === "/paper-live/scores") return "system";
  if (PAPER_PATHS.has(pathname)) return "paper";
  return "overview";
}

export const PaperLiveShell: React.FC = () => {
  const location = useLocation();
  const snapshotState = useOperatorSnapshot();
  const activeSnapshot = snapshotState.status === "success" ? snapshotState.snapshot : null;
  const lastFetchedAt = snapshotState.status === "success"
    ? snapshotState.fetchedAt
    : snapshotState.lastSuccess?.fetchedAt ?? null;
  const activeDomain = domain(location.pathname);
  const independentRoute = activeDomain === "market" ||
    location.pathname === "/paper-live/lifecycle" ||
    location.pathname === "/paper-live/burn-in" ||
    location.pathname === "/paper-live/finance";

  return (
    <div className="operator-shell" data-testid="paper-live-shell">
      <header className="operator-header">
        <SpaceNavigation />
        <div className="operator-header-row">
          <div className="operator-brand-group">
            <span className="operator-brand">CRYPTO<span className="operator-brand-accent">AI</span></span>
            {activeDomain === "market" ? (
              <span className="domain-badge domain-badge-market" data-testid="market-domain-badge">
                <span className="domain-dot" aria-hidden="true" /> MARKET OBSERVATORY
              </span>
            ) : activeDomain === "paper" ? (
              <span className="domain-badge domain-badge-paper" data-testid="paper-domain-badge">
                <span className="domain-dot" aria-hidden="true" /> PAPER LIVE · PAPER SCIENCE
              </span>
            ) : activeDomain === "system" ? (
              <span className="domain-badge domain-badge-system" data-testid="system-domain-badge">
                <span className="domain-dot" aria-hidden="true" /> SYSTEM
              </span>
            ) : <ModeBadge mode={activeSnapshot?.portfolio.mode} />}
          </div>
          <nav className="operator-nav" aria-label="Espaces opérateur">
            {mainLinks.map((link) => (
              <NavLink key={link.to} to={link.to} end={link.end}
                className={({ isActive }) => `operator-tab${isActive ? " operator-tab-active" : ""}`}
                data-testid={link.testId}>
                <span className="operator-tab-glyph" aria-hidden="true">{link.glyph}</span><span>{link.label}</span>
              </NavLink>
            ))}
            <NavLink className="direction-open-link" to="/direction" data-testid="open-direction">
              Ouvrir Direction →
            </NavLink>
          </nav>
          <span className="operator-last-fetch" data-testid="last-fetch">
            {lastFetchedAt ? new Date(lastFetchedAt).toLocaleTimeString() : "—"}
          </span>
        </div>
      </header>
      {!independentRoute && <SnapshotStatusBanner state={snapshotState} />}
      <main className="operator-main">
        {activeDomain === "paper" && <>
          <div className="paper-domain-banner" data-testid="paper-domain-banner">
            PAPER LIVE · DONNÉES MARCHÉ RÉELLES · DÉCISIONS MACHINE RÉELLES · EXÉCUTION PAPER · NOT REAL MONEY
          </div>
          <nav className="operator-subnav" aria-label="Vues PAPER LIVE" data-testid="paper-subnav">
            {paperLinks.map((link) => (
              <NavLink key={link.to} to={link.to}
                className={({ isActive }) => `operator-subtab${isActive ? " operator-subtab-active" : ""}`}
                data-testid={link.testId}>{link.label}</NavLink>
            ))}
          </nav>
        </>}
        {activeDomain === "system" && <nav className="operator-subnav" aria-label="Vues Système / Gouvernance">
          <NavLink to="/paper-live/system" className={({ isActive }) => `operator-subtab${isActive ? " operator-subtab-active" : ""}`} data-testid="tab-system-health">System Health</NavLink>
          <NavLink to="/paper-live/scores" className={({ isActive }) => `operator-subtab${isActive ? " operator-subtab-active" : ""}`} data-testid="tab-scores">Scores</NavLink>
        </nav>}
        <Outlet context={{ snapshotState, activeSnapshot } satisfies PaperLiveOutletContext} />
      </main>
    </div>
  );
};
