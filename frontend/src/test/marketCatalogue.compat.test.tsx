import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MarketView } from "../views/MarketView";
import { validateMarketRadarSnapshot } from "../lib/marketValidation";
import type { MarketRadarSnapshot } from "../lib/marketTypes";

const file = path.join(process.env.CROSS_STACK_FIXTURES_DIR ?? path.resolve(".cross-stack-fixtures"), "R_market_catalogue.json");
const available = existsSync(file);
if (process.env.CROSS_STACK_FIXTURES_DIR && !available) throw new Error("Missing generated full MARKET catalogue fixture");
function fixture(): MarketRadarSnapshot { return JSON.parse(readFileSync(file, "utf8")).body; }
const response = (body: unknown, status = 200) => ({ ok: status === 200, status, json: async () => body }) as Response;

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe.skipIf(!available)("MARKET catalogue: Python producer → reader → API → React", () => {
  it("admits the real bounded catalogue, including BTC beyond top 20 and ETH below threshold", () => {
    const doc = fixture();
    expect(validateMarketRadarSnapshot(doc)).toBe(true);
    expect(doc.top_opportunities).toHaveLength(20);
    expect(doc.catalogue!.qualified_rows).toHaveLength(46);
    expect(doc.catalogue!.rows).toHaveLength(47);
    expect(doc.top_opportunities.some((r) => r.symbol === "BTC/USDT")).toBe(false);
    expect(doc.catalogue!.rows.find((r) => r.symbol === "ETH/USDT")!.avg_confidence).toBe(55);
  });

  it.each([
    ["wrong version", (d: any) => { d.schema_version = "1.0.0"; }],
    ["missing row", (d: any) => { d.catalogue.rows.pop(); }],
    ["wrong population", (d: any) => { d.catalogue.population = "ALL_EXCHANGE_PAIRS"; }],
    ["extra authority", (d: any) => { d.catalogue.rows[0].trade_allowed = true; }],
    ["duplicate", (d: any) => { d.catalogue.rows[1].symbol = d.catalogue.rows[0].symbol; }],
    ["reordered preview", (d: any) => { d.catalogue.qualified_rows.reverse(); }],
    ["bad partition", (d: any) => { d.catalogue.coverage.input_packets = 0; }],
    ["bad unit", (d: any) => { d.catalogue.coverage.future_packets = true; }],
    ["wrong window", (d: any) => { d.catalogue.coverage.start_at_utc = "2026-10-29T08:00:00Z"; }],
    ["naive instant", (d: any) => { d.catalogue.coverage.start_at_utc = "2026-10-30T08:00:00"; }],
    ["future source", (d: any) => { d.source_updated_at_utc = "2026-10-30T12:00:01Z"; }],
    ["no evidence", (d: any) => { d.catalogue.rows[0].n_signals = 0; }],
  ])("rejects inconsistent catalogue: %s", (_name, mutate) => {
    const doc = fixture();
    mutate(doc);
    expect(validateMarketRadarSnapshot(doc)).toBe(false);
  });

  it("accepts explicit-offset catalogue instants by their UTC meaning", () => {
    const doc = fixture();
    doc.catalogue!.coverage.start_at_utc = "2026-10-30T10:00:00+02:00";
    doc.catalogue!.coverage.end_at_utc = "2026-10-30T14:00:00+02:00";
    expect(validateMarketRadarSnapshot(doc)).toBe(true);
  });

  it("paginates 20 rows in source order and searches the entire observed population without a request", async () => {
    const doc = fixture();
    const fetchMock = vi.fn().mockResolvedValue(response(doc));
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketView />);
    await waitFor(() => expect(screen.getAllByTestId("market-opportunity-row")).toHaveLength(20));
    expect(screen.getAllByTestId("market-opportunity-row").map((r) => r.textContent?.split("90.0")[0])[0]).toContain("COIN00/USDT");
    expect(screen.getByRole("button", { name: "Page précédente" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Page suivante" }));
    expect(screen.getAllByTestId("market-opportunity-row")[0]).toHaveTextContent("COIN20/USDT");
    fireEvent.click(screen.getByRole("button", { name: "Page suivante" }));
    expect(screen.getAllByTestId("market-opportunity-row")).toHaveLength(6);
    expect(screen.getByRole("button", { name: "Détail BTC/USDT" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Page suivante" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Recherche symbole"), { target: { value: "  btc " } });
    expect(screen.getByTestId("market-opportunity-row")).toHaveTextContent("49.0");
    expect(screen.getByLabelText("Population")).toBeDisabled();
    expect(screen.getByTestId("market-scanner-coverage")).toHaveTextContent("Recherche élargie à tous les observés");
    fireEvent.click(screen.getByRole("button", { name: "Détail BTC/USDT" }));
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("tous les paquets observés");
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("49.0");
    fireEvent.change(screen.getByLabelText("Recherche symbole"), { target: { value: "ETH" } });
    expect(screen.queryByTestId("market-symbol-detail")).not.toBeInTheDocument();
    expect(screen.getByTestId("market-opportunity-row")).toHaveTextContent("ETH/USDT");
    expect(screen.getByTestId("market-opportunity-row")).toHaveTextContent("55.0");
    fireEvent.change(screen.getByLabelText("Recherche symbole"), { target: { value: "ABSENT" } });
    expect(screen.getByTestId("market-filter-empty")).toHaveTextContent("Le marché n’est pas déclaré vide");
    fireEvent.click(screen.getByRole("button", { name: "Réinitialiser" }));
    expect(screen.getAllByTestId("market-opportunity-row")).toHaveLength(20);
    expect(screen.getByLabelText("Population")).toHaveValue("qualified");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/market", { method: "GET" });
  });

  it("uses one alternate heatmap with the same published order, values and accessible detail", async () => {
    const doc = fixture();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(doc)));
    render(<MarketView />);
    await waitFor(() => expect(screen.getAllByTestId("market-opportunity-row")).toHaveLength(20));
    fireEvent.click(screen.getByRole("button", { name: "Carte des symboles" }));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const cells = screen.getAllByRole("button", { name: /^Détail / });
    expect(cells.map((c) => c.textContent?.split("90.0")[0])[0]).toContain("COIN00/USDT");
    expect(cells).toHaveLength(20);
    expect(cells[0]).toHaveTextContent("90.0 · score moyen");
    fireEvent.click(cells[0]);
    expect(screen.getByTestId("market-symbol-detail")).toHaveFocus();
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("90.0");
    expect(screen.getByTestId("market-symbol-detail")).toHaveTextContent("Ancien · périmé · historique");
    fireEvent.keyDown(screen.getByTestId("market-symbol-detail"), { key: "Escape" });
    expect(screen.queryByTestId("market-symbol-detail")).not.toBeInTheDocument();
    expect(cells[0]).toHaveFocus();
    fireEvent.change(screen.getByLabelText("Régime publié"), { target: { value: "VOLATILE" } });
    expect(screen.getAllByRole("button", { name: /^Détail / })).toHaveLength(15);
    expect(screen.getByTestId("market-view")).toHaveTextContent("état actuel du marché INCONNU");
    expect(screen.getByTestId("market-view")).toHaveTextContent("Non disponible : les volumes de marché");
    fireEvent.click(screen.getByRole("button", { name: "Tableau" }));
    expect(screen.getAllByTestId("market-opportunity-row")).toHaveLength(15);
    expect(screen.queryByTestId("market-heatmap")).not.toBeInTheDocument();
  });

  it("clamps a page after source replacement and removes old detail on error", async () => {
    vi.useFakeTimers();
    const first = fixture();
    const reduced = fixture();
    reduced.catalogue!.rows = reduced.catalogue!.rows.slice(0, 1);
    reduced.catalogue!.qualified_rows = reduced.catalogue!.qualified_rows.slice(0, 1);
    reduced.top_opportunities = reduced.top_opportunities.slice(0, 1);
    reduced.universe_size = reduced.actionable_count = reduced.packets_observed = 1;
    reduced.watchlist_count = 0;
    Object.assign(reduced.catalogue!.coverage, { input_packets: 1, included_packets: 1, outside_window_packets: 0, future_packets: 0, unresolved_timestamp_packets: 0 });
    expect(validateMarketRadarSnapshot(reduced)).toBe(true);
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(response(first))
      .mockResolvedValueOnce(response(reduced))
      .mockResolvedValueOnce(response({ error_code: "MARKET_SNAPSHOT_MISSING" }, 503)));
    render(<MarketView />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(screen.getByRole("button", { name: "Page suivante" }));
    fireEvent.click(screen.getByRole("button", { name: "Page suivante" }));
    fireEvent.click(screen.getByRole("button", { name: "Détail BTC/USDT" }));
    expect(screen.getByTestId("market-symbol-detail")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(screen.getByTestId("market-opportunity-row")).toHaveTextContent("COIN00/USDT");
    expect(screen.queryByTestId("market-symbol-detail")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Page suivante" })).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(screen.getByTestId("market-error")).toHaveTextContent("indisponibles");
    expect(screen.queryByTestId("market-scanner-coverage")).not.toBeInTheDocument();
  });
});
