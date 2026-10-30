// ── ModeBadge — canonical portfolio mode (PAPER/REAL_API/TESTNET_API/UNKNOWN) ─
// No fallback from an unknown/invalid value to PAPER; UNKNOWN stays visibly
// UNKNOWN; REAL_API is never relabeled LIVE; mode is never inferred from
// balances, positions, env vars, or frontend configuration — it is rendered
// exactly as the canonical snapshot's `portfolio.mode` field.

import React from "react";
import type { PortfolioMode } from "../types";

const MODE_STYLE: Record<string, { color: string; background: string; label: string }> = {
  PAPER: { color: "var(--neutral)", background: "var(--neutral-dim)", label: "PAPER" },
  REAL_API: { color: "var(--warn)", background: "var(--warn-dim)", label: "REAL_API" },
  TESTNET_API: { color: "var(--accent)", background: "var(--accent-dim)", label: "TESTNET_API" },
  // UNKNOWN is an unavailable/unresolved state, not an actual runtime failure.
  UNKNOWN: { color: "var(--neutral)", background: "var(--neutral-dim)", label: "UNKNOWN" },
};

export const ModeBadge: React.FC<{ mode: PortfolioMode | string | null | undefined }> = ({ mode }) => {
  const key = typeof mode === "string" && mode in MODE_STYLE ? mode : "UNKNOWN";
  const { color, background, label } = MODE_STYLE[key];
  return (
    <span
      data-testid="mode-badge"
      data-mode={key}
      className="mode-badge"
      style={{ color, background, borderRadius: "var(--r-chip)" }}
    >
      <span className="mode-dot" style={{ background: color }} aria-hidden="true" />
      {label}
    </span>
  );
};
