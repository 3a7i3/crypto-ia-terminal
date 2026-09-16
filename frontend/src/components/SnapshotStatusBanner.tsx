// ── SnapshotStatusBanner — honest canonical-domain status presentation ─────
// Never converts a failed fetch into an empty "healthy" snapshot; never
// silently continues presenting cached data as current without saying so.
// WEB-UX-01 only changes visual severity: SNAPSHOT_MISSING is unresolved,
// not a critical runtime failure. Transport failures remain critical.

import React from "react";
import type { SnapshotState } from "../lib/snapshotClient";

export const SnapshotStatusBanner: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "loading") {
    return (
      <div data-testid="snapshot-status-loading" className="snapshot-banner snapshot-banner-neutral">
        Loading canonical snapshot…
      </div>
    );
  }

  if (state.status === "success") {
    return null;
  }

  if (state.status === "api_error") {
    const errorCode = state.error.error_code ?? "UNKNOWN_ERROR";
    const unresolved = errorCode === "SNAPSHOT_MISSING";
    return (
      <div
        data-testid="snapshot-status-api-error"
        className={`snapshot-banner ${unresolved ? "snapshot-banner-neutral" : "snapshot-banner-critical"}`}
      >
        {unresolved ? "Canonical snapshot unresolved" : `API structured failure (HTTP ${state.httpStatus})`}: {errorCode} —{" "}
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

  return (
    <div
      data-testid="snapshot-status-transport-error"
      className="snapshot-banner snapshot-banner-critical"
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
