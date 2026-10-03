import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { MarketMicrostructureView } from "../views/MarketMicrostructureView";
import { microstructureFixture } from "./marketMicrostructureFixtures";

const jsonResponse = (body: unknown, status = 200) => ({ ok: status === 200, status, json: async () => body } as Response);
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("U3b LMI presentation", () => {
  it("distinguishes real zero, missing measures, source freshness and per-symbol freshness", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(microstructureFixture())));
    render(<MarketMicrostructureView />);
    await waitFor(() => expect(screen.getAllByTestId("microstructure-row")).toHaveLength(3));
    const [btc, eth, unavailable] = screen.getAllByTestId("microstructure-row");
    expect(btc).toHaveTextContent("FRESH");
    expect(btc).toHaveTextContent(/12\s345,67/);
    expect(eth).toHaveTextContent("STALE");
    expect(within(eth).getByText("Prix observé").nextElementSibling).toHaveTextContent(/^0$/);
    expect(within(eth).getByText("Flux total · USD").nextElementSibling).toHaveTextContent("NOT_AVAILABLE");
    expect(unavailable).toHaveTextContent("SOURCE_UNAVAILABLE");
    expect(screen.getByTestId("microstructure-coverage")).toHaveTextContent("Demandés 3 · Streamables 2 · Observés 2 · Indisponibles 1");
    fireEvent.click(screen.getByText("Provenance LMI et fenêtre des mesures"));
    expect(screen.getByTestId("microstructure-view")).toHaveTextContent("123");
  });

  it("preserves a positive tiny price in display rather than rounding it to zero", async () => {
    const doc = microstructureFixture(); doc.rows[0].price = 0.00000001;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(doc)));
    render(<MarketMicrostructureView />);
    await waitFor(() => expect(screen.getAllByTestId("microstructure-row")).toHaveLength(3));
    expect(within(screen.getAllByTestId("microstructure-row")[0]).getByText("Prix observé").nextElementSibling).toHaveTextContent("0,00000001");
  });

  it("filters literal symbols and notable observations without refetch or recomputation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(microstructureFixture()));
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketMicrostructureView />);
    await waitFor(() => expect(screen.getAllByTestId("microstructure-row")).toHaveLength(3));
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getAllByTestId("microstructure-row")).toHaveLength(1);
    expect(screen.getByTestId("microstructure-row")).toHaveTextContent("BTCUSDT");
    fireEvent.change(screen.getByLabelText("Recherche LMI"), { target: { value: " eth " } });
    expect(screen.getByTestId("microstructure-empty")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Réinitialiser LMI" }));
    expect(screen.getAllByTestId("microstructure-row")).toHaveLength(3);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/market-microstructure", { method: "GET", signal: expect.any(AbortSignal) });
  });

  it("shows degraded unit provenance and unknown observation time without fabricated healthy state", async () => {
    const doc = microstructureFixture();
    doc.unit_contract_source = "fallback"; doc.unit_contract_degraded = true;
    doc.rows[0].observed_at_utc = null; doc.rows[0].observation_age_s = null; doc.rows[0].freshness_classification = "UNKNOWN";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(doc)));
    render(<MarketMicrostructureView />);
    await waitFor(() => expect(screen.getByTestId("microstructure-units")).toHaveTextContent("DÉGRADÉES"));
    expect(screen.getAllByTestId("microstructure-row")[0]).toHaveTextContent("état actuel INCONNU");
  });

  it("keeps LMI available when Scanner and Advisor are unavailable", async () => {
    window.history.replaceState({}, "", "/paper-live/market");
    const fetchMock = vi.fn((url) => Promise.resolve(String(url).endsWith("/market-microstructure") ? jsonResponse(microstructureFixture()) : jsonResponse({ error_code: "SOURCE_NOT_DEPLOYED" }, 503)));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await waitFor(() => expect(screen.getAllByTestId("microstructure-row")).toHaveLength(3));
    expect(screen.getByTestId("market-error")).toBeInTheDocument();
    expect(screen.getByTestId("market-canonical-context")).toHaveTextContent("SOURCE_NOT_DEPLOYED");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it.each(["api", "invalid", "network"])("keeps %s failures explicit without zero coverage", async (kind) => {
    vi.stubGlobal("fetch", kind === "network" ? vi.fn().mockRejectedValue(new Error("offline")) : vi.fn().mockResolvedValue(kind === "api" ? jsonResponse({ error_code: "MICROSTRUCTURE_MISSING" }, 503) : jsonResponse({ product: "MarketMicrostructureSnapshot" })));
    render(<MarketMicrostructureView />);
    await waitFor(() => expect(screen.getByTestId("microstructure-status")).toHaveTextContent("INCONNU"));
    await waitFor(() => expect(screen.getByTestId("microstructure-view")).not.toHaveTextContent("Chargement"));
    expect(screen.queryByTestId("microstructure-coverage")).not.toBeInTheDocument();
    expect(screen.queryByTestId("microstructure-row")).not.toBeInTheDocument();
  });

  it("replaces a success on polling failure and aborts/unsubscribes on unmount", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(microstructureFixture())).mockResolvedValue(jsonResponse({ error_code: "MICROSTRUCTURE_MISSING" }, 503));
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<MarketMicrostructureView />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getAllByTestId("microstructure-row")).toHaveLength(3);
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(screen.queryByTestId("microstructure-row")).not.toBeInTheDocument();
    expect(screen.getByTestId("microstructure-view")).toHaveTextContent("MICROSTRUCTURE_MISSING");
    const signal = fetchMock.mock.calls[1][1].signal;
    view.unmount();
    expect(signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(20_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("bounds network wait and never overlaps polling requests", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((_url, { signal }) => new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new Error("aborted")))));
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketMicrostructureView />);
    await act(async () => { await vi.advanceTimersByTimeAsync(4_999); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByTestId("microstructure-view")).toHaveTextContent("délai dépassé");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
