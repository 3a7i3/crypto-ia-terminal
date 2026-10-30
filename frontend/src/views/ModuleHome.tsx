import React from "react";
import { Link } from "react-router-dom";
import { AppIcon } from "../components/AppIcon";
import { ModuleHeading } from "../components/ModuleHeading";
import { PublicationStamp } from "../components/PublicationStamp";
import { MODULES } from "../lib/moduleNavigation";
import { useOperatorSnapshot } from "../lib/snapshotClient";
import { useMarketSnapshot } from "../lib/marketClient";
import { useFinancialReconciliation } from "../lib/financialReconciliationClient";
import { useResearchLabSnapshot } from "../lib/researchLabClient";
import { useRuntimeService } from "../lib/runtimeServiceClient";
import { fr } from "../lib/presentationFr";
type SourceState = {
  status: string;
  snapshot?: {
    generated_at_utc: string;
    freshness_classification?: string;
    snapshot_age_s?: number | null;
  };
};
export const ModuleHome: React.FC = () => {
  const canonical = useOperatorSnapshot();
  const market = useMarketSnapshot();
  const finance = useFinancialReconciliation();
  const research = useResearchLabSnapshot();
  const system = useRuntimeService();
  const sources: { state: SourceState; source: string }[] = [
    { state: market, source: "CryptoRadar" },
    { state: canonical, source: "Projection des décisions" },
    { state: canonical, source: "Projection des positions" },
    { state: finance, source: "FIN · réconciliation" },
    { state: research, source: "Research · évaluations" },
    { state: system, source: "Observation du service Advisor" },
  ];
  return (
    <div data-testid="module-home" className="module-home">
      <ModuleHeading
        title="Ton infrastructure, module par module."
        description="Choisis une source pour comprendre ses observations et ses limites."
      />
      <aside className="home-notice">
        <span className="home-notice-mark" aria-hidden="true">
          i
        </span>
        <p>
          Chaque module conserve sa source et sa date. La disponibilité d’une
          publication ne certifie pas l’activité de la machine.
        </p>
      </aside>
      <nav className="module-grid" aria-label="Explorer les modules">
        {MODULES.slice(1).map((module, index) => {
          const { state, source } = sources[index];
          const snapshot =
            state.status === "success" ? state.snapshot : undefined;
          const label = snapshot
            ? snapshot.freshness_classification
              ? fr(snapshot.freshness_classification)
              : "Publication disponible"
            : state.status === "loading"
              ? "Lecture en cours"
              : state.status === "transport_error"
                ? "Lecture impossible"
                : "Source indisponible";
          return (
            <article className="module-card" key={module.to}>
              <div className="module-card-top">
                <span className="module-icon">
                  <AppIcon name={module.icon} size={23} />
                </span>
                <span
                  className={`source-pill ${snapshot?.freshness_classification === "STALE" ? "source-pill-stale" : ""}`}
                >
                  {label}
                </span>
              </div>
              <h2>
                <Link to={module.to}>
                  {module.label}
                  <AppIcon name="arrow" size={19} />
                </Link>
              </h2>
              <p>{module.description}</p>
              {snapshot ? (
                <PublicationStamp
                  compact
                  generatedAt={snapshot.generated_at_utc}
                  freshness={snapshot.freshness_classification}
                  age={snapshot.snapshot_age_s}
                  source={source}
                />
              ) : (
                <div className="publication-stamp">
                  <span>{source}</span>
                  <span>Date non disponible · état actuel inconnu</span>
                </div>
              )}
            </article>
          );
        })}
      </nav>
      <p className="home-footnote">
        Les montants, positions et résultats sont consultables dans leur module,
        avec leurs preuves. Aucune donnée absente n’est remplacée par zéro.
      </p>
    </div>
  );
};
