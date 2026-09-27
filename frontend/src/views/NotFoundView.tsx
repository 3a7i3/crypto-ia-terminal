import React from "react";
import { Link, useLocation } from "react-router-dom";

export const NotFoundView: React.FC = () => {
  const location = useLocation();
  return <main className="not-found-view" data-testid="not-found-view">
    <div className="direction-eyebrow">ROUTE INCONNUE</div><h1>NOT FOUND</h1>
    <code data-testid="not-found-path">{location.pathname}</code>
    <p>Cette route ne correspond à aucune surface produit déployée.</p>
    <nav aria-label="Retour vers une surface produit"><Link to="/paper-live">PAPER LIVE</Link><Link to="/direction">DIRECTION</Link><Link to="/research">RESEARCH</Link></nav>
  </main>;
};
