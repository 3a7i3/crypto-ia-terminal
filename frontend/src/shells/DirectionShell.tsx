import React from "react";
import { Link, Outlet } from "react-router-dom";

export const DirectionShell: React.FC = () => (
  <div className="operator-shell direction-shell" data-testid="direction-shell">
    <header className="direction-header">
      <Link className="direction-return-link" to="/paper-live" data-testid="return-paper-live">← Retour à PAPER LIVE</Link>
      <div><div className="direction-eyebrow">CRYPTO AI TERMINAL</div><h1>DIRECTION</h1></div>
    </header>
    <main className="direction-main"><Outlet /></main>
  </div>
);
