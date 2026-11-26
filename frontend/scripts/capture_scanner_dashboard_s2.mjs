// Preuve visuelle locale — CAT SCANNER-UI S2 / S2.1 : tableau de bord mobile de l'univers
// (Marché → Scanner, /paper-live/market/radar). Publications 100 % SYNTHÉTIQUES
// construites ici ; aucune API réelle, aucune donnée runtime. Les autres API
// répondent depuis la fixture de test Radar Spot.
// Vérifie à 360, 384 et 412 px : aucun défilement horizontal de page, quatre
// cartes de source, cibles tactiles ≥ 44 px dans le tableau de bord, et que
// l'en-tête, les sources et la couverture tiennent dans le premier écran.
// S2.1 : cartes compactes 2 × 2 (hauteur mesurée), quatre indicateurs de
// couverture sur une seule ligne, thèmes clair et sombre pour chaque état.
// Usage : npm run build && npx vite preview --port 4173 &
//         node scripts/capture_scanner_dashboard_s2.mjs
const { chromium } = (await import(process.env.PLAYWRIGHT_MODULE || "playwright")).default ?? await import(process.env.PLAYWRIGHT_MODULE || "playwright");
import { mkdir, readFile, writeFile } from "node:fs/promises";

const base = process.env.SCANNER_VISUAL_BASE_URL || "http://127.0.0.1:4173";
const out = process.env.SCANNER_VISUAL_OUT_DIR || "artifacts/scanner-dashboard-s2";
const assert = (ok, message) => { if (!ok) throw new Error(message); };
const scanner = JSON.parse(await readFile(new URL("../src/test/fixtures/spotRadar-scanner.json", import.meta.url)));
const MARKETS = ["MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_SPOT", "KRAKEN_PERPETUAL"];
const NOW = Number(scanner.server_time_ms);

function publication({ pairs = [], status = pairs.length ? "VERIFIED" : "VERIFIED_EMPTY", blocked = null, ages = {}, assets = null }) {
  const now = NOW;
  const native = (m, b, q) => ({ MEXC_SPOT: b + q, MEXC_PERPETUAL: `${b}_${q}`, KRAKEN_SPOT: (b === "BTC" ? "XBT" : b) + q, KRAKEN_PERPETUAL: `PF_${b === "BTC" ? "XBT" : b}${q}` })[m];
  const age = m => ages[m] ?? 120_000;
  const doc = {
    schema_version: assets ? "scanner-universe/1.1.0" : "scanner-universe/1.0.0", product: "ScannerCommonUniverse", authority: "OBSERVATIONAL_TELEMETRY",
    execution_authority: false, rule: "SYNTHETIC", status, computed_ms: now - 60_000, served_ms: now, freshness_max_age_ms: 2_100_000, cadence_ms: 900_000,
    blocking_sources: blocked ? [{ market: blocked, reason: "UNAVAILABLE:HTTP_503" }] : [],
    sources: MARKETS.map(m => ({ market: m, state: m === blocked ? "UNAVAILABLE" : "COMPLETE", catalogue_state: m === blocked ? "UNAVAILABLE" : "COMPLETE",
      reason: m === blocked ? "UNAVAILABLE:HTTP_503" : null, collected_ms: m === blocked ? null : now - age(m), age_ms: m === blocked ? null : age(m),
      current: m !== blocked, instruments: { MEXC_SPOT: 2210, MEXC_PERPETUAL: 812, KRAKEN_SPOT: 1094, KRAKEN_PERPETUAL: 356 }[m], admissible: m === blocked ? 0 : { MEXC_SPOT: 1980, MEXC_PERPETUAL: 790, KRAKEN_SPOT: 1012, KRAKEN_PERPETUAL: 341 }[m], excluded: {}, raw_sha256: {} })),
    pairs: status === "VERIFIED" ? pairs.map(([b, q]) => ({ key: `${b}/${q}`, base: b, quote: q, proofs: Object.fromEntries(MARKETS.map(m => [m, {
      exchange: m.startsWith("MEXC") ? "mexc" : "kraken", market_type: m.endsWith("SPOT") ? "SPOT" : "PERPETUAL", native_symbol: native(m, b, q),
      base: b, quote: q, native_base: b, native_quote: q, status: "SYNTHETIC fixture", contract_type: m.endsWith("SPOT") ? "SPOT" : "LINEAR_PERPETUAL",
      settlement_asset: m.endsWith("SPOT") ? null : q, settlement_basis: "SYNTHETIC", collected_ms: now - age(m), exclusion: null }])) })) : [],
    pair_count: status === "VERIFIED" ? pairs.length : 0,
    exclusions: assets ? [] : [{ key: "ETH/USDT", reasons: { MEXC_SPOT: null, MEXC_PERPETUAL: null, KRAKEN_SPOT: null, KRAKEN_PERPETUAL: "ABSENT" }, native_symbols: { MEXC_SPOT: ["ETHUSDT"] } }],
    exclusions_truncated: false,
    reference: blocked ? { universe_sha256: "f".repeat(64), status: "VERIFIED", computed_ms: now - 960_000, keys: [], current: false } : null,
    universe_sha256: "e".repeat(64),
  };
  if (assets) { doc.assets = status === "UNVERIFIABLE" ? [] : assets; doc.asset_count = doc.assets.length; }
  return doc;
}
// Invented listings in the style of the 2026-11-23 catalogues (Kraken USD, MEXC USDT).
const row = (s, q, perp = false) => ({ native_symbol: s, quote: q, contract_type: perp ? "LINEAR_PERPETUAL" : "SPOT", settlement_asset: perp ? q : null });
const full = b => ({ MEXC_SPOT: [row(b + "USDT", "USDT")], MEXC_PERPETUAL: [row(b + "_USDT", "USDT", true)], KRAKEN_SPOT: [row(b + "USD", "USD")], KRAKEN_PERPETUAL: [row(`PF_${b}USD`, "USD", true)] });
const asset = (base, markets, cls = "CRYPTO") => ({ base, asset_class: cls, market_count: Object.keys(markets).length, quotes: [...new Set(Object.values(markets).flat().map(r => r.quote))].sort(), markets });
const pick = (b, keys) => Object.fromEntries(Object.entries(full(b)).filter(([k]) => keys.includes(k)));
const ASSETS = [
  ...["BTC", "ETH", "SOL", "XRP", "ADA", "LINK", "DOT", "AVAX"].map(b => asset(b, full(b))),
  ...["ATOM", "LTC", "NEAR", "UNI", "AAVE"].map(b => asset(b, pick(b, ["MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_PERPETUAL"]))),
  ...["DOGE", "PEPE", "TIA", "SUI", "APT", "ARB", "OP"].map(b => asset(b, pick(b, ["MEXC_SPOT", "MEXC_PERPETUAL"]))),
  asset("USDC", pick("USDC", ["MEXC_SPOT", "MEXC_PERPETUAL"]), "STABLECOIN"),
];

const states = [
  ["1-verifie-1.0.0", () => ({ json: publication({ pairs: [["BTC", "USDT"], ["ETH", "USDT"], ["SOL", "USDT"]] }) })],
  ["2-strict-vide-multi-1.1.0", () => ({ json: publication({ assets: ASSETS }) })],
  ["3-source-indisponible", () => ({ json: publication({ assets: ASSETS, status: "UNVERIFIABLE", blocked: "KRAKEN_PERPETUAL" }) })],
  ["4-source-perimee", () => ({ json: publication({ assets: ASSETS, ages: { MEXC_PERPETUAL: 2_280_000 } }) })],
  ["6-sans-regroupement-1.0.0-vide", () => ({ json: publication({}) })],
  ["5-publication-invalide", () => ({ json: { ...publication({ pairs: [["BTC", "USDT"]] }), schema_version: "scanner-universe/9.9.9" } })],
  ["0-chargement", () => null],
];
const viewports = [{ name: "384x832", width: 384, height: 832 }, { name: "360x800", width: 360, height: 800 }, { name: "412x915", width: 412, height: 915 }];
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const results = [];
async function capture(vp, state, make, theme = "light", interact = false) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  const requests = [];
  page.on("request", r => { if (r.url().includes("/api/")) requests.push(new URL(r.url()).pathname); });
  await page.addInitScript(([t, th]) => { const o = t - Date.now(); const N = Date.now; Date.now = () => N() + o; try { localStorage.setItem("crypto-terminal.theme", th); } catch { /* */ } }, [NOW, theme]);
  await page.route("**/api/operator/v1/**", route => {
    const url = new URL(route.request().url()).pathname;
    if (url === "/api/operator/v1/scanner-universe") { const r = make(); return r ? route.fulfill(r) : undefined; }
    if (url.startsWith("/api/operator/v1/spot-radar/scanner")) return route.fulfill({ json: scanner });
    return route.fulfill({ status: 503, json: { error_code: "LOCAL_CAPTURE_NOT_CONFIGURED" } });
  });
  await page.goto(`${base}/paper-live/market/radar`);
  await page.waitForSelector(state === "0-chargement" ? ".scanner-universe[data-state=LOADING]" : ".scanner-universe[data-state]:not([data-state=LOADING])");
  await page.waitForTimeout(500);
  const m = await page.evaluate(() => {
    const root = document.querySelector(".scanner-universe");
    const small = [...root.querySelectorAll("button, summary, a")].filter(e => e.offsetParent !== null && !e.closest("dialog"))
      .map(e => ({ t: (e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 40), h: e.getBoundingClientRect().height, w: e.getBoundingClientRect().width }))
      .filter(r => r.h < 44 || r.w < 44);
    const cov = root.querySelector(".su-coverage").getBoundingClientRect();
    const fs = [...root.querySelectorAll(".su-sources li *, .su-tile dt, .su-tile dd, .su-note, .su-meta, .su-block-head")].map(e => parseFloat(getComputedStyle(e).fontSize));
    const cardBoxes = [...root.querySelectorAll(".su-sources li")].map(e => e.getBoundingClientRect());
    const tiles = [...root.querySelectorAll(".su-tiles > div")].map(e => e.getBoundingClientRect());
    return { cardHeights: cardBoxes.map(b => Math.round(b.height)), cardColumns: new Set(cardBoxes.map(b => Math.round(b.left))).size,
      tileRows: new Set(tiles.map(b => Math.round(b.top))).size, tiles: tiles.length,
      scroll: document.documentElement.scrollWidth, width: window.innerWidth, state: root.dataset.state, code: root.dataset.code ?? null,
      cards: root.querySelectorAll(".su-sources li").length, coverageBottom: Math.round(cov.bottom + window.scrollY), viewportHeight: window.innerHeight,
      pill: root.querySelector(".su-pill").textContent, smallTargets: small, minFontPx: Math.min(...fs) };
  });
  const tag = `${vp.name} ${state} ${theme}`;
  assert(m.scroll <= m.width, `${tag}: défilement horizontal ${m.scroll} > ${m.width}`);
  assert(m.cards === 4, `${tag}: ${m.cards} cartes de source`);
  assert(m.cardColumns === 2, `${tag}: grille des sources sur ${m.cardColumns} colonnes`);
  assert(m.tiles === 4 && m.tileRows === 1, `${tag}: ${m.tiles} indicateurs sur ${m.tileRows} lignes`);
  assert(Math.max(...m.cardHeights) <= 90, `${tag}: carte de source trop haute ${m.cardHeights}`);
  assert(m.coverageBottom <= m.viewportHeight, `${tag}: couverture sous le premier écran ${m.coverageBottom} > ${m.viewportHeight}`);
  assert(m.minFontPx >= 12, `${tag}: police ${m.minFontPx} px`);
  assert(!m.smallTargets.length, `${tag}: cibles tactiles < 44 px ${JSON.stringify(m.smallTargets)}`);
  const file = `${out}/s2-${state}-${theme}-${vp.name}`;
  await page.screenshot({ path: `${file}-ecran.png` });
  await page.locator(".scanner-universe").screenshot({ path: `${file}-tableau.png` });
  const extra = [];
  if (interact) {
    await page.getByText("Détail technique des sources et de la publication").tap();
    await page.waitForTimeout(200);
    await page.locator(".scanner-universe").screenshot({ path: `${file}-details-sources.png` });
    extra.push(`${file}-details-sources.png`);
    const assetTier = page.locator("summary", { hasText: "crypto-actifs sur 3 ou 2 marchés" });
    if (await assetTier.count()) {
      await assetTier.tap();
      await page.getByRole("button", { name: "DOGE" }).first().tap();
      await page.waitForSelector("dialog.universe-detail[open]");
      await page.screenshot({ path: `${file}-dialogue-actif.png` });
      extra.push(`${file}-dialogue-actif.png`);
      await page.getByRole("button", { name: "Fermer" }).tap();
    }
    const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
    assert(scroll <= vp.width, `${tag}: défilement horizontal après ouverture des détails ${scroll}`);
  }
  const universeReads = requests.filter(p => p === "/api/operator/v1/scanner-universe").length;
  assert(universeReads === 1, `${tag}: ${universeReads} lectures de l'univers`);
  results.push({ viewport: vp.name, state, theme, ...m, firstScreen: m.coverageBottom <= m.viewportHeight, requests: [...new Set(requests)], files: [`${file}-ecran.png`, `${file}-tableau.png`, ...extra] });
  await context.close();
}
for (const vp of viewports) for (const [state, make] of states) await capture(vp, state, make, "light", vp.width === 384 && state.startsWith("2-"));
for (const vp of viewports) for (const [state, make] of states) await capture(vp, state, make, "dark");
await browser.close();
await writeFile(`${out}/mobile_layout_results.json`, JSON.stringify(results, null, 1) + "\n");
console.log(`${results.length} captures OK · aucun défilement horizontal · sources 2 × 2 · 4 indicateurs sur une ligne · couverture dans le premier écran · cibles ≥ 44 px · police ≥ 12 px · 1 lecture de l'univers par page`);
for (const r of results) console.log(r.viewport, r.state, r.theme, "pill=" + r.pill, "cartes=" + r.cardHeights.join("/"), "couverture bas=" + r.coverageBottom + "/" + r.viewportHeight, "police min=" + r.minFontPx);
