// M1-C5 (EO-026, D3): CI-only compatibility proof of the CryptoRadar historique
// scanner (GET /api/operator/v1/market). The component is the unrouted
// MarketScanner kept by M1-C3, mounted unchanged. This entry is served only by
// the capture harnesses (Vite dev server, or the separate dist-legacy-proof
// build); it is not part of the production bundle and registers no service
// worker. The banner states what the page is; it never certifies a runtime.
import React from "react";
import ReactDOM from "react-dom/client";
import "../tokens.css";
import "../operator.css";
import "../clarity.css";
import "../mobile-operator.css";
import "../workspace.css";
import "../radar-polish.css";
import { MarketScanner } from "../views/MarketScanner";
import { applyTheme, readTheme } from "../lib/theme";

export const LEGACY_PROOF_LABEL = "Preuve de compatibilité · CryptoRadar historique · composant legacy non exposé dans l’application";

export const MarketScannerProof: React.FC = () => (
  // Same style scope as the application frame (.operator-shell), without its
  // navigation: the proof page must not offer any application route.
  <div className="operator-shell" data-testid="legacy-proof">
    <main className="app-content">
      <p role="note" data-testid="legacy-proof-banner" className="home-notice">{LEGACY_PROOF_LABEL}</p>
      <MarketScanner />
    </main>
  </div>
);

applyTheme(readTheme());
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MarketScannerProof />
  </React.StrictMode>,
);
