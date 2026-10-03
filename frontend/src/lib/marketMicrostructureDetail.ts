/** Closed source field labels. Acceleration is a rate difference, not USD/s². */
export const detailLabels = {
  flow: {
    window_ms: "Fenêtre · ms", buy_volume_usd: "Volume achat · USD", sell_volume_usd: "Volume vente · USD",
    buy_count: "Trades achat · nombre", sell_count: "Trades vente · nombre",
    buy_avg_size_usd: "Taille moyenne achat · USD", sell_avg_size_usd: "Taille moyenne vente · USD",
    large_buy_count: "Gros trades achat · nombre", large_sell_count: "Gros trades vente · nombre",
    buy_acceleration: "Variation débit achat · USD/s", sell_acceleration: "Variation débit vente · USD/s",
    dominant_side: "Côté dominant", pressure_ratio: "Pression achat · 0–1",
  },
  liquidity: {
    bid_added_usd: "Bid ajouté · USD", ask_added_usd: "Ask ajouté · USD",
    bid_removed_usd: "Bid retiré hors consommation · USD", ask_removed_usd: "Ask retiré hors consommation · USD",
    bid_consumed_usd: "Bid consommé · USD", ask_consumed_usd: "Ask consommé · USD",
    cancellation_rate_bid: "Annulation bid · 0–1", cancellation_rate_ask: "Annulation ask · 0–1",
    net_liquidity_change_usd: "Variation nette de liquidité · USD",
  },
  resistance: {
    volume_applied_usd: "Volume appliqué · USD", price_displacement_bps: "Déplacement absolu · bps",
    resistance_score: "Résistance · USD/bps", fragility_score: "Fragilité · 0–1", absorption_ratio: "Absorption · 0–1",
  },
  state_components: {
    pressure_ratio: "Pression achat · 0–1", absorption: "Absorption · 0–1", fragility: "Fragilité · 0–1",
    displacement_bps: "Déplacement absolu · bps", canc_bid: "Annulation bid · 0–1", canc_ask: "Annulation ask · 0–1",
  },
} as const;
export type DetailName = keyof typeof detailLabels;
type Fields<N extends DetailName> = { [K in keyof typeof detailLabels[N]]: K extends "dominant_side" ? "buy" | "sell" | "neutral" | null : number | null };
export interface DetailTime {
  observed_at_utc: string | null;
  observation_age_s: number | null;
  freshness_classification: "FRESH" | "STALE" | "UNKNOWN";
}
export type MicrostructureDetail = {
  flow: (Fields<"flow"> & DetailTime) | null;
  liquidity: (Fields<"liquidity"> & DetailTime & { observation_evidence: "SOURCE_VALUES_ONLY" }) | null;
  resistance: (Fields<"resistance"> & DetailTime) | null;
  state_components: Fields<"state_components"> | null;
};
