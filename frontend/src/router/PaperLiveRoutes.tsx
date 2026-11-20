import React, { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import type { PaperLiveOutletContext } from "../shells/PaperLiveShell";
import { DecisionsView } from "../views/DecisionsView";
import { FinancialReconciliationView } from "../views/FinancialReconciliationView";
import { MarketView } from "../views/MarketView";
import { PaperPositionArchive } from "../views/PaperPositionArchive";
import { PaperOrderRegisterView } from "../views/PaperOrderRegisterView";
import { PortfolioView } from "../views/PortfolioView";
import { PplComparisonView } from "../views/PplComparisonView";
import { SystemView } from "../views/SystemView";
import { RuntimeServiceView } from "../views/RuntimeServiceView";
import { StorageView } from "../views/StorageView";
import { SnapshotStatusBanner } from "../components/SnapshotStatusBanner";
import { PublicationStamp } from "../components/PublicationStamp";
import { useOperatorSnapshot } from "../lib/snapshotClient";
const CanonicalView: React.FC<{
  children: (
    snapshot: NonNullable<PaperLiveOutletContext["activeSnapshot"]>,
  ) => React.ReactNode;
}> = ({ children }) => {
  const { snapshotState, activeSnapshot } =
    useOutletContext<PaperLiveOutletContext>();
  if (!activeSnapshot)
    return (
      <div data-testid="no-snapshot">
        <SnapshotStatusBanner state={snapshotState} />
      </div>
    );
  return (
    <>
      <PublicationStamp
        source="Projection opérateur"
        generatedAt={activeSnapshot.generated_at_utc}
        freshness={activeSnapshot.freshness_classification}
        age={activeSnapshot.snapshot_age_s}
      />
      {(activeSnapshot.runtime_state === "LAST_KNOWN" ||
        activeSnapshot.instance_relation !== "CURRENT_INSTANCE") && (
        <p className="home-notice">
          Capture antérieure ou instance non vérifiée : aucune activité actuelle
          attestée.
        </p>
      )}
      <details className="snapshot-source-details">
        <summary>Source et identité de la capture</summary>
        <dl>
          <dt>Relation d’instance</dt>
          <dd data-testid="instance-relation">
            {activeSnapshot.instance_relation}
          </dd>
          <dt>État de la capture</dt>
          <dd data-testid="runtime-state">{activeSnapshot.runtime_state}</dd>
          <dt>Identifiant</dt>
          <dd>{activeSnapshot.snapshot_id}</dd>
          <dt>Source SHA</dt>
          <dd>{activeSnapshot.source_sha ?? "Inconnu"}</dd>
          <dt>Preuve SHA</dt>
          <dd>{activeSnapshot.runtime_sha_evidence_status}</dd>
          <dt>Motif</dt>
          <dd>{activeSnapshot.stale_reason ?? "Non disponible"}</dd>
        </dl>
      </details>
      {children(activeSnapshot)}
    </>
  );
};
// M1-C1 (EO-022, D-C4): Microstructure is a top-level Market destination
// (/paper-live/market/lmi) instead of a <details> below every Market view.
export const MarketRoute: React.FC = () => <MarketView />;
export const PortfolioRoute: React.FC = () => (
  <>
    <CanonicalView>
      {(snapshot) => <PortfolioView snapshot={snapshot} />}
    </CanonicalView>
    {import.meta.env.DEV && <PaperOrderRegisterView />}
    <PaperPositionArchive />
  </>
);
export const DecisionsRoute: React.FC = () => (
  <CanonicalView>
    {(snapshot) => <DecisionsView snapshot={snapshot} />}
  </CanonicalView>
);
export const LifecycleRoute: React.FC = () => <PplComparisonView />;
export const FinanceRoute: React.FC = () => <FinancialReconciliationView />;
const AdvisorDiagnostics: React.FC = () => {
  const state = useOperatorSnapshot();
  return state.status === "success" ? (
    <>
      <PublicationStamp
        source="Projection opérateur · diagnostic"
        generatedAt={state.snapshot.generated_at_utc}
        freshness={state.snapshot.freshness_classification}
        age={state.snapshot.snapshot_age_s}
      />
      <SystemView snapshot={state.snapshot} />
    </>
  ) : (
    <SnapshotStatusBanner state={state} />
  );
};
export const SystemRoute: React.FC = () => {
  const [diagnostics, setDiagnostics] = useState(false);
  return (
    <>
      <div className="system-source-grid">
        <RuntimeServiceView />
        <StorageView />
      </div>
      <details
        className="module-details"
        onToggle={(e) => setDiagnostics(e.currentTarget.open)}
      >
        <summary>Diagnostic applicatif Advisor</summary>
        {diagnostics && <AdvisorDiagnostics />}
      </details>
      <Link className="module-secondary-link" to="/paper-live/events">
        Consulter le journal des événements →
      </Link>
    </>
  );
};
