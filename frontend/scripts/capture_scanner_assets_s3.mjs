// Preuve visuelle locale — CAT SCANNER-UI S3 : liste des actifs publiés, recherche,
// filtres 4/4 · 3/4 · 2/4 et détail par instrument (Marché → Scanner).
// Publications 100 % SYNTHÉTIQUES construites ici ; aucune API réelle, aucune
// donnée runtime. Les autres API répondent depuis la fixture de test Radar Spot.
// Vérifie à 360, 384 et 412 px, clair et sombre (critère A10) : aucun défilement
// horizontal, cibles tactiles ≥ 44 px et police ≥ 12 px dans la liste, premier
// écran S2.1 inchangé (couverture visible), une seule lecture de l'univers par
// page même en cherchant, filtrant, paginant et ouvrant un détail, et paramètres
// d'URL conservés (product) ou bornés (q, cov).
// Usage : npm run build && npx vite preview --port 4173 &
//         node scripts/capture_scanner_assets_s3.mjs
const { chromium } = (await import(process.env.PLAYWRIGHT_MODULE || "playwright")).default ?? await import(process.env.PLAYWRIGHT_MODULE || "playwright");
import { mkdir, readFile, writeFile } from "node:fs/promises";

const base = process.env.SCANNER_VISUAL_BASE_URL || "http://127.0.0.1:4173";
const out = process.env.SCANNER_VISUAL_OUT_DIR || "artifacts/scanner-assets-s3";
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


// S3: BTC carries Kraken's own native symbols (XBT…) and an invented inverse perpetual,
// plus 60 invented crypto-assets so that the list pages (50, then « Afficher … de plus »).
const btc = asset("BTC", { MEXC_SPOT: [row("BTCUSDT", "USDT")], MEXC_PERPETUAL: [row("BTC_USDT", "USDT", true)],
  KRAKEN_SPOT: [row("XBTUSD", "USD"), row("XBTUSDT", "USDT")],
  KRAKEN_PERPETUAL: [row("PF_XBTUSD", "USD", true), { native_symbol: "PI_XBTUSD", quote: "USD", contract_type: "INVERSE_PERPETUAL", settlement_asset: "BTC" }] });
const SYN = Array.from({ length: 60 }, (_, i) => asset(`SYN${String(i + 1).padStart(2, "0")}`, pick(`SYN${String(i + 1).padStart(2, "0")}`, ["MEXC_SPOT", "MEXC_PERPETUAL"])));
const S3_ASSETS = [btc, ...ASSETS.filter(a => a.base !== "BTC" && a.asset_class === "CRYPTO"), ...SYN, ...ASSETS.filter(a => a.asset_class !== "CRYPTO"),
  asset("EUR", pick("EUR", ["KRAKEN_SPOT", "KRAKEN_PERPETUAL"]), "FIAT")];
const ok = () => ({ json: publication({ assets: S3_ASSETS }) });
const states = [
  ["1-liste-tous", "", ok, ""],
  ["2-recherche-xbt", "?q=xbt", ok, "?q=XBT"],
  ["3-filtre-3-sur-4", "?cov=3&product=spot-radar", ok, "?cov=3&product=spot-radar"],
  ["4-aucun-resultat", "?q=zzz&cov=4", ok, "?q=ZZZ&cov=4"],
  ["5-url-bornee", `?product=signals-demo&q=${"b".repeat(60)}%3C%3E&cov=9`, ok, `?product=signals-demo&q=${"B".repeat(32)}`],
  ["6-source-perimee", "?q=eth", () => ({ json: publication({ assets: S3_ASSETS, ages: { MEXC_PERPETUAL: 2_280_000 } }) }), "?q=ETH"],
  ["7-publication-1.0.0", "", () => ({ json: publication({ pairs: [["BTC", "USDT"], ["ETH", "USDT"]] }) }), ""],
  ["8-chargement", "", () => null, ""],
];
const viewports = [{ name: "384x832", width: 384, height: 832 }, { name: "360x800", width: 360, height: 800 }, { name: "412x915", width: 412, height: 915 }];
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const results = [];
async function capture(vp, [state, search, make, expectSearch], theme, interact) {
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
  await page.goto(`${base}/paper-live/market/radar${search}`);
  await page.waitForSelector(state === "8-chargement" ? ".scanner-universe[data-state=LOADING]" : ".scanner-universe[data-state]:not([data-state=LOADING])");
  await page.waitForTimeout(500);
  const tag = `${vp.name} ${state} ${theme}`;
  if (expectSearch !== null && state !== "1-liste-tous") assert(new URL(page.url()).search === expectSearch, `${tag}: URL ${new URL(page.url()).search} ≠ ${expectSearch}`);
  const measure = () => page.evaluate(() => {
    const root = document.querySelector(".scanner-universe"), list = root.querySelector(".su-assets");
    const small = [...list.querySelectorAll("button, input")].filter(e => e.offsetParent !== null)
      .map(e => ({ t: (e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 40), h: e.getBoundingClientRect().height, w: e.getBoundingClientRect().width }))
      .filter(r => r.h < 44 || r.w < 44);
    const fs = [...list.querySelectorAll("*")].filter(e => e.offsetParent !== null && e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())).map(e => parseFloat(getComputedStyle(e).fontSize));
    const rowsH = [...list.querySelectorAll(".su-asset-row")].map(e => Math.round(e.getBoundingClientRect().height));
    const filters = [...list.querySelectorAll(".su-chip-filter")].map(e => e.getBoundingClientRect());
    const cov = root.querySelector(".su-coverage").getBoundingClientRect();
    return { scroll: document.documentElement.scrollWidth, width: window.innerWidth, state: root.dataset.state, listState: list.dataset.listState,
      rows: rowsH.length, rowMax: rowsH.length ? Math.max(...rowsH) : null, filterRows: new Set(filters.map(b => Math.round(b.top))).size,
      coverageBottom: Math.round(cov.bottom + window.scrollY), viewportHeight: window.innerHeight, smallTargets: small, minFontPx: Math.min(...fs),
      results: list.querySelector(".su-results")?.textContent ?? null, message: list.querySelector(".su-list-msg")?.textContent ?? null,
      chips: [...list.querySelectorAll(".su-chip-filter")].map(e => e.textContent) };
  });
  const m = await measure();
  assert(m.scroll <= m.width, `${tag}: défilement horizontal ${m.scroll} > ${m.width}`);
  assert(m.coverageBottom <= m.viewportHeight, `${tag}: premier écran S2.1 modifié, couverture à ${m.coverageBottom} > ${m.viewportHeight}`);
  assert(m.filterRows === 1, `${tag}: puces sur ${m.filterRows} lignes`);
  assert(m.minFontPx >= 12, `${tag}: police ${m.minFontPx} px`);
  assert(!m.smallTargets.length, `${tag}: cibles tactiles < 44 px ${JSON.stringify(m.smallTargets)}`);
  assert(m.rows <= 50, `${tag}: ${m.rows} lignes affichées (> 50)`);
  if (m.listState !== "READY") assert(m.rows === 0 && !m.chips.some(c => /\b0\b/.test(c)), `${tag}: lignes ou zéro hors état vérifié ${m.rows} ${m.chips}`);
  const file = `${out}/s3-${state}-${theme}-${vp.name}`;
  const files = [`${file}-ecran.png`, `${file}-liste.png`];
  await page.screenshot({ path: files[0] });
  await page.locator(".su-assets").scrollIntoViewIfNeeded();
  await page.screenshot({ path: files[1] });
  if (interact) {
    const more = page.locator(".su-more");
    if (await more.count()) { await more.tap(); await page.waitForTimeout(150); }
    const after = await measure();
    assert(after.scroll <= vp.width, `${tag}: défilement horizontal après pagination`);
    const btcRow = page.getByRole("button", { name: /^BTC, 4 marchés sur 4/ });
    if (await btcRow.count()) {
      await btcRow.tap();
      await page.waitForSelector("dialog.universe-detail[open]");
      await page.screenshot({ path: `${file}-detail-btc.png` });
      files.push(`${file}-detail-btc.png`);
      const items = await page.locator("dialog.universe-detail[open] .su-instrument-rows li").count();
      assert(items === 6, `${tag}: ${items} instruments BTC affichés au lieu de 6`);
      await page.getByRole("button", { name: "Fermer" }).tap();
      assert(await btcRow.evaluate(e => e === document.activeElement), `${tag}: focus non rendu à la ligne BTC`);
    }
    await page.locator(".su-search").fill("pf_");
    await page.waitForTimeout(150);
    assert(new URL(page.url()).search.includes("q=PF_"), `${tag}: recherche non écrite dans l'URL`);
    await page.locator(".su-assets").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${file}-recherche-pf.png` });
    files.push(`${file}-recherche-pf.png`);
  }
  const universeReads = requests.filter(p => p === "/api/operator/v1/scanner-universe").length;
  assert(universeReads === 1, `${tag}: ${universeReads} lectures de l'univers`);
  results.push({ viewport: vp.name, state, theme, url: new URL(page.url()).search, ...m, files });
  await context.close();
}
for (const theme of ["light", "dark"]) for (const vp of viewports) for (const s of states) await capture(vp, s, theme, theme === "light" && s[0] === "1-liste-tous");
await browser.close();
await writeFile(`${out}/mobile_layout_results.json`, JSON.stringify(results, null, 1) + "\n");
console.log(`${results.length} états capturés OK · aucun défilement horizontal · premier écran S2.1 inchangé · puces sur une ligne · cibles ≥ 44 px · police ≥ 12 px · ≤ 50 lignes · 1 lecture de l'univers par page`);
for (const r of results) console.log(r.viewport, r.state, r.theme, r.listState, "url=" + r.url, "lignes=" + r.rows, "hauteur max=" + r.rowMax, "police min=" + r.minFontPx, "|", r.results ?? r.message);
