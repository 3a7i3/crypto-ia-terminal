import React from "react";

const unavailable = ["File de décisions", "Agents", "Bounties", "Économie AIC", "Coûts réels", "Sécurité / dette / incidents"];

export const DirectionOverview: React.FC = () => (
  <div className="direction-stack" data-testid="direction-view">
    <section className="direction-intro">
      <div><div className="direction-eyebrow">SURFACE PROPRIÉTAIRE · PRÉSENTATION / GOUVERNANCE</div><h2>Vue Direction</h2></div>
      <span className="direction-status-unknown">ÉTAT GLOBAL · INCONNU</span>
    </section>
    <section className="direction-grid" aria-label="Capacités Direction">
      {unavailable.map((label) => <article className="direction-card" key={label}><h3>{label}</h3><strong>NON DÉPLOYÉ</strong><p>Aucune projection gouvernée n’est disponible pour ce bloc.</p></article>)}
    </section>
    <p className="direction-boundary">Direction ne crée aucune vérité scientifique et ne peut ni merger, ni déployer, ni modifier l’epoch PAPER active.</p>
  </div>
);
