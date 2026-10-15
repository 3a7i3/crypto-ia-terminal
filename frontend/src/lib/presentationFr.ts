/** Presentation vocabulary only. API keys, identifiers and enums remain unchanged. */
const labels: Record<string, string> = {
  UNKNOWN: "Inconnu", NOT_AVAILABLE: "Non disponible", UNAVAILABLE: "Indisponible",
  NOT_APPLICABLE: "Sans objet", NON_DEPLOYED: "Non déployé", STALE: "Ancien · périmé",
  FRESH: "Publication récente", PRESENT: "Observé", EMPTY: "Vide observé",
  UNRESOLVED: "Non résolu", EXACT: "Concordance exacte", WITHIN_TOLERANCE: "Dans la tolérance",
  DIVERGENT: "Divergence", COMPLETE: "Terminée", PARTIAL: "Partiel", LOW_SAMPLE: "Échantillon limité",
  DEGRADED: "Dégradé",
  BUY: "Achat", SELL: "Vente",
  LONG: "Acheteur", SHORT: "Vendeur", MIXED: "Mixte", active: "En cours", inactive: "Arrêté",
  failed: "En échec", activating: "Démarrage", deactivating: "Arrêt en cours",
  ACTIVE: "En cours", QUIESCING: "Mise au repos", FINALIZING: "Finalisation", FINAL: "Finalisée",
  STRATEGY: "Stratégie", FEATURE: "Variable", CONFIG: "Configuration", HYBRID: "Hybride",
  DISCOVERY: "Exploration", EVALUATION: "Évaluation", VALIDATION: "Validation",
  AVAILABLE: "Disponible", DESCRIPTIVE_ONLY: "Descriptif uniquement", NOT_EVALUATED: "Non évalué",
  ADEQUATE_FOR_DECLARED_TEST: "Adéquat pour le test déclaré", sideways: "Latéral",
  bull_trend: "Tendance haussière", bear_trend: "Tendance baissière", range: "Latéral",
  POSITION_OPENED: "Position ouverte", POSITION_CLOSED: "Position clôturée",
  POSITION_UNRESOLVED: "Position non résolue", EPOCH_CREATED: "Expérience créée",
  RECOVERY_COMPLETED: "Récupération terminée",
};
export function fr(value: string | null | undefined): string {
  return value == null ? "Non disponible" : labels[value] ?? value;
}

/** Display only: formats the API's own snapshot_age_s; no age is computed in the browser. */
export function ageFr(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days} j ${hours} h`;
  if (hours > 0) return `${hours} h ${minutes} min`;
  if (minutes > 0) return `${minutes} min`;
  return `${total} s`;
}

/** Display only: an ISO UTC instant with its year, e.g. "07/10/2026 23:29 UTC". */
export function utcStampFr(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return `${parsed.toLocaleString("fr-FR", {
    timeZone: "UTC",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })} UTC`;
}
