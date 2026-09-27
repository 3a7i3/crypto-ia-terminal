import React from "react";
import { Link, Outlet } from "react-router-dom";

export const ResearchShell: React.FC = () => (
  <div className="operator-shell" data-testid="research-shell">
    <header className="operator-header">
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
    <main className="operator-main"><Outlet /></main>
  </div>
);
