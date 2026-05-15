// ── Badges.tsx — Tous les badges et chips du dashboard ───────────────────────
// SignalBadge | IndicatorChip | ConvictionBadge | RegimeBadge
// PostmortemBadge | DecisionStateBadge | IndicatorChipSet

import React from "react";
import type {
  SignalKind, IndicatorState, ConvictionLevel,
  MarketRegime, PostmortemCategory, DecisionState, IndicatorSet,
} from "../types";
import {
  signalPalette, chipPalette, convictionColor, convictionShort,
  postmortemColor, postmortemShort, decisionStateColor, regimeMeta,
  rsiState, bbState,
} from "../lib/tokens";

// ── Chip de base ──────────────────────────────────────────────────────────────

export const Chip: React.FC<{
  label: string;
  value?: string;
  state: IndicatorState;
}> = ({ label, value, state }) => {
  const { bg, fg } = chipPalette(state);
  return (
    <span
      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 font-mono text-[11px] font-semibold leading-none"
      style={{ background: bg, color: fg, borderRadius: "var(--r-chip)" }}
    >
      <span style={{ opacity: 0.65 }}>{label}</span>
      {value !== undefined && <span className="font-bold ml-0.5">{value}</span>}
    </span>
  );
};

// ── Signal badge ──────────────────────────────────────────────────────────────

const SIGNAL_LABEL: Record<SignalKind, string> = {
  trade: "TRADE", setup: "SETUP", watch: "WATCH", hold: "HOLD", block: "BLOCK",
};

export const SignalBadge: React.FC<{ kind: SignalKind }> = ({ kind }) => {
  const { bg, fg } = signalPalette(kind);
  return (
    <span
      className="inline-block px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest uppercase leading-none"
      style={{ background: bg, color: fg, borderRadius: "var(--r-chip)" }}
    >
      {SIGNAL_LABEL[kind]}
    </span>
  );
};

// ── Indicateurs techniques ────────────────────────────────────────────────────

export const RSIChip: React.FC<{ value?: number }> = ({ value }) => {
  if (value == null) return <Chip label="RSI" value="—" state="neutral" />;
  const state = rsiState(value);
  const suffix = state === "alert" ? "!" : state === "ok" ? "v" : "";
  return <Chip label="RSI" value={`${value.toFixed(0)}${suffix ? " " + suffix : ""}`} state={state} />;
};

export const BBChip: React.FC<{ value?: number }> = ({ value }) => {
  if (value == null) return <Chip label="BB%" value="—" state="neutral" />;
  return <Chip label="BB%" value={value.toFixed(2)} state={bbState(value)} />;
};

export const ATRChip: React.FC<{ value?: number }> = ({ value }) => {
  if (value == null) return <Chip label="ATR" value="—" state="neutral" />;
  return <Chip label="ATR" value={value.toFixed(3)} state="neutral" />;
};

export const BoolChip: React.FC<{
  label: string;
  value?: boolean;
  positiveWhenTrue?: boolean;
}> = ({ label, value, positiveWhenTrue = true }) => {
  if (value == null) return <Chip label={label} value="—" state="neutral" />;
  const positive = positiveWhenTrue ? value : !value;
  return <Chip label={label} value={value ? "OK" : "—"} state={positive ? "ok" : "neutral"} />;
};

export const IndicatorChipSet: React.FC<{ indicators: IndicatorSet }> = ({
  indicators,
}) => (
  <div className="flex flex-wrap gap-1">
    <RSIChip  value={indicators.rsi} />
    <BBChip   value={indicators.bb_pct} />
    <ATRChip  value={indicators.atr} />
    <BoolChip label="MACD" value={indicators.macd_bull} />
    <BoolChip label="EMA"  value={indicators.ema_bull} />
    <BoolChip label="SQZ"  value={indicators.squeeze} positiveWhenTrue={false} />
  </div>
);

// ── Conviction badge ──────────────────────────────────────────────────────────

export const ConvictionBadge: React.FC<{ level: ConvictionLevel }> = ({ level }) => {
  const color = convictionColor(level);
  return (
    <span
      className="inline-block px-1.5 py-0.5 font-mono text-[10px] font-bold leading-none"
      style={{ color, background: `${color}18`, borderRadius: "var(--r-chip)" }}
      title={`Conviction: ${level}`}
    >
      {convictionShort(level)}
    </span>
  );
};

// ── Regime badge ──────────────────────────────────────────────────────────────

export const RegimeBadge: React.FC<{ regime: MarketRegime }> = ({ regime }) => {
  const { glyph, label, color } = regimeMeta(regime);
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[10px] font-semibold leading-none"
      style={{ color, background: `${color}18`, borderRadius: "var(--r-chip)" }}
    >
      <span aria-hidden="true">{glyph}</span>
      {label}
    </span>
  );
};

// ── Postmortem badge ──────────────────────────────────────────────────────────

export const PostmortemBadge: React.FC<{ category: PostmortemCategory }> = ({
  category,
}) => {
  const color = postmortemColor(category);
  return (
    <span
      className="inline-block px-1.5 py-0.5 font-mono text-[10px] font-bold tracking-wide leading-none"
      style={{ color, background: `${color}18`, borderRadius: "var(--r-chip)" }}
    >
      {postmortemShort(category)}
    </span>
  );
};

// ── Decision state badge ──────────────────────────────────────────────────────

export const DecisionStateBadge: React.FC<{ state: DecisionState }> = ({
  state,
}) => {
  const color = decisionStateColor(state);
  return (
    <span
      className="inline-block px-1.5 py-0.5 font-mono text-[10px] font-semibold leading-none"
      style={{ color, background: `${color}18`, borderRadius: "var(--r-chip)" }}
    >
      {state.replace(/_/g, " ")}
    </span>
  );
};

// ── Mode badge (paper / testnet / live) ───────────────────────────────────────

const MODE_STYLE: Record<string, { color: string; label: string }> = {
  paper:   { color: "#9ca3af", label: "PAPER"   },
  testnet: { color: "#3b82f6", label: "TESTNET" },
  live:    { color: "#22c55e", label: "LIVE"    },
};

export const ModeBadge: React.FC<{ mode: "paper" | "testnet" | "live" }> = ({
  mode,
}) => {
  const { color, label } = MODE_STYLE[mode] ?? MODE_STYLE.paper;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest leading-none"
      style={{ color, background: `${color}18`, borderRadius: "var(--r-chip)" }}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{ background: color }}
        aria-hidden="true"
      />
      {label}
    </span>
  );
};
