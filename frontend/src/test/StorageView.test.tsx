import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { StorageCard, StorageView } from "../views/StorageView";
import { validateStorageSnapshot } from "../lib/storage";

const file = path.join(process.env.CROSS_STACK_FIXTURES_DIR ?? path.resolve(".cross-stack-fixtures"), "N_storage.json");
const available = fs.existsSync(file);
if (process.env.CROSS_STACK_FIXTURES_DIR && !available) throw new Error("Missing generated Storage fixture");
const fixture = () => JSON.parse(fs.readFileSync(file, "utf8")).body;
const response = (body: unknown, ok = true) => ({ ok, json: async () => body }) as Response;
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe.skipIf(!available)("APP-STORAGE-01 real metadata producer/API/React", () => {
  it("accepts real exact bytes and never treats the mtime as a packet/health verdict", async () => {
    const body = fixture();
    expect(validateStorageSnapshot(body)).toBe(true);
    const fetchMock = vi.fn().mockResolvedValue(response(body));
    vi.stubGlobal("fetch", fetchMock);
    render(<StorageView />);
    await waitFor(() => expect(screen.getByTestId("storage-view")).toHaveTextContent("Capture disponible"));
    expect(screen.getByTestId("storage-view")).toHaveTextContent(`Volume exact en octets${body.total_bytes}`);
    expect(screen.getByTestId("storage-view")).toHaveTextContent("Fichiers à la capture2");
    expect(screen.getByTestId("storage-view")).toHaveTextContent("ne mesure ni le nombre de packets");
    expect(screen.getByTestId("storage-view")).not.toHaveTextContent("SECRET");
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/storage", { method: "GET", signal: expect.any(AbortSignal) });
  });

  it("renders on System even when Advisor and host evidence are missing", async () => {
    window.history.replaceState({}, "", "/paper-live/system");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(url => Promise.resolve(String(url).endsWith("/storage") ? response(fixture()) : response({ error_code: "SNAPSHOT_MISSING" }, false))));
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("storage-view")).toHaveTextContent("Capture disponible"));
    expect(screen.getByTestId("no-snapshot")).toHaveTextContent("non résolu");
    expect(screen.getByTestId("runtime-service-view")).toHaveTextContent("INCONNU");
  });

  it("distinguishes unavailable metrics from a known zero and labels stale values", () => {
    const missing = fixture(); missing.source_status = "SOURCE_CHANGED";
    for (const key of ["entries_observed", "matched_file_count", "total_bytes", "latest_file_modified_at_utc", "inventory_sha256"]) missing[key] = null;
    expect(validateStorageSnapshot(missing)).toBe(true);
    const view = render(<StorageCard state={{ status: "success", snapshot: missing }} />);
    expect(screen.getByTestId("storage-view")).toHaveTextContent("Volume exact en octetsIndisponible");
    const empty = fixture(); empty.entries_observed = empty.matched_file_count = empty.total_bytes = 0; empty.latest_file_modified_at_utc = null;
    expect(validateStorageSnapshot(empty)).toBe(true);
    view.rerender(<StorageCard state={{ status: "success", snapshot: empty }} />);
    expect(screen.getByTestId("storage-view")).toHaveTextContent("Volume exact en octets0");
    expect(screen.getByTestId("storage-view")).toHaveTextContent("ne prouve pas l’absence de décisions");
    const stale = fixture(); stale.snapshot_age_s = 91; stale.freshness_classification = "STALE";
    view.rerender(<StorageCard state={{ status: "success", snapshot: stale }} />);
    expect(screen.getByTestId("storage-view")).toHaveTextContent("volume actuel inconnu");
  });

  it.each([
    (x: any) => { x.total_bytes = true; },
    (x: any) => { x.total_bytes = 1.5; },
    (x: any) => { x.matched_file_count = 4; },
    (x: any) => { x.source_status = "MISSING"; },
    (x: any) => { x.latest_file_modified_at_utc = "2027-02-30T00:00:00Z"; },
    (x: any) => { x.snapshot_age_s = 91; },
    (x: any) => { x.inventory_sha256 = "bad"; },
    (x: any) => { x.private_path = "secret"; },
  ])("rejects a corrupt transport contract %#", async mutate => {
    const body = fixture(); mutate(body);
    expect(validateStorageSnapshot(body)).toBe(false);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(body)));
    render(<StorageView />);
    await waitFor(() => expect(screen.getByTestId("storage-view")).toHaveTextContent("STORAGE_CONTRACT_ERROR"));
    expect(screen.getByTestId("storage-view")).not.toHaveTextContent("Volume exact en octets");
  });

  it("clears old bytes after a hanging JSON refresh and aborts on close", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValueOnce(response(fixture())).mockResolvedValue({ ok: true, json: () => new Promise(() => {}) });
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<StorageView />);
    await act(async () => {});
    expect(screen.getByTestId("storage-view")).toHaveTextContent(`Volume exact en octets${fixture().total_bytes}`);
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(screen.getByTestId("storage-view")).toHaveTextContent("STORAGE_TRANSPORT_ERROR");
    expect(screen.getByTestId("storage-view")).not.toHaveTextContent("Volume exact en octets");
    expect(fetchMock.mock.calls[1][1].signal.aborted).toBe(true);
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(40_000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

it("fails closed on unknown API errors without displaying private text", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ error_code: "PRIVATE_PATH_SECRET" }, false)));
  render(<StorageView />);
  await waitFor(() => expect(screen.getByTestId("storage-view")).toHaveTextContent("STORAGE_SOURCE_ERROR"));
  expect(screen.getByTestId("storage-view")).not.toHaveTextContent("PRIVATE_PATH");
});
