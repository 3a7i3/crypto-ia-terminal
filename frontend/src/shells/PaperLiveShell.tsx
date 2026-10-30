import React from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useOperatorSnapshot, type SnapshotState } from "../lib/snapshotClient";
import type { OperatorSnapshot } from "../types";
import { ModuleHeading } from "../components/ModuleHeading";
import { ModeBadge } from "../components/ModeBadge";
export interface PaperLiveOutletContext {
  snapshotState: SnapshotState;
  activeSnapshot: OperatorSnapshot | null;
}
// Only dependent routes mount this reader. Independent modules never fetch Advisor.
const CanonicalOutlet: React.FC = () => {
  const snapshotState = useOperatorSnapshot();
  const positions = useLocation().pathname.endsWith("/portfolio");
  return (
    <>
      {!positions && (
        <span className="module-mode">
          <ModeBadge
            mode={
              snapshotState.status === "success"
                ? snapshotState.snapshot.portfolio.mode
                : undefined
            }
          />
        </span>
      )}
      <Outlet
        context={
          {
            snapshotState,
            activeSnapshot:
              snapshotState.status === "success"
                ? snapshotState.snapshot
                : null,
          } satisfies PaperLiveOutletContext
        }
      />
    </>
  );
};
export const PaperLiveShell: React.FC = () => {
  const { pathname } = useLocation();
  const key = pathname.split("/").at(-1) ?? "";
  const headings: Record<string, [string, string]> = {
    market: ["Marché", "Scanner CryptoRadar et contexte de liquidité publié."],
    decisions: [
      "Décisions",
      "Signaux observés, motifs de refus et traces de décision.",
    ],
    portfolio: [
      "Positions",
      "Positions publiées et provenance de leur cycle de vie.",
    ],
    lifecycle: [
      "Positions",
      "Comparaison publiée entre simulateur et PPL ; autorités distinctes.",
    ],
    finance: [
      "Finance",
      "Montants FIN, frais et rapprochements. Historique PPL séparé.",
    ],
    events: [
      "Événements",
      "Journal publié des événements, dans son périmètre de couverture.",
    ],
    system: [
      "Système",
      "Preuves de service et de stockage ; aucune santé globale déduite.",
    ],
  };
  const [title, description] = headings[key] ?? [
    "Module",
    "Source de présentation en lecture seule.",
  ];
  const canonical = key === "portfolio" || key === "decisions";
  return (
    <div data-testid="paper-live-shell">
      <ModuleHeading title={title} description={description} />
      {(key === "portfolio" || key === "lifecycle") && (
        <nav className="module-subnav" aria-label="Vues Positions">
          <NavLink to="/paper-live/portfolio" data-testid="tab-portfolio">
            Positions observées
          </NavLink>
          <NavLink to="/paper-live/lifecycle" data-testid="tab-ppl">
            Comparaison PPL
          </NavLink>
        </nav>
      )}
      {canonical ? <CanonicalOutlet /> : <Outlet />}
    </div>
  );
};
