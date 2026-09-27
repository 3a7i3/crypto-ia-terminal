import React from "react";
import { Link, Outlet } from "react-router-dom";

export const DirectionShell: React.FC = () => (
  <div className="operator-shell direction-shell" data-testid="direction-shell">
    <a className="direction-skip-link" href="#direction-content">Aller au contenu Direction</a>
    <header className="direction-header" aria-label="En-tête Direction">
      <nav className="direction-return-nav" aria-label="Retour à la surface de trading PAPER">
        <Link className="direction-return-link" to="/paper-live" data-testid="return-paper-live">
          <span aria-hidden="true">←</span>
          <span>Retour à PAPER LIVE</span>
        </Link>
      </nav>
      <div className="direction-identity">
        <div className="direction-product-mark" aria-hidden="true">D</div>
        <div>
          <div className="direction-eyebrow">CRYPTO AI TERMINAL · SURFACE PROPRIÉTAIRE</div>
          <h1>DIRECTION</h1>
          <p>Synthèse, gouvernance et décisions humaines</p>
        </div>
      </div>
      <aside className="direction-authority-strip" aria-label="Frontière d’autorité Direction" data-testid="direction-authority-strip">
        <span>PRÉSENTATION</span>
        <span>LECTURE SEULE</span>
        <span>AUCUNE AUTORITÉ PAPER</span>
      </aside>
    </header>
    <main className="direction-main" id="direction-content" tabIndex={-1}><Outlet /></main>
  </div>
);
