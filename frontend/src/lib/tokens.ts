// ── Token helpers — miroir de tokens.css en JS ───────────────────────────────
// Utiliser ces fonctions dans les composants plutôt que des hex codés en dur.

import type {
  MarketRegime, ConvictionLevel, PostmortemCategory,
  DecisionState, SignalKind, IndicatorState,
} from "../types";

// ── Market state ─────────────────────────────────────────────────────────────

export interface MarketStateInfo {
  glyph: string;
  label: string;
  color: string;
  description: string;
}

export function getMarketState(
  regime: MarketRegime,
  score: number,
  gateAllowed: boolean,
): MarketStateInfo {
  if (!gateAllowed)
    return { glyph: "⊘", label: "Blocked",  color: "var(--danger)", description: "Risk gate closed" };
  if (regime === "TREND_BULL" && score >= 70)
    return { glyph: "↗", label: "Setup",    color: "var(--accent)", description: "High-confidence long setup" };
  if (regime === "TREND_BULL")
    return { glyph: "↗", label: "Bull",     color: "var(--ok)",     description: "Bullish trend" };
  if (regime === "TREND_BEAR" && score >= 70)
    return { glyph: "↘", label: "Short",    color: "var(--danger)", description: "High-confidence short setup" };
  if (regime === "TREND_BEAR")
    return { glyph: "↘", label: "Bear",     color: "var(--danger)", description: "Bearish trend" };
  if (regime === "VOLATILE")
    return { glyph: "~", label: "Volatile", color: "var(--warn)",   description: "High volatility — caution" };
  if (score >= 50)
    return { glyph: "◎", label: "Watch",    color: "var(--warn)",   description: "Monitoring for entry" };
  return   { glyph: "●", label: "Hold",     color: "var(--neutral)","description": "No actionable signal" };
}

// ── Signal badge ─────────────────────────────────────────────────────────────

const SIGNAL_PALETTE: Record<SignalKind, { bg: string; fg: string }> = {
  trade:  { bg: "var(--accent-dim)",  fg: "var(--accent)"   },
  setup:  { bg: "var(--accent-dim)",  fg: "var(--accent)"   },
  watch:  { bg: "var(--warn-dim)",    fg: "var(--warn)"     },
  hold:   { bg: "var(--neutral-dim)", fg: "var(--text-sec)" },
  block:  { bg: "var(--danger-dim)",  fg: "var(--danger)"   },
};
export const signalPalette = (k: SignalKind) => SIGNAL_PALETTE[k] ?? SIGNAL_PALETTE.hold;

// ── Indicator chip ────────────────────────────────────────────────────────────

const CHIP_PALETTE: Record<IndicatorState, { bg: string; fg: string }> = {
  ok:      { bg: "var(--ok-dim)",      fg: "var(--ok)"       },
  warn:    { bg: "var(--warn-dim)",    fg: "var(--warn)"     },
  alert:   { bg: "var(--danger-dim)",  fg: "var(--danger)"   },
  neutral: { bg: "var(--neutral-dim)", fg: "var(--text-sec)" },
};
export const chipPalette = (s: IndicatorState) => CHIP_PALETTE[s] ?? CHIP_PALETTE.neutral;

// ── RSI / BB% state ───────────────────────────────────────────────────────────

export function rsiState(v?: number): IndicatorState {
  if (v == null) return "neutral";
  if (v > 70)    return "alert";
  if (v < 30)    return "ok";
  return "neutral";
}

export function bbState(v?: number): IndicatorState {
  if (v == null) return "neutral";
  if (v > 0.9)   return "warn";
  if (v < 0.1)   return "ok";
  return "neutral";
}

// ── Conviction ────────────────────────────────────────────────────────────────

const CONVICTION_COLOR: Record<ConvictionLevel, string> = {
  VERY_HIGH: "var(--cv-vh)",
  HIGH:      "var(--cv-hi)",
  MEDIUM:    "var(--cv-md)",
  LOW:       "var(--cv-lo)",
  SKIP:      "var(--cv-skip)",
};
export const convictionColor = (l: ConvictionLevel) => CONVICTION_COLOR[l] ?? "var(--neutral)";

const CONVICTION_SHORT: Record<ConvictionLevel, string> = {
  VERY_HIGH: "VH", HIGH: "HI", MEDIUM: "MD", LOW: "LO", SKIP: "—",
};
export const convictionShort = (l: ConvictionLevel) => CONVICTION_SHORT[l] ?? "?";

// ── Postmortem ────────────────────────────────────────────────────────────────

const PM_COLOR: Record<PostmortemCategory, string> = {
  VALIDATED: "var(--pm-validated)",
  LUCKY:     "var(--pm-lucky)",
  UNLUCKY:   "var(--pm-unlucky)",
  MISTAKE:   "var(--pm-mistake)",
};
export const postmortemColor = (c: PostmortemCategory) => PM_COLOR[c] ?? "var(--neutral)";

const PM_SHORT: Record<PostmortemCategory, string> = {
  VALIDATED: "VALID", LUCKY: "LUCKY", UNLUCKY: "UNLUCKY", MISTAKE: "MISTAKE",
};
export const postmortemShort = (c: PostmortemCategory) => PM_SHORT[c];

// ── Decision state ────────────────────────────────────────────────────────────

const DS_COLOR: Partial<Record<DecisionState, string>> = {
  CREATED:             "var(--ds-created)",
  SIGNAL_GENERATED:    "var(--ds-created)",
  CONTEXT_ENRICHED:    "var(--ds-enriched)",
  REGIME_VALIDATED:    "var(--ds-regime)",
  RISK_EVALUATED:      "var(--ds-risk)",
  APPROVED:            "var(--ds-approved)",
  EXECUTION_PENDING:   "var(--ds-pending)",
  EXECUTED:            "var(--ds-executed)",
  MONITORED:           "var(--ds-executed)",
  CLOSED:              "var(--ds-created)",
  POSTMORTEM_ANALYZED: "var(--ds-created)",
  REJECTED:            "var(--ds-rejected)",
  EXPIRED:             "var(--warn)",
  CANCELLED:           "var(--ds-created)",
  FAILED:              "var(--ds-rejected)",
  VETOED:              "var(--ds-vetoed)",
};
export const decisionStateColor = (s: DecisionState) => DS_COLOR[s] ?? "var(--neutral)";

// ── Regime ────────────────────────────────────────────────────────────────────

const REGIME_META: Record<MarketRegime, { glyph: string; label: string; color: string }> = {
  TREND_BULL: { glyph: "↗", label: "Bull",     color: "var(--ok)"      },
  TREND_BEAR: { glyph: "↘", label: "Bear",     color: "var(--danger)"  },
  RANGE:      { glyph: "—", label: "Range",    color: "var(--neutral)" },
  VOLATILE:   { glyph: "~", label: "Volatile", color: "var(--warn)"    },
  UNKNOWN:    { glyph: "?", label: "Unknown",  color: "var(--neutral)" },
};
export const regimeMeta = (r: MarketRegime) => REGIME_META[r] ?? REGIME_META.UNKNOWN;

// ── Utilities ─────────────────────────────────────────────────────────────────

export const pnlColor  = (v: number) => v >= 0 ? "var(--ok)" : "var(--danger)";
export const fmtPrice  = (v: number, d = 2) =>
  v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmtPct    = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
export const fmtUsd    = (v: number) => `${v >= 0 ? "+" : ""}$${Math.abs(v).toFixed(2)}`;
export const fmtDur    = (ms: number) => {
  if (ms < 60_000)     return `${(ms / 1000).toFixed(0)}s`;
  if (ms < 3_600_000)  return `${(ms / 60_000).toFixed(0)}m`;
  return `${(ms / 3_600_000).toFixed(1)}h`;
};
