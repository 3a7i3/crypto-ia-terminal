// ── Data contracts — Crypto AI Terminal ──────────────────────────────────────

export type MarketRegime =
  | "TREND_BULL" | "TREND_BEAR" | "RANGE" | "VOLATILE" | "UNKNOWN";

export type ConvictionLevel = "VERY_HIGH" | "HIGH" | "MEDIUM" | "LOW" | "SKIP";

export type DecisionState =
  | "CREATED" | "SIGNAL_GENERATED" | "CONTEXT_ENRICHED"
  | "REGIME_VALIDATED" | "RISK_EVALUATED" | "APPROVED"
  | "EXECUTION_PENDING" | "EXECUTED" | "MONITORED" | "CLOSED"
  | "POSTMORTEM_ANALYZED" | "REJECTED" | "EXPIRED"
  | "CANCELLED" | "FAILED" | "VETOED";

export type PostmortemCategory = "VALIDATED" | "LUCKY" | "UNLUCKY" | "MISTAKE";
export type SignalKind          = "trade" | "setup" | "watch" | "hold" | "block";
export type IndicatorState      = "ok" | "warn" | "alert" | "neutral";
export type MiniChartMetric     = "pnl" | "signal_score" | "exposure";

export interface IndicatorSet {
  rsi?:       number;
  bb_pct?:    number;
  atr?:       number;
  macd_bull?: boolean;
  ema_bull?:  boolean;
  squeeze?:   boolean;
}

export interface SymbolSignal {
  symbol:       string;
  price:        number;
  change_24h:   number;
  regime:       MarketRegime;
  score:        number;
  signal:       SignalKind;
  gate_allowed: boolean;
  actionable:   boolean;
  indicators:   IndicatorSet;
  pnl_series?:  number[];
}

export interface OpenPosition {
  id:            string;
  symbol:        string;
  side:          "long" | "short";
  size:          number;
  entry_price:   number;
  current_price: number;
  pnl_usd:       number;
  pnl_pct:       number;
  sl_price?:     number;
  tp_price?:     number;
  regime:        MarketRegime;
  conviction:    ConvictionLevel;
  subaccount:    string;
  opened_at:     string;
  pnl_series:    number[];
}

export interface ClosedPosition {
  id:          string;
  symbol:      string;
  side:        "long" | "short";
  pnl_usd:     number;
  pnl_pct:     number;
  r_multiple:  number;
  regime:      MarketRegime;
  conviction:  ConvictionLevel;
  postmortem:  PostmortemCategory;
  duration_ms: number;
  closed_at:   string;
  pnl_series:  number[];
}

export interface DecisionPacket {
  id:               string;
  symbol:           string;
  state:            DecisionState;
  decision_type:    string;
  score:            number;
  conviction:       ConvictionLevel;
  regime:           MarketRegime;
  rejection_reason?: string;
  postmortem?:      PostmortemCategory;
  created_at:       string;
  duration_ms:      number;
}

export interface ModuleHealth {
  name:        string;
  status:      "ok" | "warn" | "error" | "offline";
  last_tick_ms: number;
  detail?:     string;
}

export interface SystemSnapshot {
  capital_usd:      number;
  daily_pnl:        number;
  open_positions:   number;
  win_rate_7d:      number;
  mode:             "paper" | "testnet" | "live";
  modules:          ModuleHealth[];
  last_updated:     string;
}

// ── Score tracking ────────────────────────────────────────────────────────────

export type RegimeStatus = "STRONG" | "GOOD" | "WEAK" | "AVOID";

export interface RegimePerf {
  regime:  string;
  trades:  number;
  winrate: number;  // 0-1
  avg_pnl: number;  // % as decimal (0.04 = +4%)
  status:  RegimeStatus;
}

export interface OptimizerEntry {
  regime:   string;
  tp:       number;
  sl:       number;
  trailing: number;
  score:    number;
  winrate:  number;  // 0-1
}

export interface ScoreSnapshot {
  trades:       number;
  winrate:      number;  // 0-1
  expectancy:   number;  // decimal e.g. 0.0346
  efficiency:   number;  // 0-1
  pnl_total:    number;  // USD
  avg_mfe:      number;  // 0-1
  avg_mae:      number;  // 0-1 (negative)
  equity_curve: number[]; // cumulative PnL USD per trade
  regimes:      RegimePerf[];
  optimizer:    OptimizerEntry[];
  last_updated: string;
}
