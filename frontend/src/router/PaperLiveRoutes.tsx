import React from "react";
import { useOutletContext } from "react-router-dom";
import type { SnapshotState } from "../lib/snapshotClient";
import type { PaperLiveOutletContext } from "../shells/PaperLiveShell";
import { DecisionsView } from "../views/DecisionsView";
import { FinancialReconciliationView } from "../views/FinancialReconciliationView";
import { MarketMicrostructureView } from "../views/MarketMicrostructureView";
import { MarketView } from "../views/MarketView";
import { NotExposedView } from "../views/NotExposedView";
import { OverviewView } from "../views/OverviewView";
import { PortfolioView } from "../views/PortfolioView";
import { PplComparisonView } from "../views/PplComparisonView";
import { SystemView } from "../views/SystemView";
import { RuntimeServiceView } from "../views/RuntimeServiceView";
import { StorageView } from "../views/StorageView";

function usePaperLive(): PaperLiveOutletContext { return useOutletContext<PaperLiveOutletContext>(); }

const NoSnapshot: React.FC<{ domain: string }> = ({ domain }) => (
  <div className="canonical-unresolved" data-testid="no-snapshot">
    Snapshot canonique indisponible — {domain} reste non résolu jusqu’à réception d’une source validée.
  </div>
);

const MarketCanonicalContext: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "success") return null;
  if (state.status === "loading") return <div className="market-domain-context" data-testid="market-canonical-context">Chargement du contexte Advisor canonique · les observations du marché ont leur propre source.</div>;
  const summary = state.status === "api_error"
    ? state.error.error_code === "SNAPSHOT_MISSING" ? "Advisor canonique : UNRESOLVED · SNAPSHOT_MISSING" : `Erreur API Advisor canonique · ${state.error.error_code ?? "UNKNOWN_ERROR"}`
    : "Advisor canonique : DISCONNECTED";
  const detail = state.status === "api_error" ? state.error.error_message ?? "Aucun message source fourni" : state.message;
  return <details className="market-domain-context" data-testid="market-canonical-context"><summary>{summary} · le marché reste un domaine observationnel indépendant</summary><div className="market-domain-context-detail">{detail}</div></details>;
};

const PplCanonicalContext: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "success") return null;
  const summary = state.status === "loading" ? "Chargement du contexte Advisor canonique" : state.status === "api_error" ? `Advisor canonique : ${state.error.error_code ?? "UNRESOLVED"}` : "Advisor canonique : DISCONNECTED";
  return <div className="market-domain-context" data-testid="ppl-canonical-context">{summary} · la comparaison PPL conserve sa source indépendante.</div>;
};

export const OverviewRoute: React.FC = () => { const { activeSnapshot } = usePaperLive(); return activeSnapshot ? <OverviewView snapshot={activeSnapshot} /> : <NoSnapshot domain="PAPER LIVE" />; };
export const MarketRoute: React.FC = () => { const { snapshotState } = usePaperLive(); return <><MarketCanonicalContext state={snapshotState} /><MarketView /><details className="machine-section"><summary>Microstructure · flux et liquidité publiés</summary><MarketMicrostructureView /></details></>; };
export const PortfolioRoute: React.FC = () => { const { activeSnapshot } = usePaperLive(); return activeSnapshot ? <PortfolioView snapshot={activeSnapshot} /> : <NoSnapshot domain="PAPER LIVE" />; };
export const DecisionsRoute: React.FC = () => { const { activeSnapshot } = usePaperLive(); return activeSnapshot ? <DecisionsView snapshot={activeSnapshot} /> : <NoSnapshot domain="PAPER LIVE" />; };
export const LifecycleRoute: React.FC = () => { const { snapshotState } = usePaperLive(); return <><PplCanonicalContext state={snapshotState} /><PplComparisonView /></>; };
export const FinanceRoute: React.FC = () => <FinancialReconciliationView />;
export const SystemRoute: React.FC = () => { const { activeSnapshot } = usePaperLive(); return <><RuntimeServiceView /><StorageView />{activeSnapshot ? <SystemView snapshot={activeSnapshot} /> : <NoSnapshot domain="SYSTEM" />}</>; };
export const ScoresRoute: React.FC = () => <NotExposedView title="Scores" />;
