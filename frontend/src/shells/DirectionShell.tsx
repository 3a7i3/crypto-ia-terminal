import React from "react";
import { Link, Outlet } from "react-router-dom";

import { SpaceNavigation } from "../components/SpaceNavigation";

export const DirectionShell: React.FC = () => (
  <div className="operator-shell direction-shell" data-testid="direction-shell">
    <a className="direction-skip-link" href="#direction-content">Aller au contenu Direction</a>
    <SpaceNavigation />
    <header className="direction-header" aria-label="En-tête Direction">
      <nav className="direction-return-nav" aria-label="Retour à la surface de trading PAPER">
        <Link className="direction-return-link" to="/paper-live" data-testid="return-paper-live">
          <span aria-hidden="true">←</span>
          <span>Données PAPER</span>
        </Link>
      </nav>
      <div className="direction-identity">
        <div className="direction-product-mark" aria-hidden="true">◉</div>
        <div>
          <div className="direction-eyebrow">MACHINE · SYNTHÈSE OPÉRATEUR</div>
          <h1>Machine</h1>
          <p>État, portefeuille et marché</p>
        </div>
      </div>
      <details className="direction-authority-details"><summary>Périmètre de lecture</summary><aside className="direction-authority-strip" aria-label="Frontière d’autorité Direction" data-testid="direction-authority-strip">
        <span>PRÉSENTATION</span>
        <span>LECTURE SEULE</span>
        <span>AUCUNE AUTORITÉ PAPER</span>
      </aside></details>
    </header>
    <main className="direction-main" id="direction-content" tabIndex={-1}><Outlet /></main>
  </div>
);
