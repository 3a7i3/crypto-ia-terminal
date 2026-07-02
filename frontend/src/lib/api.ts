// Interfaces pour les réponses de l'API FastAPI (port 8000)

export interface ApiIndicators {
  rsi?:       number;
  bb_pct?:    number;
  atr?:       number;
  macd_bull?: boolean;
  ema_bull?:  boolean;
  squeeze?:   boolean;
}

export interface ApiSymbol {
  symbol:       string;
  prix:         number;
  score:        number;
  regime:       string;
  signal_kind:  string;
  gate_allowed: boolean;
  actionable:   boolean;
  conviction:   string;
  indicators:   ApiIndicators;
}

export interface ApiModule {
  name:         string;
  status:       string;
  last_tick_ms: number;
  detail?:      string;
}

export interface ApiExchange {
  healthy:              boolean;
  consecutive_failures: number;
  last_latency_ms:      number;
  avg_latency_ms:       number;
  uptime_pct:           number;
  total_checks:         number;
  last_error?:          string;
}

export interface SnapshotResponse {
  capital_usd:         number;
  daily_pnl:           number;
  open_positions:      number;
  win_rate_7d:         number;
  mode:                "paper" | "testnet" | "live";
  last_updated:        string;
  cycle:               number;
  safe_mode:           boolean;
  n_symbols:           number;
  n_actionable:        number;
  cycle_duration_ms:   number;
  refusal_breakdown:   Record<string, number>;
  regime_distribution: Record<string, number>;
  exchange:            ApiExchange;
  symbols:             ApiSymbol[];
  positions:           ApiOpenPosition[];
  modules:             ApiModule[];
}

export interface ApiDecision {
  id:               string;
  symbol:           string;
  state:            string;
  decision_type:    string;
  score:            number;
  conviction:       string;
  regime:           string;
  rejection_reason: string | null;
  created_at:       string;
  duration_ms:      number;
}

export interface DecisionsResponse {
  decisions: ApiDecision[];
}

export interface ApiOpenPosition {
  id:            string;
  symbol:        string;
  side:          string;
  size:          number;
  entry_price:   number;
  current_price: number;
  pnl_usd:       number;
  pnl_pct:       number;
  sl_price?:     number;
  tp_price?:     number;
  regime:        string;
  conviction:    string;
  subaccount:    string;
  opened_at:     string;
  pnl_series:    number[];
}

export interface ApiClosedPosition {
  id:          string;
  symbol:      string;
  side:        string;
  pnl_usd:     number;
  pnl_pct:     number;
  r_multiple:  number;
  regime:      string;
  conviction:  string;
  postmortem:  string;
  duration_ms: number;
  closed_at:   string;
  pnl_series:  number[];
}

export interface TradesResponse {
  closed: ApiClosedPosition[];
  open:   ApiOpenPosition[];
}

export interface ApiGate {
  id:       string;
  label:    string;
  required: number;
  current:  number;
  status:   "LOCKED" | "IN_PROGRESS" | "PASSED";
}

export interface ScientificResponse {
  experiment: {
    id:             string;
    title:          string;
    status:         string;
    objective:      string;
    dataset_uuid:   string;
    date_start:     string;
    date_end:       string | null;
    engine_version: string;
    hypotheses:     string[];
  };
  progress: {
    n_closed:      number;
    n_required:    number;
    n_calibration: number;
    wr:            number;
    pf:            number;
    pnl_paper:     number;
  };
  gates:      ApiGate[];
  hypotheses: unknown[];
}
