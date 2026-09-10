// ── NotExposedView — explicit static placeholder for unsupported panels ────
// Market and Scores are not supported by O-02W-D1's canonical snapshot.
// This view makes no legacy API request and contains no demo values.

import React from "react";

export const NotExposedView: React.FC<{ title: string }> = ({ title }) => (
  <div
    data-testid="not-exposed-view"
    className="p-6 font-mono text-xs"
    style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)", color: "var(--text-muted)" }}
  >
    <div className="font-bold mb-1" style={{ color: "var(--text-pri)" }}>
      {title}
    </div>
    <div data-testid="not-exposed-label">NOT_EXPOSED</div>
    <div className="mt-1">
      This view is not supported by the canonical O-02W-D1 operator snapshot in this mission. No market/order-book/
      spread/history/regret endpoint is implemented here, and no fabricated data is shown.
    </div>
  </div>
);
