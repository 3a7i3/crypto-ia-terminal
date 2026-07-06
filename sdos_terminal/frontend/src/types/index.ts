export interface HealthData {
  ts: string
  observer_pct: number
  dataset_pct: number
  knowledge_pct: number
  evidence_pct: number
  capital_pct: number
  drift_pct: number
  system_state: string
  trading_enabled: boolean
  capital_usd: number
  n_trades: number
  win_rate_pct: number
  profit_factor: number
  heartbeat_age_seconds: number | null
  top_root_cause: string | null
  top_root_cause_pct: number | null
}

export interface PipelineData {
  ts: string
  n_signals: number
  n_traded: number
  n_refused: number
  pass_rate_pct: number
  refusal_breakdown: Record<string, number>
  regime_distribution: Record<string, number>
  capital_usd: number
  cycle: number
  top_layer: string | null
}

export interface PortfolioData {
  ts: string
  n_trades: number
  n_wins: number
  n_losses: number
  win_rate_pct: number
  profit_factor: number
  expectancy_pct: number
  max_drawdown_pct: number
  sharpe: number
  total_pnl_usd: number
  avg_pnl_usd: number
  avg_duration_h: number
  capital_usd: number
}

export interface SystemData {
  health: HealthData
  pipeline: PipelineData
  portfolio: PortfolioData
  sdos_version: string
}

export interface IVCheck {
  id: string
  status: string
  score: number
  duration_ms: number
}

export interface ScientificData {
  ts: string
  certification_level: number
  certification_name: string
  iii: number
  ocs: number
  n_decisions_production: number
  n_knowledge_entries: number
  n_alerts_active: number
  n_counterfactuals: number
  last_cert_at: string | null
  cert_decision: string
  checks: IVCheck[]
}

export interface TimelineEvent {
  packet_id: string
  ts: string
  symbol: string
  event_category: string
  lifecycle_state: string
  regime: string
  conviction: string
  reason: string
}

export interface TimelineData {
  ts: string
  total_packets: number
  n_trade: number
  n_system: number
  n_rejected: number
  n_executed: number
  events: TimelineEvent[]
}

export interface CertRecord {
  certification_id: string
  generated_at: string
  level: number
  level_name: string
  iii: number
  ocs: number
  n_live_passed: number
  n_live_failed: number
  n_decisions_production: number
  decision: string
  checks: IVCheck[]
}

export interface DatasetsData {
  ts: string
  latest_level: number
  latest_iii: number
  latest_ocs: number
  certifications: CertRecord[]
}

export interface RejectionEventData {
  packet_id: string
  ts: string | null
  cycle: number
  symbol: string
  side: string
  regime: string
  trade_allowed: boolean
  first_blocker: string | null
  first_blocker_label: string | null
}

export interface RejectionsData {
  ts: string
  days_covered: string[]
  n_entries: number
  n_unique: number
  by_layer: Record<string, number>
  by_layer_pct: Record<string, number>
  by_regime: Record<string, number>
  by_personality: Record<string, number>
  recent: RejectionEventData[]
}

export interface BurnInData {
  ts: string
  generated_at: string | null
  trades_count: number
  trades_min: number
  wins: number
  wins_min: number
  losses: number
  losses_min: number
  missed_win_count: number
  missed_win_min: number
  good_refusal_count: number
  good_refusal_min: number
  per_regime_min: number
  per_layer_min: number
  win_rate_pct: number
  profit_factor: number
  expectancy_pct: number
  coverage_pct: number
  cri: number | null
  cri_min: number
  calibration_locked: boolean
  go_no_go: string
  blockers: string[]
  warnings: string[]
}

export interface RegretInvestigationData {
  ts: string
  regret_type: string
  n_total: number
  by_layer: Record<string, number>
  by_regime: Record<string, number>
  by_score_bin: Record<string, number>
  by_week: Record<string, number>
  first_evaluated_at: string | null
  last_evaluated_at: string | null
}

export interface TraceStepData {
  step: number
  name: string
  status: boolean | null
  detail: string
}

export interface DecisionPacketData {
  packet_id: string
  observation_id: string
  cycle: number
  symbol: string
  side: string
  score: number
  regime: string
  personality: string
  ts: string | null
  steps: TraceStepData[]
  first_blocker: string | null
  first_blocker_label: string | null
  all_blockers: string[]
  trade_allowed: boolean
  verdict: string
  base_size_usd: number
}

// SVL v1.0 colors
export const SVL = {
  bg:           '#1A1A2E',
  bgPanel:      '#16213E',
  bgCard:       '#0F3460',
  border:       '#2A2A40',
  text:         '#E8E8E8',
  textDim:      '#888888',
  EXPERIMENTAL: '#9E9E9E',
  EMERGING:     '#4499FF',
  OPERATIONAL:  '#FFCC00',
  STRONG:       '#22BB55',
  PREDICTIVE:   '#9933CC',
  ARCHIVED:     '#555555',
  CONTRADICTED: '#FF3333',
  DRIFT:        '#FF8800',
} as const

export function pctColor(pct: number): string {
  if (pct >= 80) return SVL.STRONG
  if (pct >= 60) return SVL.OPERATIONAL
  if (pct >= 40) return SVL.EMERGING
  return SVL.CONTRADICTED
}

export function pctIcon(pct: number): string {
  if (pct >= 80) return '✅'
  if (pct >= 50) return '⚠️'
  return '🚨'
}
