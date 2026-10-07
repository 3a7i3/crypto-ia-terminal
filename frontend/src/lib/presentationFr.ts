/** Presentation vocabulary only. API keys, identifiers and enums remain unchanged. */
const labels: Record<string, string> = {
  UNKNOWN: "Inconnu", NOT_AVAILABLE: "Non disponible", UNAVAILABLE: "Indisponible",
  NOT_APPLICABLE: "Sans objet", NON_DEPLOYED: "Non déployé", STALE: "Ancien · périmé",
  FRESH: "Publication récente", PRESENT: "Observé", EMPTY: "Vide observé",
  UNRESOLVED: "Non résolu", EXACT: "Concordance exacte", WITHIN_TOLERANCE: "Dans la tolérance",
  DIVERGENT: "Divergence", COMPLETE: "Terminée", PARTIAL: "Partiel", LOW_SAMPLE: "Échantillon limité",
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
