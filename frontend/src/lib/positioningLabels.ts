const REASONS: Record<string, string> = {
  NO_OBSERVATION: "Aucune observation enregistrée", CADENCE_UNKNOWN: "Cadence de collecte non déclarée",
  NO_COMPARABLE_POINT_AT_START: "Aucun point comparable au début de la fenêtre", NO_COMPARABLE_POINT_AT_END: "Aucun point comparable à la fin de la fenêtre",
  OPEN_INTEREST_UNITS_DIFFER: "Unités d’open interest différentes", CONTRACT_SIZES_DIFFER: "Tailles de contrat différentes",
  TIME_BASES_DIFFER: "Bases temporelles différentes", INSUFFICIENT_COVERAGE: "Couverture insuffisante", REFERENCE_OPEN_INTEREST_ZERO: "Open interest de référence nul",
  SCAN_BUDGET_EXCEEDED: "Historique trop volumineux", MARK_OR_INDEX_MISSING: "Prix de marque ou indice absent", MARK_MISSING: "Prix de marque absent",
  SPOT_REFERENCE_NOT_QUALIFIED_OR_MISSING: "Référence spot non qualifiée", FUNDING_RATE_MISSING: "Funding non reçu", FUNDING_INTERVAL_UNKNOWN: "Intervalle de funding inconnu",
  NEXT_FUNDING_IN_PAST: "Prochain funding déjà passé", OPEN_INTEREST_MISSING: "Open interest non reçu", PRICE_MISSING_FOR_NOTIONAL: "Prix absent : notionnel indisponible",
  CONTRACT_SIZE_UNKNOWN: "Taille de contrat inconnue", FUNDING_INTERVALS_DIFFER: "Intervalles de funding différents", QUOTE_CURRENCIES_DIFFER: "Devises de cotation différentes",
  LEG_WITHOUT_OBSERVATION: "Une plateforme sans observation", LATEST_PRICE_OR_OI_MISSING: "Dernier prix ou OI absent", HISTORY_TOO_LONG: "Historique trop long pour le graphique",
  POINT_WITHOUT_PRICE_OR_OI: "Point sans prix ou sans OI", POINTS_OFF_CADENCE_GRID: "Points hors de la grille de cadence", NOT_ALIGNED_WITH_REFERENCE_LEG: "Non aligné sur la série de référence",
  SPOT_REFERENCE_NOT_QUALIFIED: "Référence spot non qualifiée", INDEX_NOT_PUBLISHED: "Indice non publié", NO_SPOT_MARKET_DECLARED: "Aucun marché spot déclaré",
};
export const positioningReason = (r: string | null) => r === null ? "" : REASONS[r] ?? "Raison technique";
export const OI_UNIT: Record<string, string> = { CONTRACTS: "contrats", BASE: "unités de base", QUOTE: "unités de cotation" };
export const FIELD: Record<string, string> = { mark_price: "Prix de marque", index_price: "Prix d’indice", spot_reference: "Référence spot", open_interest: "Open interest", funding_rate: "Funding" };
