// ── ModeBadge — canonical portfolio mode (PAPER/REAL_API/TESTNET_API/UNKNOWN) ─
// No fallback from an unknown/invalid value to PAPER; UNKNOWN stays visibly
// UNKNOWN; REAL_API is never relabeled LIVE; mode is never inferred from
// balances, positions, env vars, or frontend configuration — it is rendered
// exactly as the canonical snapshot's `portfolio.mode` field.

import React from "react";
import type { PortfolioMode } from "../types";

const MODE_STYLE: Record<string, { color: string; label: string }> = {
  PAPER: { color: "#9ca3af", label: "PAPER" },
  REAL_API: { color: "#f97316", label: "REAL_API" },
  TESTNET_API: { color: "#3b82f6", label: "TESTNET_API" },
  UNKNOWN: { color: "#ef4444", label: "UNKNOWN" },
};

export const ModeBadge: React.FC<{ mode: PortfolioMode | string | null | undefined }> = ({ mode }) => {
  const key = typeof mode === "string" && mode in MODE_STYLE ? mode : "UNKNOWN";
  const { color, label } = MODE_STYLE[key];
  return (
    <span
      data-testid="mode-badge"
      data-mode={key}
      className="inline-flex items-center gap-1 px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest leading-none"
      style={{ color, background: `${color}18`, borderRadius: "var(--r-chip)" }}
    >
      <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: color }} aria-hidden="true" />
      {label}
    </span>
  );
};
