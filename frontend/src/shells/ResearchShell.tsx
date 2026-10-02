import React from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { SpaceNavigation } from "../components/SpaceNavigation";

export const ResearchShell: React.FC = () => (
  <div className="operator-shell" data-testid="research-shell">
    <header className="operator-header">
      <SpaceNavigation />
      <div className="operator-header-row research-shell-header">
        <div className="operator-brand-group">
          <span className="operator-brand">CRYPTO<span className="operator-brand-accent">AI</span></span>
          <span className="domain-badge domain-badge-research" data-testid="research-header-domain-badge">
            <span className="domain-dot" aria-hidden="true" /> RESEARCH NON-AUTORITAIRE
          </span>
        </div>
        <nav className="operator-nav" aria-label="Navigation Research">
          <Link className="operator-tab" to="/paper-live" data-testid="tab-overview">← PAPER LIVE</Link>
          <Link className="direction-open-link" to="/direction">Ouvrir Direction →</Link>
        </nav>
      </div>
    </header>
    <main className="operator-main">
      <div className="workspace-intro"><span className="workspace-eyebrow">LABORATOIRE QUANTITATIF</span><h1>Comprendre les résultats de la recherche</h1><p>Évaluations, stratégies et preuves, séparées du portefeuille PAPER.</p></div>
      <nav className="operator-subnav" aria-label="Vues Laboratoire">
        <NavLink to="/research" end className={({ isActive }) => `operator-subtab${isActive ? " operator-subtab-active" : ""}`}>Évaluations & preuves</NavLink>
        <NavLink to="/research/strategies" className={({ isActive }) => `operator-subtab${isActive ? " operator-subtab-active" : ""}`} data-testid="lab-strategies-link">Stratégies</NavLink>
      </nav>
      <Outlet />
    </main>
  </div>
);
