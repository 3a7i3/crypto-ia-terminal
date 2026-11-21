import type { Sign, StressLeg } from "./derivativesStress";
import { marketKindLabel, venueName } from "./venueNames";

const REASONS: Record<string, string> = {
  SOURCE_NOT_SUPPLIED: "Source non reçue", STALE: "Observation périmée", LEG_UNAVAILABLE: "Plateforme indisponible",
  UNRESOLVED_TIMESTAMP_KIND: "Date exchange non qualifiée", MISSING_EXCHANGE_TIMESTAMP: "Date exchange absente",
  UNRESOLVED_OBSERVER_CLOCK: "Horloge d’observation non qualifiée", FUTURE_OR_INCONSISTENT_CLOCK: "Horloges incohérentes",
  NOT_APPLICABLE: "Sans objet", NO_SPOT_REFERENCE: "Aucune référence spot qualifiée", OBSERVER_CLOCKS_NOT_ALIGNED: "Horloges non alignées",
  TIMESTAMP_KINDS_DIFFER: "Sémantiques de date différentes", EVENTS_NOT_SYNCHRONIZED: "Observations non synchronisées",
  PRICE_KINDS_DIFFER: "Natures de prix différentes", QUOTE_UNAVAILABLE: "Une des deux cotations est indisponible",
  MARK_OR_INDEX_MISSING: "Prix de marque ou indice absent", DERIVATIVE_OR_SPOT_MISSING: "Prix dérivé ou spot absent",
  FUNDING_RATE_MISSING: "Funding non reçu", FUNDING_INTERVAL_UNKNOWN: "Intervalle de funding inconnu", NEXT_FUNDING_IN_PAST: "Prochain funding déjà passé",
  OPEN_INTEREST_MISSING: "Open interest non reçu", OPEN_INTEREST_UNIT_UNKNOWN: "Unité d’open interest inconnue",
  CONTRACT_SIZE_UNKNOWN: "Taille de contrat inconnue : notionnel indisponible", PRICE_MISSING_FOR_NOTIONAL: "Prix absent : notionnel indisponible",
  NO_SAMPLE_AT_WINDOW_START: "Aucun échantillon au début de la fenêtre", SAMPLE_WITHOUT_PRICE_OR_OPEN_INTEREST: "Échantillon sans prix ni open interest",
  PARTIAL_COVERAGE: "Couverture partielle : total non publié", NO_DERIVATIVE_LEG: "Aucun dérivé attendu",
  NO_TRADE_TAPE: "Aucune série de transactions reçue", TIMESTAMP_KIND_NOT_MATCHING_ENGINE: "Heure de transaction non qualifiée (moteur d’appariement requis)",
  SAMPLE_TOO_SMALL: "Échantillon trop petit pour mesurer", RESOLUTION_NOT_ADMITTED: "Résolution d’horodatage non admise",
  TIMESTAMP_NOT_ON_DECLARED_RESOLUTION: "Horodatages incompatibles avec la résolution déclarée", EVENT_OUTSIDE_WINDOW: "Transaction hors fenêtre",
  EVENT_MALFORMED: "Transaction invalide", WINDOW_INVALID: "Fenêtre invalide", TAPE_TOO_LARGE: "Série trop volumineuse",
};
export const reasonLabel = (reason: string | null) => reason === null ? "" : REASONS[reason] ?? "Raison technique";
export const signLabel = (sign: Sign | null) => sign === "UP" ? "hausse" : sign === "DOWN" ? "baisse" : sign === "FLAT" ? "stable" : "—";
export const windowLabel = (seconds: number) => seconds % 86400 === 0 ? seconds / 86400 + " j" : seconds % 3600 === 0 ? seconds / 3600 + " h" : seconds + " s";
export const legLabel = (leg: StressLeg) => `${venueName(leg.venue)} · ${marketKindLabel[leg.instrument.market_kind] ?? leg.instrument.market_kind} · ${leg.native_symbol}`;
export const periodLabel = (seconds: number) => seconds >= 3600 ? seconds / 3600 + " h" : seconds >= 60 ? seconds / 60 + " min" : seconds + " s";
