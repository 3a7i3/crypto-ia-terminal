import React from "react";
import { useOutletContext } from "react-router-dom";
import type { SnapshotState } from "../lib/snapshotClient";
import type { PaperLiveOutletContext } from "../shells/PaperLiveShell";
import { DecisionsView } from "../views/DecisionsView";
import { FinancialReconciliationView } from "../views/FinancialReconciliationView";
import { MarketView } from "../views/MarketView";
import { NotExposedView } from "../views/NotExposedView";
import { OverviewView } from "../views/OverviewView";
import { PortfolioView } from "../views/PortfolioView";
import { PplComparisonView } from "../views/PplComparisonView";
import { SystemView } from "../views/SystemView";
import { RuntimeServiceView } from "../views/RuntimeServiceView";

function usePaperLive(): PaperLiveOutletContext { return useOutletContext<PaperLiveOutletContext>(); }

const NoSnapshot: React.FC<{ domain: string }> = ({ domain }) => (
  <div className="canonical-unresolved" data-testid="no-snapshot">
    Canonical snapshot unavailable — {domain} is UNRESOLVED until a validated snapshot is available.
  </div>
);

const MarketCanonicalContext: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "success") return null;
  if (state.status === "loading") return <div className="market-domain-context" data-testid="market-canonical-context">Canonical advisor context loading · MARKET telemetry is sourced independently.</div>;
  const summary = state.status === "api_error"
    ? state.error.error_code === "SNAPSHOT_MISSING" ? "Canonical advisor: UNRESOLVED · SNAPSHOT_MISSING" : `Canonical advisor API error · ${state.error.error_code ?? "UNKNOWN_ERROR"}`
    : "Canonical advisor: DISCONNECTED";
  const detail = state.status === "api_error" ? state.error.error_message ?? "no error message supplied" : state.message;
  return <details className="market-domain-context" data-testid="market-canonical-context"><summary>{summary} · MARKET remains a separate observational domain</summary><div className="market-domain-context-detail">{detail}</div></details>;
};

const PplCanonicalContext: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "success") return null;
  const summary = state.status === "loading" ? "Canonical advisor context loading" : state.status === "api_error" ? `Canonical advisor: ${state.error.error_code ?? "UNRESOLVED"}` : "Canonical advisor: DISCONNECTED";
  return <div className="market-domain-context" data-testid="ppl-canonical-context">{summary} · PPL comparison remains an independent observational domain.</div>;
};

export const OverviewRoute: React.FC = () => { const { activeSnapshot } = usePaperLive(); return activeSnapshot ? <OverviewView snapshot={activeSnapshot} /> : <NoSnapshot domain="PAPER LIVE" />; };
export const MarketRoute: React.FC = () => { const { snapshotState } = usePaperLive(); return <><MarketCanonicalContext state={snapshotState} /><MarketView /></>; };
export const PortfolioRoute: React.FC = () => { const { activeSnapshot } = usePaperLive(); return activeSnapshot ? <PortfolioView snapshot={activeSnapshot} /> : <NoSnapshot domain="PAPER LIVE" />; };
export const DecisionsRoute: React.FC = () => { const { activeSnapshot } = usePaperLive(); return activeSnapshot ? <DecisionsView snapshot={activeSnapshot} /> : <NoSnapshot domain="PAPER LIVE" />; };
export const LifecycleRoute: React.FC = () => { const { snapshotState } = usePaperLive(); return <><PplCanonicalContext state={snapshotState} /><PplComparisonView /></>; };
export const FinanceRoute: React.FC = () => <FinancialReconciliationView />;
export const SystemRoute: React.FC = () => { const { activeSnapshot } = usePaperLive(); return <><RuntimeServiceView />{activeSnapshot ? <SystemView snapshot={activeSnapshot} /> : <NoSnapshot domain="SYSTEM" />}</>; };
export const ScoresRoute: React.FC = () => <NotExposedView title="Scores" />;
