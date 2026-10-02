import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { RuntimeServiceCard, RuntimeServiceView } from "../views/RuntimeServiceView";
import { runtimeServiceFixture } from "./runtimeServiceFixtures";

const response = (body: unknown, status = 200) => ({ ok: status === 200, status, json: async () => body }) as Response;
afterEach(() => vi.unstubAllGlobals());

describe("U2b independent host runtime presentation", () => {
  it("renders host evidence with observed zero restarts and no inferred code or health", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(runtimeServiceFixture()));
    vi.stubGlobal("fetch", fetchMock);
    render(<RuntimeServiceView />);
    await waitFor(() => expect(screen.getByTestId("runtime-service-view")).toHaveTextContent("ÉTAT OBSERVÉ · active"));
    const view = screen.getByTestId("runtime-service-view");
    expect(view).toHaveTextContent("NRestarts0");
    expect(view).toHaveTextContent("MainPID à la capture1234");
    expect(view).toHaveTextContent("Source code · preuve fournieNOT_AVAILABLE");
    expect(view).toHaveTextContent("ni la santé du cycle Advisor");
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/runtime-service", { method: "GET", signal: expect.any(AbortSignal) });
  });
  it("stale active observation never becomes current liveness", () => {
    const d = runtimeServiceFixture(); d.freshness_classification = "STALE";
    render(<RuntimeServiceCard state={{ status: "success", snapshot: d }} />);
    expect(screen.getByTestId("runtime-service-state")).toHaveTextContent("ÉTAT ACTUEL · INCONNU");
    expect(screen.getByTestId("runtime-service-view")).toHaveTextContent("Preuve périmée");
    expect(screen.getByTestId("runtime-service-view")).toHaveTextContent("ActiveState à la captureactive");
  });
  it("timeout keeps PID and restart count unavailable", () => {
    const d = runtimeServiceFixture();
    d.service = { unit: "crypto-advisor.service", query_status: "TIMEOUT", load_state: null, active_state: null, sub_state: null, main_pid: null, restart_count: null, exec_main_started_at_utc: null, invocation_id: null };
    render(<RuntimeServiceCard state={{ status: "success", snapshot: d }} />);
    expect(screen.getByTestId("runtime-service-view")).toHaveTextContent("NRestartsNOT_AVAILABLE");
    expect(screen.getByTestId("runtime-service-view")).toHaveTextContent("MainPID à la captureNOT_AVAILABLE");
  });
  it("host view survives a missing Advisor snapshot on the real System route", async () => {
    window.history.replaceState({}, "", "/paper-live/system");
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url) => Promise.resolve(String(url).endsWith("/runtime-service") ? response(runtimeServiceFixture()) : response({ error_code: "SNAPSHOT_MISSING" }, 503))));
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("runtime-service-view")).toHaveTextContent("ÉTAT OBSERVÉ · active"));
    expect(screen.getByTestId("no-snapshot")).toHaveTextContent("UNRESOLVED");
  });
  it.each([
    [response({ authority: "fake" }), "ERREUR TRANSPORT / CONTRAT"],
    [response({ error_code: "RUNTIME_SERVICE_MISSING" }, 503), "RUNTIME_SERVICE_MISSING"],
  ])("fails closed without fallback to Advisor or API health %#", async (result, text) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(result));
    render(<RuntimeServiceView />);
    await waitFor(() => expect(screen.getByTestId("runtime-service-view")).toHaveTextContent(text));
    expect(screen.getByTestId("runtime-service-view")).toHaveTextContent("INCONNU");
  });
});
