import React from "react";
import type { MarketSourceSetup } from "../lib/marketSourceSetup";

/** M1-C2: one wording for a Market source that this server does not provide.
 * The exact error code stays visible; nothing is presented as empty or zero. */
export const MarketSourceNotice: React.FC<{ source: string; setup: MarketSourceSetup; code: string; httpStatus?: number | null }> = ({ source, setup, code, httpStatus }) =>
  <p role="status" className="market-source-notice" data-testid="market-source-not-configured" data-source-setup={setup}>
    Source {source} {setup === "NOT_DEPLOYED" ? "non déployée" : "non configurée"} sur ce serveur{httpStatus ? ` · HTTP ${httpStatus}` : ""} · <code>{code}</code>.
    {" "}Aucune publication lue : ni marché vide, ni valeur nulle. État actuel INCONNU.
  </p>;
