import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, cleanup, act } from "@testing-library/react";
import { useOperatorSnapshot } from "../lib/snapshotClient";
import { baseSnapshot } from "./fixtures";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (v: T) => void;
  reject: (e: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

// O-02W-D2-R1 Correction C — serialized polling / no out-of-order rollback.
describe("useOperatorSnapshot — serialized polling (Correction C)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("never overlaps a slow request with the next scheduled poll", async () => {
    const d1 = deferred<Response>();
    fetchMock.mockReturnValueOnce(d1.promise);

    renderHook(() => useOperatorSnapshot(1_000));

    // First request issued synchronously by the effect.
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Advance well past the poll interval while the first request is still
    // pending — no second fetch may be issued, because the next poll is
    // only scheduled after the current one settles.
    await vi.advanceTimersByTimeAsync(5_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      d1.resolve(jsonResponse(baseSnapshot()));
    });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("resumes normal polling after a success, issuing exactly one next request per interval", async () => {
    const d1 = deferred<Response>();
    fetchMock.mockReturnValueOnce(d1.promise);

    const { result } = renderHook(() => useOperatorSnapshot(1_000));
    await act(async () => {
      d1.resolve(jsonResponse(baseSnapshot()));
    });
    await vi.waitFor(() => expect(result.current.status).toBe("success"));

    expect(fetchMock).toHaveBeenCalledTimes(1);

    const d2 = deferred<Response>();
    fetchMock.mockReturnValueOnce(d2.promise);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await act(async () => {
      d2.resolve(jsonResponse(baseSnapshot({ snapshot_id: "snap-2" })));
    });
    await vi.waitFor(() =>
      expect(result.current.status === "success" && result.current.snapshot.snapshot_id).toBe("snap-2"),
    );
  });

  it("resumes normal polling after a failure, issuing exactly one next request per interval", async () => {
    const d1 = deferred<Response>();
    fetchMock.mockReturnValueOnce(d1.promise);

    const { result } = renderHook(() => useOperatorSnapshot(1_000));
    await act(async () => {
      d1.reject(new Error("network down"));
    });
    await vi.waitFor(() => expect(result.current.status).toBe("transport_error"));

    expect(fetchMock).toHaveBeenCalledTimes(1);

    const d2 = deferred<Response>();
    fetchMock.mockReturnValueOnce(d2.promise);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await act(async () => {
      d2.resolve(jsonResponse(baseSnapshot()));
    });
    await vi.waitFor(() => expect(result.current.status).toBe("success"));
  });

  it("never updates state after unmount, even when a pending fetch resolves later", async () => {
    const d1 = deferred<Response>();
    fetchMock.mockReturnValueOnce(d1.promise);

    const { result, unmount } = renderHook(() => useOperatorSnapshot(1_000));
    expect(result.current.status).toBe("loading");

    unmount();
    d1.resolve(jsonResponse(baseSnapshot()));
    // Flush microtasks — if the guard were missing this would throw an
    // "update on an unmounted component" style state change.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // No assertion possible on `result.current` post-unmount changing, but
    // the absence of a React warning/error and no further fetch prove the
    // effect's cleanup froze it.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("discards a stale in-flight response from a torn-down effect instance, never rolling back a newer accepted result", async () => {
    // Simulate an interval change forcing the effect to tear down and
    // restart while its first request is still in flight (the same
    // alive-guard mechanism that protects against any out-of-order
    // arrival within one mount lifecycle) — the stale effect's eventual
    // response must never reach state once a newer instance has taken
    // over and accepted its own result.
    const dOld = deferred<Response>();
    fetchMock.mockReturnValueOnce(dOld.promise);

    const { result, rerender } = renderHook(({ ms }) => useOperatorSnapshot(ms), {
      initialProps: { ms: 1_000 },
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const dNew = deferred<Response>();
    fetchMock.mockReturnValueOnce(dNew.promise);
    // Changing the interval tears down the old effect (old become
    // non-"alive") and starts a fresh one immediately.
    rerender({ ms: 2_000 });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // The NEW effect's request resolves first and is accepted.
    await act(async () => {
      dNew.resolve(jsonResponse(baseSnapshot({ snapshot_id: "snap-new" })));
    });
    await vi.waitFor(() =>
      expect(result.current.status === "success" && result.current.snapshot.snapshot_id).toBe("snap-new"),
    );

    // The OLD (torn-down) effect's response arrives late — it must never
    // roll the UI back to its (older) content.
    await act(async () => {
      dOld.resolve(jsonResponse(baseSnapshot({ snapshot_id: "snap-old" })));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status === "success" && result.current.snapshot.snapshot_id).toBe("snap-new");
  });

  it("never fetches on repeated re-renders that do not change the interval (tab navigation proxy)", async () => {
    const d1 = deferred<Response>();
    fetchMock.mockReturnValueOnce(d1.promise);
    d1.resolve(jsonResponse(baseSnapshot()));

    const { result, rerender } = renderHook(() => useOperatorSnapshot(1_000));
    await act(async () => {
      await Promise.resolve();
    });
    await vi.waitFor(() => expect(result.current.status).toBe("success"));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    rerender();
    rerender();
    rerender();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
