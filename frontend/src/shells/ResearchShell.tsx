import React from "react";
import { NavLink, Outlet } from "react-router-dom";

import { SpaceNavigation } from "../components/SpaceNavigation";

export const ResearchShell: React.FC = () => (
  <div className="operator-shell" data-testid="research-shell">
    <header className="operator-header">
      <SpaceNavigation />
      <div className="operator-header-row research-shell-header">
        <div className="operator-brand-group">
          <span className="operator-brand">CRYPTO<span className="operator-brand-accent">AI</span></span>
          <span className="domain-badge domain-badge-research" data-testid="research-header-domain-badge">
            <span className="domain-dot" aria-hidden="true" /> RECHERCHE NON AUTORITAIRE
          </span>
        </div>

      </div>
    </header>
    <main className="operator-main">
      <div className="workspace-intro"><h1>Laboratoire quantitatif</h1></div>
      <nav className="operator-subnav" aria-label="Vues Laboratoire">
        <NavLink to="/research" end className={({ isActive }) => `operator-subtab${isActive ? " operator-subtab-active" : ""}`}>Évaluations & preuves</NavLink>
        <NavLink to="/research/strategies" className={({ isActive }) => `operator-subtab${isActive ? " operator-subtab-active" : ""}`} data-testid="lab-strategies-link">Stratégies</NavLink>
      </nav>
      <Outlet />
    </main>
  </div>
);
