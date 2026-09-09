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
});
