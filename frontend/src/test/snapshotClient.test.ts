import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useOperatorSnapshot, SNAPSHOT_ENDPOINT } from "../lib/snapshotClient";
import { baseSnapshot } from "./fixtures";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("useOperatorSnapshot", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches only the canonical GET /api/operator/v1/snapshot endpoint, no legacy path", async () => {
    fetchMock.mockResolvedValue(jsonResponse(baseSnapshot()));
    const { result } = renderHook(() => useOperatorSnapshot(60_000));

    await waitFor(() => expect(result.current.status).toBe("success"));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(SNAPSHOT_ENDPOINT);
    expect(url).not.toMatch(/\/api\/(snapshot|decisions|trades)$/);
    expect((init as RequestInit).method).toBe("GET");
  });

  it("issues no non-GET request", async () => {
    fetchMock.mockResolvedValue(jsonResponse(baseSnapshot()));
    renderHook(() => useOperatorSnapshot(60_000));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    for (const call of fetchMock.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      expect((init?.method ?? "GET").toUpperCase()).toBe("GET");
    }
  });

  it("produces an explicit unavailable/error state on a malformed/unusable response", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ unexpected: "shape" }));
    const { result } = renderHook(() => useOperatorSnapshot(60_000));
    await waitFor(() => expect(result.current.status).toBe("transport_error"));
  });

  it("displays HTTP 503 structured errors without fabricating domain data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error_code: "SNAPSHOT_MISSING", error_message: "no snapshot on disk" }, 503),
    );
    const { result } = renderHook(() => useOperatorSnapshot(60_000));
    await waitFor(() => expect(result.current.status).toBe("api_error"));
    if (result.current.status === "api_error") {
      expect(result.current.error.error_code).toBe("SNAPSHOT_MISSING");
      expect(result.current.httpStatus).toBe(503);
    }
  });

  it("never converts a transport failure into an empty healthy snapshot", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));
    const { result } = renderHook(() => useOperatorSnapshot(60_000));
    await waitFor(() => expect(result.current.status).toBe("transport_error"));
    expect(result.current.status).not.toBe("success");
  });

  // O-02W-D2-R1.1 case 15 — every malformed HTTP 200 body MASTER
  // independently reproduced must produce transport_error, never success.
  it.each([
    ["portfolio.status = object", () => {
      const s = baseSnapshot();
      (s.portfolio as unknown as Record<string, unknown>).status = { bad: true };
      return s;
    }],
    ["system_health.freshness = array", () => {
      const s = baseSnapshot();
      (s.system_health as unknown as Record<string, unknown>).freshness = ["bad"];
      return s;
    }],
    ["open_positions[].side = object", () => {
      const s = baseSnapshot();
      s.portfolio.open_positions = {
        semantics: "PRESENT",
        value: [
          {
            position_id: "p1",
            symbol: "BTCUSDT",
            side: { bad: true },
            size_usd: 100,
            entry_price: 50000,
            current_price: { value: 51000, semantics: "PRESENT" },
            current_price_observed_at_utc: null,
            tp_price: null,
            sl_price: null,
            tp_sl_source: "original",
            unrealized_pnl_usd: { value: 20, semantics: "PRESENT" },
            unrealized_pnl_pct: { value: 2, semantics: "PRESENT" },
            opened_at: null,
            regime: { value: "TREND_BULL", semantics: "PRESENT" },
            restored_without_regime: false,
            personality: null,
            restored: false,
          },
        ],
      } as never;
      return s;
    }],
    ["contradictory confidence_raw", () => {
      const s = baseSnapshot();
      s.decision_pipeline.per_symbol_decisions = [
        {
          symbol: "ETHUSDT",
          packet_id: null,
          context_id: null,
          created_cycle_id: null,
          created_at: { value: null, semantics: "UNKNOWN" },
          latest_transition_at_utc: { value: null, semantics: "UNKNOWN" },
          side: { value: null, semantics: "UNKNOWN" },
          confidence_raw: { value: null, semantics: "PRESENT" },
          confidence_adjusted: { value: null, semantics: "UNKNOWN" },
          regime: { value: null, semantics: "UNKNOWN" },
          lifecycle_state: { value: null, semantics: "UNKNOWN" },
          is_actionable: { value: false, semantics: "FALSE", authority: "EXECUTION_AUTHORITY" },
          trade_allowed: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
          first_blocker: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
        },
      ] as never;
      return s;
    }],
  ] as const)("rejects malformed body (%s) as transport_error, never success", async (_label, build) => {
    fetchMock.mockResolvedValue(jsonResponse(build()));
    const { result } = renderHook(() => useOperatorSnapshot(60_000));
    await waitFor(() => expect(result.current.status).toBe("transport_error"));
    expect(result.current.status).not.toBe("success");
  });

  // O-02W-D2-R1.2 — `isObservedValue()` validates the generic null-
  // semantics matrix but not the generic type `T`; MASTER reproduced a
  // string-valued boolean/numeric field and a non-array EMPTY list
  // slipping through as `true`. Every body below must produce
  // transport_error, never success.
  it.each([
    ["string-valued boot_alive", () => {
      const s = baseSnapshot();
      s.system_health.boot_alive = { value: "false", semantics: "PRESENT" } as never;
      return s;
    }],
    ["string-valued is_actionable", () => {
      const s = baseSnapshot();
      s.decision_pipeline.per_symbol_decisions = [
        {
          symbol: "ETHUSDT",
          packet_id: null,
          context_id: null,
          created_cycle_id: null,
          created_at: { value: null, semantics: "UNKNOWN" },
          latest_transition_at_utc: { value: null, semantics: "UNKNOWN" },
          side: { value: null, semantics: "UNKNOWN" },
          confidence_raw: { value: null, semantics: "UNKNOWN" },
          confidence_adjusted: { value: null, semantics: "UNKNOWN" },
          regime: { value: null, semantics: "UNKNOWN" },
          lifecycle_state: { value: null, semantics: "UNKNOWN" },
          is_actionable: { value: "false", semantics: "PRESENT", authority: "EXECUTION_AUTHORITY" },
          trade_allowed: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
          first_blocker: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
        },
      ] as never;
      return s;
    }],
    ["string-valued numeric equity", () => {
      const s = baseSnapshot();
      s.portfolio.paper_equity_usd = { value: "1000", semantics: "PRESENT" } as never;
      return s;
    }],
    ["non-array EMPTY open_positions", () => {
      const s = baseSnapshot();
      s.portfolio.open_positions = { semantics: "EMPTY", value: "" } as never;
      return s;
    }],
    ["incorrect authority mapping (trade_allowed as EXECUTION_AUTHORITY)", () => {
      const s = baseSnapshot();
      s.decision_pipeline.per_symbol_decisions = [
        {
          symbol: "ETHUSDT",
          packet_id: null,
          context_id: null,
          created_cycle_id: null,
          created_at: { value: null, semantics: "UNKNOWN" },
          latest_transition_at_utc: { value: null, semantics: "UNKNOWN" },
          side: { value: null, semantics: "UNKNOWN" },
          confidence_raw: { value: null, semantics: "UNKNOWN" },
          confidence_adjusted: { value: null, semantics: "UNKNOWN" },
          regime: { value: null, semantics: "UNKNOWN" },
          lifecycle_state: { value: null, semantics: "UNKNOWN" },
          is_actionable: { value: false, semantics: "FALSE", authority: "EXECUTION_AUTHORITY" },
          trade_allowed: { value: false, semantics: "FALSE", authority: "EXECUTION_AUTHORITY" },
          first_blocker: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
        },
      ] as never;
      return s;
    }],
  ] as const)("rejects R1.2 malformed body (%s) as transport_error, never success", async (_label, build) => {
    fetchMock.mockResolvedValue(jsonResponse(build()));
    const { result } = renderHook(() => useOperatorSnapshot(60_000));
    await waitFor(() => expect(result.current.status).toBe("transport_error"));
    expect(result.current.status).not.toBe("success");
  });
});
