import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MarketView } from "../views/MarketView";
import { MarketVenuesView } from "../views/MarketVenuesView";
import { validateVenuePublication, type VenuePublication } from "../lib/venueComparison";
const dir = process.env.CROSS_STACK_FIXTURES_DIR;
const suite = dir ? describe : describe.skip;
const fixture = (name = "S_market_venues") => JSON.parse(readFileSync(path.join(dir!, name + ".json"), "utf8")).body as VenuePublication;
const response = (body: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
afterEach(() => vi.unstubAllGlobals());

suite("Venue publication through real offline producer/reader/API", () => {
  it.each(["S_market_venues", "S_market_venues_stale", "S_market_venues_unresolved"])("admits %s without changing prices", name => {
    expect(validateVenuePublication(fixture(name))).toBe(true);
  });
  it.each([
    (d: VenuePublication) => { (d as unknown as Record<string, unknown>).secret = "extra"; },
    (d: VenuePublication) => { d.source_counts.expected = 0; },
    (d: VenuePublication) => { d.groups[0].rows[0].bid = 100 as unknown as string; },
    (d: VenuePublication) => { d.groups[0].rows[0].bid = "0"; },
    (d: VenuePublication) => { d.groups[0].rows[0].spread_bps = "NaN"; },
    (d: VenuePublication) => { d.groups[0].comparisons.pop(); },
    (d: VenuePublication) => { d.groups[0].rows[1].observer_clock_id = "OTHER_CLOCK"; },
    (d: VenuePublication) => { d.execution_authority = true as false; },
    (d: VenuePublication) => { d.groups[0].instrument.quote_asset_id = "UNKNOWN"; },
    (d: VenuePublication) => { d.valid_until_utc = null; },
  ])("refuses invalid or inconsistent publications", mutate => {
    const d = fixture(); mutate(d); expect(validateVenuePublication(d)).toBe(false);
  });
  it("shows exact prices, source quality and explicitly synthetic provenance", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(fixture())));
    render(<MarketVenuesView/>);
    await screen.findByText("Exemple synthétique · aucune connexion attestée");
    const row = screen.getByRole("button", { name: "Détail source Bybit" }).closest("tr")!;
    expect(within(row).getByText("100")).toBeInTheDocument();
    expect(within(row).getByText("100.2")).toBeInTheDocument();
    expect(screen.getByText("29.97002997 bp")).toBeInTheDocument();
    expect(screen.getAllByText("Date exchange non qualifiée")).toHaveLength(2);
    expect(screen.getByText(/Frais, funding, conversions/)).toBeInTheDocument();
  });
  it("changes reference using prepublished comparisons and preserves source order", async () => {
    const doc = fixture(); vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(doc)));
    render(<MarketVenuesView/>);await screen.findByRole("button", { name: "Détail source Bybit" });
    fireEvent.change(screen.getByLabelText("Plateforme de référence"), { target: { value: "okx" } });
    const p = doc.groups[0].comparisons.find(x => x.reference_venue === "okx" && x.other_venue === "bybit")!;
    expect(screen.getByText(p.mid_basis_bps + " bp")).toBeInTheDocument();
    expect(screen.getAllByTestId("venue-row").map(r => r.querySelector("button")!.textContent)).toEqual(["Bybit","OKX","MEXC","KuCoin"]);
  });
  it("opens one source detail, retains timestamps/hash, and restores keyboard focus", async () => {
    const doc = fixture();vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(doc)));
    render(<MarketVenuesView/>);const b = await screen.findByRole("button", { name: "Détail source MEXC" });
    fireEvent.click(b);const detail=screen.getByTestId("venue-source-detail");
    await waitFor(() => expect(detail).toHaveFocus());
    expect(within(detail).getByText(doc.groups[0].rows[2].source.payload_sha256!)).toBeInTheDocument();
    expect(within(detail).getByText("Date non disponible")).toBeInTheDocument();
    expect(within(detail).getByText("UNRESOLVED_TIMESTAMP_KIND")).toBeInTheDocument();
    fireEvent.keyDown(detail, { key: "Escape" });
    expect(screen.queryByTestId("venue-source-detail")).not.toBeInTheDocument();expect(b).toHaveFocus();
  });
  it("keeps USD, USDT, UBTC and derivatives in distinct instrument groups", async () => {
    const doc=fixture();vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(doc)));
    render(<MarketVenuesView/>);await screen.findByRole("button",{name:"Détail source Bybit"});
    const usd=doc.groups.find(g=>g.instrument.quote_asset_id==="USD")!;
    fireEvent.change(screen.getByLabelText("Instrument observé"),{target:{value:usd.instrument_id}});
    expect(screen.queryByRole("button",{name:"Détail source Bybit"})).not.toBeInTheDocument();
    expect(screen.getAllByTestId("venue-row")).toHaveLength(3);
    const perp=doc.groups.find(g=>g.instrument.market_kind==="PERPETUAL_LINEAR")!;
    fireEvent.change(screen.getByLabelText("Instrument observé"),{target:{value:perp.instrument_id}});
    expect(screen.getAllByTestId("venue-row")).toHaveLength(2);
  });
  it.each(["S_market_venues_stale","S_market_venues_unresolved"])("preserves %s rather than substituting zero",async name=>{
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(fixture(name))));
    render(<MarketVenuesView/>);await screen.findByTestId("venue-synthetic");
    expect(screen.getByRole("status")).toHaveTextContent(name.includes("stale")?"Publication périmée":"Qualité temporelle indisponible");
    if(name.includes("unresolved"))expect(screen.getAllByText("Source non reçue").length).toBeGreaterThan(0);
  });
  it("missing publication is unavailable, not an empty market",async()=>{
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response({error_code:"VENUE_COMPARISON_NOT_CONFIGURED"},503)));
    render(<MarketVenuesView/>);await screen.findByText("Aucune publication de comparaison disponible.");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();expect(screen.getByText(/ne sont pas déclarés vides/)).toBeInTheDocument();
  });
  it("comparison tab is accessible independently from missing scanner data",async()=>{
    const fetchMock=vi.fn(async(input:RequestInfo|URL)=>String(input).endsWith("/venue-comparison")?response(fixture()):response({error_code:"MARKET_SNAPSHOT_MISSING"},503));
    vi.stubGlobal("fetch",fetchMock);render(<MarketView/>);
    await screen.findByTestId("market-error");
    const tab=screen.getByRole("tab",{name:"Comparaison des plateformes"});
    fireEvent.keyDown(screen.getByRole("tab",{name:"Scanner"}),{key:"ArrowRight"});
    await screen.findByTestId("venue-synthetic");expect(tab).toHaveFocus();expect(tab).toHaveAttribute("aria-selected","true");
    expect(screen.queryByTestId("market-error")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([u])=>String(u).startsWith("/api/operator/v1/"))).toBe(true);
    fireEvent.keyDown(tab,{key:"Home"});expect(screen.getByRole("tab",{name:"Scanner"})).toHaveAttribute("aria-selected","true");
    await screen.findByTestId("market-error");
  });
});
