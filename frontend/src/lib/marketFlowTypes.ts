// CryptoRadar Flux — frontend contract 1.0.0 (lot 3A, source only).
//
// Mirrors the closed, nested MarketFlowArtifact contract owned by the Python
// oracle contract.py of the Python Flux package. Nothing here is computed or
// authoritative: a value that fits these types has passed a FORM check, it is
// not true, fresh or admitted data. Nanosecond values and financial decimals
// are TEXT (JavaScript numbers lose integers beyond 2**53); counters and
// indices are JSON integers within the safe range.

export const MARKET_FLOW_SCHEMA_VERSION = "1.0.0" as const;
export const MARKET_FLOW_PRODUCT = "MarketFlowArtifact" as const;
export const MARKET_FLOW_CALC_VERSION = "flow-calc-1.0.0" as const;
export const MARKET_FLOW_VENUE = "coinbase_advanced" as const;
export const MARKET_FLOW_CHANNEL = "l2_data" as const;
export const MARKET_FLOW_INSTRUMENTS = {
  "BTC-USD": ["BTC", "USD"],
  "ETH-USD": ["ETH", "USD"],
} as const;
export type MarketFlowInstrument = keyof typeof MARKET_FLOW_INSTRUMENTS;

export const MARKET_FLOW_BAR_STATUSES = ["OBSERVED", "OBSERVED_ZERO", "NOT_COVERED", "SESSION_BREAK_UNRESOLVED"] as const;
export const MARKET_FLOW_BOOK_STATES = ["NO_SNAPSHOT", "LIVE", "INVALID", "CONNECTION_CLOSED", "UNRESOLVED"] as const;
export const MARKET_FLOW_L2_REFUSALS = [
  "BOUNDED_BYTES_REQUIRED", "CHANNEL_MISSING", "DECIMAL_TEXT_REFUSED", "DUPLICATE_NATIVE_FIELD",
  "ENVELOPE_NOT_OBJECT", "EVENTS_NOT_LIST", "EVENT_NOT_OBJECT", "EVENT_TYPE_UNKNOWN", "INVALID_JSON",
  "JSON_NUMBER_FRACTION_REFUSED", "LEVEL_LIMIT_EXCEEDED", "NONFINITE_JSON", "REMOVE_UNKNOWN_LEVEL",
  "SEQUENCE_NOT_NONNEGATIVE_INTEGER", "SIDE_UNKNOWN", "SNAPSHOT_DUPLICATE_LEVEL", "TIME_FORMAT_REFUSED",
  "TIME_NOT_TEXT", "TIME_VALUE_REFUSED", "UNEXPECTED_PRODUCT", "UPDATES_NOT_LIST", "ZERO_NOT_ALLOWED",
] as const;
export type MarketFlowL2Refusal = (typeof MARKET_FLOW_L2_REFUSALS)[number];
export type MarketFlowInvalidReason =
  | "SEQUENCE_DUPLICATE_OR_REORDERED"
  | "SEQUENCE_GAP"
  | "CROSSED_OR_LOCKED_BOOK"
  | `MALFORMED_MESSAGE:${MarketFlowL2Refusal}`
  | `APPLY_REFUSED:${MarketFlowL2Refusal}`;
export const MARKET_FLOW_SILENCE_STATUSES = ["UNRESOLVED", "STALE_BY_SILENCE", "SILENCE_BUDGET_NOT_EXCLUDED", "WITHIN_BUDGET"] as const;
export const MARKET_FLOW_AGE_STATUSES = [
  "UNRESOLVED", "FUTURE", "FUTURE_NOT_EXCLUDED", "STALE", "STALE_NOT_EXCLUDED", "WITHIN_ASSUMPTIONS",
] as const;
export const MARKET_FLOW_FRESHNESS = [
  "NOT_USABLE", "FUTURE_TIMESTAMP", "STALE", "FUTURE_NOT_EXCLUDED", "STALE_NOT_EXCLUDED",
  "UNRESOLVED", "QUALIFIED_WITHIN_ASSUMPTIONS", "LIVE_UNQUALIFIED",
] as const;
export const MARKET_FLOW_SEND_STATES = ["NOT_SUPPLIED", "NATIVE_UNQUALIFIED"] as const;
export const MARKET_FLOW_LEVEL_TIME_STATES = ["NOT_SUPPLIED", "NATIVE_UNQUALIFIED", "PLACEHOLDER_EPOCH_NOT_A_DATE"] as const;

/** Unsigned (or, where the contract allows, signed) integer nanoseconds as ASCII text. */
export type NsText = string;
/** Decimal text: ASCII digits, optional fraction, optional leading minus where signed; never normalised. */
export type DecimalText = string;
export type NsPair = readonly [NsText, NsText];
export type DecimalPair = readonly [DecimalText, DecimalText];

export type EvidenceKind = "SYNTHETIC" | "HISTORICAL";

export interface MarketFlowIdentity {
  readonly venue: typeof MARKET_FLOW_VENUE;
  readonly instrument: MarketFlowInstrument;
  readonly base: string;
  readonly quote: string;
  readonly market_kind: "SPOT";
  readonly id_domain: "SESSION" | "INSTRUMENT";
  readonly side_convention: { readonly attested: boolean; readonly evidence_ref: string };
}

export interface MarketFlowInputs {
  readonly events_sha256: string;
  readonly event_count: number;
  readonly events_after_as_of_not_read: number;
  readonly events_straddling_as_of_not_read: number;
  readonly l2_events_not_read_after_straddle: number;
}

export interface MarketFlowTrades {
  readonly accepted: number;
  readonly duplicates: number;
  readonly conflicts: readonly { readonly trade_id: string; readonly session_id: string }[];
  /** Native refusal code -> count (>= 1). An open family: codes are not enumerated here. */
  readonly refused: { readonly [code: string]: number };
  readonly sessions: readonly string[];
  readonly excluded: {
    readonly no_event_time: number;
    readonly future_event_time: number;
    readonly outside_range: number;
  };
}

// ---------------------------------------------------------------- bars

interface BarGeometry {
  readonly index: number;
  readonly start_ns: NsText;
  readonly end_ns: NsText;
}

interface BarVolumes {
  readonly quote: string;
  readonly buy_volume: DecimalText;
  readonly sell_volume: DecimalText;
  readonly unknown_volume: DecimalText;
  readonly buy_notional: DecimalText;
  readonly sell_notional: DecimalText;
  readonly unknown_notional: DecimalText;
}

interface BarPrices {
  readonly open: DecimalText;
  readonly close: DecimalText;
  readonly high: DecimalText;
  readonly low: DecimalText;
}

interface BarNoPrices {
  readonly open: null;
  readonly close: null;
  readonly high: null;
  readonly low: null;
}

interface BarCvd {
  readonly segment: number;
  readonly cvd_base: DecimalText | null;
  readonly cvd_base_bounds: DecimalPair;
}

interface BarDeltaExact extends BarCvd {
  readonly delta_status: "EXACT";
  readonly delta_base: DecimalText;
  readonly delta_base_bounds: DecimalPair;
}

interface BarDeltaPartial extends BarCvd {
  readonly delta_status: "PARTIAL_UNKNOWN_SIDE";
  readonly delta_base: null;
  readonly delta_base_bounds: DecimalPair;
}

export type ObservedBar = BarGeometry & BarVolumes & BarPrices & (BarDeltaExact | BarDeltaPartial) & {
  readonly status: "OBSERVED";
  readonly trade_count: number;
};

export type ObservedZeroBar = BarGeometry & BarVolumes & BarNoPrices & BarDeltaExact & {
  readonly status: "OBSERVED_ZERO";
  readonly trade_count: 0;
};

/** The session boundary is unresolved: nothing is claimed about delta or CVD continuity. */
export type SessionBreakBar = BarGeometry & BarVolumes & {
  readonly status: "SESSION_BREAK_UNRESOLVED";
  readonly trade_count: number;
  readonly open: DecimalText | null;
  readonly close: DecimalText | null;
  readonly high: DecimalText | null;
  readonly low: DecimalText | null;
  readonly delta_status: "SESSION_BREAK_UNRESOLVED";
  readonly delta_base: null;
  readonly delta_base_bounds: null;
  readonly segment: null;
  readonly cvd_base: null;
  readonly cvd_base_bounds: null;
};

/** No trade-feed coverage: UNKNOWN is never 0, so every measure stays null. */
export type NotCoveredBar = BarGeometry & {
  readonly status: "NOT_COVERED";
  readonly trade_count: null;
  readonly delta_status: "NOT_COVERED";
  readonly delta_base: null;
  readonly delta_base_bounds: null;
  readonly segment: null;
  readonly cvd_base: null;
  readonly cvd_base_bounds: null;
};

export type MarketFlowBar = ObservedBar | ObservedZeroBar | SessionBreakBar | NotCoveredBar;

export type RollingDeltaEntry =
  | {
      readonly status: "EXACT";
      readonly delta_base: DecimalText;
      readonly delta_base_bounds: DecimalPair;
    }
  | {
      readonly status: "PARTIAL_UNKNOWN_SIDE";
      readonly delta_base: null;
      readonly delta_base_bounds: DecimalPair;
    }
  | {
      readonly status: "NOT_AVAILABLE";
      readonly reason: "WINDOW_BEFORE_ANCHOR" | "COVERAGE_INCOMPLETE_OR_UNRESOLVED";
    };

// ---------------------------------------------------------------- book

export type MarketFlowBookState =
  | readonly ["NO_SNAPSHOT", null]
  | readonly ["LIVE", null]
  | readonly ["INVALID", MarketFlowInvalidReason]
  | readonly ["CONNECTION_CLOSED", null]
  | readonly ["UNRESOLVED", "MESSAGE_STRADDLES_AS_OF"];

export interface BookLevel {
  readonly price: DecimalText;
  readonly size: DecimalText;
  readonly level_event_time_ns: NsText | null;
  readonly level_event_time_state: (typeof MARKET_FLOW_LEVEL_TIME_STATES)[number];
  readonly level_last_change_seq: number;
}

interface BboCommon {
  readonly connection_id: string;
  readonly product: MarketFlowInstrument;
  readonly base: string;
  readonly quote: string;
  readonly market_kind: "SPOT";
  readonly mid: null;
  readonly spread: null;
  readonly economic_metrics: null;
  readonly qualification: "UNQUALIFIED";
  readonly unattested_assumptions: readonly string[];
}

export type BookBbo =
  | (BboCommon & {
      readonly status: "OBSERVED_UNQUALIFIED";
      readonly reason: null;
      readonly bid: BookLevel;
      readonly ask: BookLevel;
    })
  | (BboCommon & {
      readonly status: "NOT_AVAILABLE";
      readonly reason: string;
      readonly bid: null;
      readonly ask: null;
    });

export interface BookFreshness {
  readonly product: MarketFlowInstrument;
  readonly book_state: (typeof MARKET_FLOW_BOOK_STATES)[number];
  readonly reason: string | null;
  readonly connection_silence_ns: NsPair | null;
  readonly connection_silence_status: (typeof MARKET_FLOW_SILENCE_STATUSES)[number];
  readonly connection_last_channel: string | null;
  readonly frontier: {
    readonly channel: typeof MARKET_FLOW_CHANNEL;
    readonly sequence_num: number;
    readonly send_state: (typeof MARKET_FLOW_SEND_STATES)[number];
  } | null;
  /** May be negative (a send time after the observer time). */
  readonly state_age_ns: NsPair | null;
  readonly state_age_status: (typeof MARKET_FLOW_AGE_STATUSES)[number];
  readonly unresolved: readonly string[];
  readonly freshness: (typeof MARKET_FLOW_FRESHNESS)[number];
  readonly unattested_assumptions: readonly string[];
}

export interface MarketFlowBook {
  readonly state: MarketFlowBookState;
  readonly bbo: BookBbo;
  /** null when no l2 message was read: no freshness is invented. */
  readonly freshness: BookFreshness | null;
}

// ---------------------------------------------------------------- heatmap / events

/** Sparse cells: [row index, displayed base quantity]. Missing rows are never allocated. */
export type HeatmapCell = readonly [number, DecimalText];

export type HeatmapColumn =
  | {
      readonly bucket: number;
      readonly status: "LIVE";
      readonly sample_receipt_ns: NsText;
      readonly bid_cover_floor: DecimalText | null;
      readonly ask_cover_ceiling: DecimalText | null;
      readonly bids: readonly HeatmapCell[];
      readonly asks: readonly HeatmapCell[];
    }
  | { readonly bucket: number; readonly status: "NOT_YET_COMPLETE" | "NO_SAMPLE"; readonly sample_receipt_ns: null }
  /** Open family BOOK_<native state>: the book was not LIVE for that sample. */
  | { readonly bucket: number; readonly status: `BOOK_${string}`; readonly sample_receipt_ns: NsText };

export interface MarketFlowHeatmap {
  readonly unit: "DISPLAYED_BASE_QUANTITY";
  readonly aggregation: "LAST_LIVE_SAMPLE_IN_BUCKET";
  readonly tick: DecimalText;
  readonly price_lo: DecimalText;
  readonly price_hi: DecimalText;
  readonly rows: number;
  readonly t0_ns: NsText;
  readonly bucket_ns: NsText;
  readonly columns: readonly HeatmapColumn[];
  readonly zero_semantics: "ABSENT_CELL_IN_LIVE_COLUMN_WITHIN_COVER_IS_OBSERVED_ZERO";
}

interface LevelEventCommon {
  readonly interval_ns: NsPair;
  readonly side: "bid" | "ask";
  readonly price: DecimalText;
}

interface LevelEventGone extends LevelEventCommon {
  readonly last_qty: DecimalText;
  readonly left_censored: boolean;
  readonly persistence_ns: { readonly min: NsText; readonly max: NsText | null };
  readonly trades_at_price_in_interval: number;
}

export type LevelEvent =
  | (LevelEventCommon & { readonly kind: "APPEARED"; readonly cause: "CAUSE_UNDETERMINED"; readonly qty: DecimalText })
  | (LevelEventGone & { readonly kind: "DISAPPEARED"; readonly cause: "CAUSE_UNDETERMINED" })
  | (LevelEventGone & { readonly kind: "LEFT_COVERED_DEPTH"; readonly cause: "NOT_A_DISAPPEARANCE" });

// ---------------------------------------------------------------- root

interface MarketFlowArtifactBase<K extends EvidenceKind> {
  readonly schema_version: typeof MARKET_FLOW_SCHEMA_VERSION;
  readonly product: typeof MARKET_FLOW_PRODUCT;
  readonly calc_version: typeof MARKET_FLOW_CALC_VERSION;
  readonly evidence_kind: K;
  readonly synthetic: true;
  readonly state_label: K;
  readonly flow: MarketFlowIdentity;
  readonly as_of_receipt_ns: NsText;
  readonly anchor_ns: NsText;
  readonly bar_ns: NsText;
  readonly inputs: MarketFlowInputs;
  readonly trades: MarketFlowTrades;
  readonly bars: readonly MarketFlowBar[];
  readonly rolling_delta: { readonly [windowNs: string]: RollingDeltaEntry };
  readonly book: MarketFlowBook;
  readonly heatmap: MarketFlowHeatmap;
  readonly level_events: { readonly items: readonly LevelEvent[]; readonly truncated: boolean };
  readonly assumptions: readonly string[];
  readonly limits: readonly string[];
  readonly economic_metrics: null;
  readonly score: null;
  readonly recommendation: null;
}

export type MarketFlowArtifact = MarketFlowArtifactBase<"SYNTHETIC"> | MarketFlowArtifactBase<"HISTORICAL">;

/** The only thing the reader adds: it assesses no freshness for the artifact it serves. */
export type MarketFlowServing<K extends EvidenceKind> = {
  readonly serving: { readonly freshness_classification: `NOT_ASSESSED_${K}` };
};

export type MarketFlowPublication =
  | (MarketFlowArtifactBase<"SYNTHETIC"> & MarketFlowServing<"SYNTHETIC">)
  | (MarketFlowArtifactBase<"HISTORICAL"> & MarketFlowServing<"HISTORICAL">);
