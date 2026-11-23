import { SpotRadarMap } from "./SpotRadarMap";
import { SymbolScanner } from "./SymbolScanner";
import { LiveTerminal } from "./LiveTerminal";
import { SignalsRadar, type SignalsDoc } from "./SignalsRadar";
// Démo uniquement : sortie de référence SYNTHÉTIQUE du contrat cat.signals.indicators.v1
// (tests/signals_indicators/fixtures/btc_reference_expected.json @30965e8e, copiée telle quelle).
// Aucune requête vers un service de signaux ; aucune ligne n'entre dans le Scanner strict.
import signalsDemo from "../demo/signalsIndicators-v1-btc-reference.json";
import { ScannerUniverse, useScannerUniverse } from "./ScannerUniverse";
import { admittedMexcSpot, admittedKeys, mexcSpotMarkets } from "../lib/scannerUniverseClient";
import React, { useEffect, useRef, useState } from "react";
import { Link, MemoryRouter, Navigate, Route, Routes, useInRouterContext, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { MarketMicrostructureView } from "./MarketMicrostructureView";
import { MARKET_BASE, MARKET_RADAR_PATH } from "../lib/moduleNavigation";
import "../market-catalogue.css";
import "../market-venues.css";
import "../market-navigation.css";

// Only the scanner and microstructure are mounted. Retired view bookmarks
// redirect to the scanner; their source modules and contracts remain in Git.
export const MARKET_VIEWS = [
  { slug: "radar", label: "Scanner" },
  { slug: "lmi", label: "Microstructure" },
] as const;

export type MarketProduct = "spot" | "live" | "spot-radar" | "signals-demo";
// Scanner refonte (2026-11-23): Bulles Intraday is retired. An old bookmark
// (`intraday=1`, `product=intraday`) opens the Classement du jour and its obsolete
// parameter is dropped with replace, like `radar=0` since M1-C3 (EO-024).
export function marketProduct(params: URLSearchParams): MarketProduct {
  if (params.get("product") === "spot-radar") return "spot-radar";
  if (params.get("product") === "live") return "live";
  if (params.get("product") === "signals-demo") return "signals-demo";
  return "spot";
}
const OBSOLETE = (params: URLSearchParams) => params.has("radar") || params.has("intraday") || params.get("product") === "intraday";

const RadarPanel: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const product = marketProduct(params);
  const [selection, setSelection] = useState<string[]>([]);
  // Scanner V1: every sub-view below shows only rows admitted by the current
  // common universe (four market proofs). No universe => no current row.
  const universe = useScannerUniverse();
  const byAsset = universe.state !== "LOADING" && universe.doc?.schema_version === "scanner-universe/1.1.0";
  const gate = { admitted: admittedMexcSpot(universe), keys: admittedKeys(universe), state: universe.state, markets: mexcSpotMarkets(universe), byAsset };
  const toggleSelection = (id: string) => setSelection(previous =>
    previous.includes(id) ? previous.filter(item => item !== id) : [...previous, id]);
  const legacy = OBSOLETE(params);
  useEffect(() => {
    if (!legacy) return;
    const query = new URLSearchParams(params);
    query.delete("radar"); query.delete("intraday");
    if (query.get("product") === "intraday") query.delete("product");
    setParams(query, { replace: true });
  }, [legacy, params, setParams]);
  // Product choice is a sub-view of Radar: written to the URL with replace so it
  // survives a reload without adding history entries (same as the former local state).
  const select = (next: MarketProduct) => {
    const query = new URLSearchParams(params);
    query.delete("radar"); query.delete("intraday"); query.delete("product");
    if (next !== "spot") query.set("product", next);
    setParams(query, { replace: true });
  };
  return <>
    <ScannerUniverse view={universe} />
    <div className="market-display-choice" role="group" aria-label="Produit du scanner">
      <button type="button" aria-pressed={product === "spot"} onClick={() => select("spot")}>Classement du jour</button>
      <button type="button" aria-pressed={product === "live"} onClick={() => select("live")}>Terminal live</button>
      <button type="button" aria-pressed={product === "spot-radar"} onClick={() => select("spot-radar")}>Radar Spot</button>
      <button type="button" aria-pressed={product === "signals-demo"} onClick={() => select("signals-demo")}>Radar de signaux · Démo</button>
    </div>
    {legacy ? null : product === "signals-demo" ? <SignalsRadar doc={signalsDemo as unknown as SignalsDoc} demo />
      : product === "spot-radar" ? <SpotRadarMap gate={gate} />
      : product === "live" ? <LiveTerminal gate={gate} />
      : <SymbolScanner selection={selection} onSelect={toggleSelection} gate={gate} />}
  </>;
};

const UnknownMarketView: React.FC = () => {
  const { pathname } = useLocation();
  return <section className="market-panel" data-testid="market-unknown-view">
    <p><strong>Vue Marché inconnue</strong> : <code>{pathname}</code>.</p>
    <p>Aucune donnée n’est chargée pour cette adresse. Choisir une des vues du marché ci-dessus.</p>
  </section>;
};

const MarketWorkspace: React.FC = () => {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const slug = pathname.startsWith(MARKET_BASE + "/") ? pathname.slice(MARKET_BASE.length + 1).replace(/\/$/, "") : "";
  const active = MARKET_VIEWS.findIndex((v) => v.slug === slug);
  // Remember the Radar sub-view query while another view is open, as the former
  // always-mounted MarketView kept its product state across tabs.
  const radarSearch = useRef("");
  useEffect(() => { if (slug === "radar") radarSearch.current = search; }, [slug, search]);
  const hrefOf = (i: number) => MARKET_BASE + "/" + MARKET_VIEWS[i].slug +
    (MARKET_VIEWS[i].slug === "radar" ? (slug === "radar" ? search : radarSearch.current) : "");
  const tabs = useRef<(HTMLAnchorElement | null)[]>([]);
  // The app frame moves focus to the content on every path change; a tab chosen
  // from the tab list gets its focus back once that has happened.
  const pendingFocus = useRef<number | null>(null);
  useEffect(() => {
    const i = pendingFocus.current;
    pendingFocus.current = null;
    if (i === null) return;
    const timer = window.setTimeout(() => tabs.current[i]?.focus());
    return () => window.clearTimeout(timer);
  }, [pathname]);
  const go = (i: number) => {
    tabs.current[i]?.focus();
    if (i === active) return;
    pendingFocus.current = i;
    navigate(hrefOf(i));
  };
  const focusable = active < 0 ? 0 : active;
  return <div className="market-workspace" data-testid="market-workspace">
    {/* Real links: the existing link sub-navigation style (.module-subnav, as for the
        Positions views) is reused, so no stylesheet changes in M1-C1. */}
    <div className="market-workspace-tabs module-subnav" role="tablist" aria-label="Vues du marché">
      {MARKET_VIEWS.map((view, i) => <Link key={view.slug} to={hrefOf(i)} role="tab" id={"market-tab-" + view.slug}
        data-testid={"market-tab-" + view.slug} className={active === i ? "active" : undefined}
        aria-selected={active === i} aria-current={active === i ? "page" : undefined}
        aria-controls={active === i ? "market-panel" : undefined} tabIndex={focusable === i ? 0 : -1}
        ref={(el) => { tabs.current[i] = el; }}
        onClick={(e) => { if (e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey && i !== active) pendingFocus.current = i; }}
        onKeyDown={(e) => {
          const next = {
            Home: 0, End: MARKET_VIEWS.length - 1,
            ArrowRight: (i + 1) % MARKET_VIEWS.length,
            ArrowLeft: (i + MARKET_VIEWS.length - 1) % MARKET_VIEWS.length,
            " ": i,
          }[e.key];
          if (typeof next === "number") { e.preventDefault(); go(next); }
        }}>{view.label}</Link>)}
    </div>
    <div id="market-panel" data-testid="market-panel" data-market-view={active < 0 ? "unknown" : slug}
      role={active < 0 ? undefined : "tabpanel"} aria-labelledby={active < 0 ? undefined : "market-tab-" + slug}>
      <Routes>
        <Route index element={<Navigate to={{ pathname: MARKET_RADAR_PATH, search }} replace />} />
        <Route path="radar" element={<RadarPanel />} />
        <Route path="venues" element={<Navigate to={MARKET_RADAR_PATH} replace />} />
        <Route path="flow" element={<Navigate to={MARKET_RADAR_PATH} replace />} />
        <Route path="lmi" element={<MarketMicrostructureView />} />
        <Route path="*" element={<UnknownMarketView />} />
      </Routes>
    </div>
  </div>;
};

// Inside the application the workspace uses the app router. Rendered alone
// (component tests), it gets its own in-memory router seeded from the current
// address, so the same navigation code runs in both cases.
export const MarketView: React.FC = () => {
  const routed = useInRouterContext();
  if (routed) return <MarketWorkspace />;
  const { pathname, search } = window.location;
  const start = (pathname === MARKET_BASE || pathname.startsWith(MARKET_BASE + "/") ? pathname : MARKET_RADAR_PATH) + search;
  return <MemoryRouter initialEntries={[start]}>
    <Routes><Route path={MARKET_BASE + "/*"} element={<MarketWorkspace />} /></Routes>
  </MemoryRouter>;
};
