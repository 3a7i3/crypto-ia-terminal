import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MarketView } from "../views/MarketView";

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function marketSnapshot(freshness: "FRESH" | "STALE" = "FRESH") {
  return {
    schema_version: "1.0.0",
    product: "CryptoRadar",
    domain: "market",
    authority: "OBSERVATIONAL_TELEMETRY",
    mode: "OBSERVATION",
    generated_at_utc: "2026-09-14T20:00:00Z",
    source_updated_at_utc: "2026-09-14T19:59:00Z",
    window_hours: 24,
    min_confidence: 65,
    packets_observed: 5,
    market_regime: "bull_trend",
    universe_size: 2,
    actionable_count: 1,
    watchlist_count: 1,
    top_opportunities: [
      {
        symbol: "BTC/USDT",
        avg_confidence: 75,
        max_confidence: 80,
        n_signals: 2,
        dominant_side: "LONG",
        dominance_pct: 100,
        regime: "bull_trend",
      },
    ],
    snapshot_age_s: freshness === "FRESH" ? 20 : 120,
    freshness_classification: freshness,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("MarketView", () => {
  it("renders the same CryptoRadar opportunity truth for desktop and mobile without execution levels", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(marketSnapshot())));
    render(<MarketView />);

    await waitFor(() => expect(screen.getByTestId("market-freshness")).toHaveTextContent("FRESH"));
    const view = screen.getByTestId("market-view");
    expect(view).toHaveTextContent("OBSERVATIONAL_TELEMETRY");
    expect(view).toHaveTextContent("rolling 24h observation window");
    expect(view).toHaveTextContent("display classification only");

    const row = screen.getByTestId("market-opportunity-row");
    const card = screen.getByTestId("market-opportunity-card");
    for (const expected of ["BTC/USDT", "75.0", "80.0", "LONG", "100%", "2", "bull_trend"]) {
      expect(row).toHaveTextContent(expected);
      expect(card).toHaveTextContent(expected);
    }

    expect(screen.getByTestId("market-opportunity-cards")).toBeInTheDocument();
    expect(view).not.toHaveTextContent("Entry");
    expect(view).not.toHaveTextContent("Stop Loss");
    expect(view).not.toHaveTextContent("Take Profit");
    expect(view).not.toHaveTextContent("trade_allowed");
  });

  it("renders stale evidence explicitly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(marketSnapshot("STALE"))));
    render(<MarketView />);

    await waitFor(() => expect(screen.getByTestId("market-freshness")).toHaveTextContent("STALE"));
    expect(screen.getByTestId("market-view")).toHaveTextContent("120s");
  });

  it("keeps provenance inspectable without changing source values", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(marketSnapshot())));
    render(<MarketView />);

    await waitFor(() => expect(screen.getByText("Provenance & source timing")).toBeInTheDocument());
    const view = screen.getByTestId("market-view");
    expect(view).toHaveTextContent("2026-09-14 20:00:00Z");
    expect(view).toHaveTextContent("2026-09-14 19:59:00Z");
  });

  it("renders explicit API failure rather than an empty healthy market", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error_code: "MARKET_SNAPSHOT_MISSING", error_message: "missing" },
          503,
        ),
      ),
    );
    render(<MarketView />);

    await waitFor(() => expect(screen.getByTestId("market-error")).toBeInTheDocument());
    expect(screen.getByTestId("market-view")).toHaveTextContent("MARKET_SNAPSHOT_MISSING");
  });
});

function scannerSnapshot() {
  const doc = marketSnapshot();
  doc.universe_size = 60;
  doc.actionable_count = 55;
  doc.top_opportunities = [
    { ...doc.top_opportunities[0], symbol: "BTC/USDT" },
    { ...doc.top_opportunities[0], symbol: "ETH/USDT", dominant_side: "SHORT" },
    { ...doc.top_opportunities[0], symbol: "SOL/USDT", dominant_side: "MIXED" },
  ];
  return doc;
}

describe("U3a scanner", () => {
  it("combines search and side filters without reranking or refetching, resets and distinguishes no match", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(scannerSnapshot()));
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketView />);
    await waitFor(() => expect(screen.getAllByTestId("market-opportunity-row")).toHaveLength(3));
    expect(screen.getByTestId("market-scanner-coverage")).toHaveTextContent("Couverture partielle");
    fireEvent.change(screen.getByLabelText("Biais dominant"), { target: { value: "SHORT" } });
    expect(screen.getAllByTestId("market-opportunity-row")).toHaveLength(1);
    expect(screen.getByTestId("market-opportunity-card")).toHaveTextContent("ETH/USDT");
    fireEvent.change(screen.getByLabelText("Recherche symbole"), { target: { value: "  eth  " } });
    fireEvent.click(screen.getAllByRole("button", { name: "Détail ETH/USDT" })[0]);
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("packets au seuil ≥ 65");
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("exacts non disponibles");
    fireEvent.change(screen.getByLabelText("Recherche symbole"), { target: { value: "BTC" } });
    expect(screen.queryByTestId("market-symbol-detail")).not.toBeInTheDocument();
    expect(screen.getByTestId("market-filter-empty")).toHaveTextContent("Le marché n’est pas déclaré vide");
    expect(screen.queryByTestId("market-empty")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Réinitialiser" }));
    expect(screen.getAllByTestId("market-opportunity-row").map((r) => r.textContent)).toEqual([
      expect.stringContaining("BTC/USDT"), expect.stringContaining("ETH/USDT"), expect.stringContaining("SOL/USDT"),
    ]);
    fireEvent.change(screen.getByLabelText("Biais dominant"), { target: { value: "MIXED" } });
    expect(screen.getByTestId("market-opportunity-row")).toHaveTextContent("SOL/USDT");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/market", { method: "GET" });
  });

  it("shows stale detail as historical and preserves explicit empty evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(marketSnapshot("STALE"))));
    render(<MarketView />);
    await waitFor(() => expect(screen.getByTestId("market-freshness")).toHaveTextContent("STALE"));
    fireEvent.click(screen.getAllByRole("button", { name: "Détail BTC/USDT" })[0]);
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("STALE · historique");
    expect(screen.getByTestId("market-view")).toHaveTextContent("état actuel du marché INCONNU");
    fireEvent.click(screen.getByRole("button", { name: "Fermer le détail" }));
    expect(screen.queryByTestId("market-symbol-detail")).not.toBeInTheDocument();
  });

  it("rejects inconsistent coverage in HTTP 200 data", async () => {
    const doc = scannerSnapshot();
    doc.actionable_count = 1;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(doc)));
    render(<MarketView />);
    await waitFor(() => expect(screen.getByTestId("market-error")).toBeInTheDocument());
    expect(screen.queryByTestId("market-scanner-coverage")).not.toBeInTheDocument();
  });
});


it("resolves selected detail from replacement snapshots and hides it on polling error", async () => {
  vi.useFakeTimers();
  try {
    const first = marketSnapshot();
    const second = marketSnapshot();
    second.top_opportunities[0].avg_confidence = 70;
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(first))
      .mockResolvedValueOnce(jsonResponse(second))
      .mockResolvedValueOnce(jsonResponse({ error_code: "MARKET_SNAPSHOT_MISSING" }, 503));
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketView />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(screen.getAllByRole("button", { name: "Détail BTC/USDT" })[0]);
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("75.0");
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("70.0");
    expect(screen.getByTestId("market-symbol-detail")).not.toHaveTextContent("75.0");
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(screen.getByTestId("market-error")).toHaveTextContent("MARKET unavailable");
    expect(screen.queryByTestId("market-symbol-detail")).not.toBeInTheDocument();
  } finally { vi.useRealTimers(); }
});
