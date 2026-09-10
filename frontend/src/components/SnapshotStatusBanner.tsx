// ── SnapshotStatusBanner — honest transport/API failure presentation ───────
// Never converts a failed fetch into an empty "healthy" snapshot; never
// silently continues presenting cached data as current without saying so.

import React from "react";
import type { SnapshotState } from "../lib/snapshotClient";

export const SnapshotStatusBanner: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "loading") {
    return (
      <div data-testid="snapshot-status-loading" className="px-4 py-2 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
        Loading canonical snapshot…
      </div>
    );
  }

  if (state.status === "success") {
    return null;
  }

  if (state.status === "api_error") {
    return (
      <div
        data-testid="snapshot-status-api-error"
        className="px-4 py-2 font-mono text-xs"
        style={{ background: "#7f1d1d33", color: "#fca5a5", borderBottom: "1px solid #7f1d1d" }}
      >
        API structured failure (HTTP {state.httpStatus}): {state.error.error_code ?? "UNKNOWN_ERROR"} —{" "}
        {state.error.error_message ?? "no error message supplied"}.
        {state.lastSuccess && (
          <span data-testid="snapshot-status-last-known">
            {" "}
            Last successful snapshot: {new Date(state.lastSuccess.fetchedAt).toLocaleTimeString()} (not shown as current).
          </span>
        )}
      </div>
    );
  }

  // transport_error
  return (
    <div
      data-testid="snapshot-status-transport-error"
      className="px-4 py-2 font-mono text-xs"
      style={{ background: "#7f1d1d33", color: "#fca5a5", borderBottom: "1px solid #7f1d1d" }}
    >
      Transport failure: {state.message}.
      {state.lastSuccess && (
        <span data-testid="snapshot-status-last-known">
          {" "}
          Last successful snapshot: {new Date(state.lastSuccess.fetchedAt).toLocaleTimeString()} (not shown as current).
        </span>
      )}
    </div>
  );
};
