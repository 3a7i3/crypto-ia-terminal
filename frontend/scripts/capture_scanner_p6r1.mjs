// Banc navigateur — CAT P6-R1 : stabilisation mobile du Scanner (F1–F4).
// Publications 100 % SYNTHÉTIQUES construites ici, calibrées sur les agrégats de
// la publication servie le 2026-11-26 (533 actifs : 123 sur 4 marchés, 227 sur 3,
// 183 sur 2 ; 4 devises fiat, 4 stablecoins ; liste de cotations la plus longue :
// 22 devises / 146 caractères ; base la plus longue : 11 caractères). Aucune
// donnée runtime n'est rejouée ; le Moniteur lit la fixture Radar Spot du dépôt.
//
// Mesures, par largeur (360, 384, 412, 832, 1440) et thème (clair, sombre) :
//  - scrollWidth == clientWidth et innerWidth stable du chargement à la fin ;
//  - aucune fenêtre de détail plus large que l'écran, bouton Fermer ≥ 44 px et
//    visible après défilement interne ;
//  - aucun « 0 admis » tant que l'univers n'est pas vérifié ;
//  - haut du Moniteur et déplacement vertical entre chargement et fin ;
//  - états LOADING, VERIFIED, VERIFIED_EMPTY, UNAVAILABLE, passage à une
//    publication périmée, ordres d'arrivée inversés, rafraîchissements répétés,
//    recherche et filtre conservés dans l'URL.
// Usage : npm run build && npx vite preview --port 4173 &
//         node scripts/capture_scanner_p6r1.mjs   (BASE, OUT, LABEL, SHOTS=1)
const pw = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const { chromium } = pw.default ?? pw;
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const base = process.env.BASE || "http://127.0.0.1:4173";
const out = process.env.OUT || "artifacts/scanner-p6r1";
const label = process.env.LABEL || "p6r1";
const shots = process.env.SHOTS !== "0";
await mkdir(out, { recursive: true });
const spot = JSON.parse(await readFile(new URL("../src/test/fixtures/spotRadar-scanner.json", import.meta.url)));
const NOW = Number(spot.server_time_ms);
const MARKETS = ["MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_SPOT", "KRAKEN_PERPETUAL"];
const LONGQ = "AUD AUSD BRL CAD CHF DAI EUR EURC EURCV EUROP FIDD GBP JPY PYUSD SOFID USD USD1 USDC USDE USDF USDQ USDT".split(" ");
const LONG_BASE = "BROCCOLIF3B";

// Moniteur: one row renamed to the longest published base so that a long symbol is admitted.
const scanner = structuredClone(spot);
{
  const last = scanner.rows.length - 1, old = scanner.rows[last];
  const oldNative = old.identity.native_symbol, oldBase = old.base_asset;
  const r0 = JSON.parse(JSON.stringify(old).replaceAll(`"${oldNative}"`, `"${LONG_BASE}USDT"`).replaceAll(`"${oldBase}/USDT"`, `"${LONG_BASE}/USDT"`).replaceAll(`"${oldBase}"`, `"${LONG_BASE}"`));
  // Same identity rule as the client: sha256 of the canonical identity JSON.
  r0.instrument_id = createHash("sha256").update(JSON.stringify({ exchange: r0.identity.exchange, market: r0.identity.market, native_symbol: r0.identity.native_symbol })).digest("hex");
  scanner.rows[last] = r0;
}

const row = (s, q, perp) => ({ native_symbol: s, quote: q, contract_type: perp ? "LINEAR_PERPETUAL" : "SPOT", settlement_asset: perp ? q : null });
function mk(b, n, cls = "CRYPTO", quotes = null) {
  const markets = {};
  for (const m of MARKETS.slice(0, n)) {
    const perp = m.endsWith("PERPETUAL");
    const qs = quotes && m === "KRAKEN_SPOT" ? quotes : [m.startsWith("MEXC") ? "USDT" : "USD"];
    markets[m] = qs.map(q => row((perp ? (m.startsWith("MEXC") ? b + "_" : "PF_" + b) : b) + q, q, perp));
  }
  return { base: b, asset_class: cls, market_count: n, quotes: [...new Set(Object.values(markets).flat().map(x => x.quote))].sort(), markets };
}
function assets() {
  const a = [mk("ADA", 4, "CRYPTO", LONGQ)];
  let i = 0; const name = () => "SYN" + String(i++).padStart(4, "0");
  for (let k = 0; k < 122; k++) a.push(mk(name(), 4));
  for (let k = 0; k < 227; k++) a.push(mk(name(), 3));
  for (let k = 0; k < 175; k++) a.push(mk(name(), 2));
  a.push(mk(LONG_BASE, 2));
  for (const s of ["USDC", "USDT", "DAI", "PYUSD"]) a.push(mk(s, 2, "STABLECOIN"));
  for (const s of ["EUR", "GBP", "AUD", "CAD"]) a.push(mk(s, 2, "FIAT"));
  for (const r of scanner.rows) { const b = r.identity.native_symbol.replace(/USDT$/, ""); if (!a.find(x => x.base === b)) a.push(mk(b, 2)); }
  return a;
}
const ASSETS = assets();
function publication({ status = "VERIFIED_EMPTY", age = 120_000, at = NOW }) {
  const pairs = status === "VERIFIED" ? [["BTC", "USDT"]].map(([b, q]) => ({ key: `${b}/${q}`, base: b, quote: q, proofs: Object.fromEntries(MARKETS.map(m => [m, {
    exchange: m.startsWith("MEXC") ? "mexc" : "kraken", market_type: m.endsWith("SPOT") ? "SPOT" : "PERPETUAL", native_symbol: b + q, base: b, quote: q, native_base: b, native_quote: q,
    status: "SYNTHETIC fixture", contract_type: m.endsWith("SPOT") ? "SPOT" : "LINEAR_PERPETUAL", settlement_asset: m.endsWith("SPOT") ? null : q, settlement_basis: "SYNTHETIC", collected_ms: at - age, exclusion: null }])) })) : [];
  return {
    schema_version: "scanner-universe/1.1.0", product: "ScannerCommonUniverse", authority: "OBSERVATIONAL_TELEMETRY", execution_authority: false, rule: "SYNTHETIC",
    status, computed_ms: at - 60_000, served_ms: at, freshness_max_age_ms: 2_100_000, cadence_ms: 900_000, blocking_sources: [],
    sources: MARKETS.map(m => ({ market: m, state: "COMPLETE", catalogue_state: "COMPLETE", reason: null, collected_ms: at - age, age_ms: age, current: true, instruments: 1000, admissible: 900, excluded: {}, raw_sha256: {} })),
    pairs, pair_count: pairs.length, exclusions: [], exclusions_truncated: false, reference: null, universe_sha256: "e".repeat(64), assets: ASSETS, asset_count: ASSETS.length,
  };
}

// Scenarios: universe responses in order (one per read) and arrival delays.
const ok = () => ({ json: publication({}) });
const SCENARIOS = [
  { id: "verifie-vide", uni: [ok], uniDelay: 1500, spotDelay: 700, main: true },
  { id: "ordre-inverse", uni: [ok], uniDelay: 300, spotDelay: 1500 },
  { id: "verifie-paires", uni: [() => ({ json: publication({ status: "VERIFIED" }) })], uniDelay: 900, spotDelay: 600 },
  { id: "chargement", uni: [() => null], uniDelay: 0, spotDelay: 400, never: true },
  { id: "indisponible", uni: [() => ({ status: 503, json: { error_code: "SCANNER_UNIVERSE_NOT_CONFIGURED" } })], uniDelay: 600, spotDelay: 400 },
  { id: "vers-perimee", uni: [ok, () => ({ json: publication({ age: 3_000_000, at: NOW + 61_000 }) })], uniDelay: 400, spotDelay: 400, refresh: 1 },
  { id: "rafraichissements", uni: [ok, ok, ok, ok], uniDelay: 400, spotDelay: 400, refresh: 3, moniteurReads: 5 },
  { id: "url-recherche", uni: [ok], uniDelay: 600, spotDelay: 400, search: "?q=AD&cov=4" },
];
const WIDTHS = [[360, 800], [384, 832], [412, 915], [832, 1100], [1440, 900]];
const THEMES = (process.env.THEMES || "light,dark").split(",");
const ONLY = process.env.SCENARIOS ? process.env.SCENARIOS.split(",") : null;

const browser = await chromium.launch();
const results = [];
for (const sc of SCENARIOS.filter(s => !ONLY || ONLY.includes(s.id))) for (const theme of THEMES) for (const [w, h] of WIDTHS) {
  const mobile = w < 800;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme });
  const page = await ctx.newPage();
  await page.clock.install({ time: NOW });
  await page.addInitScript(th => { try { localStorage.setItem("crypto-terminal.theme", th); } catch { /* */ } }, theme);
  let uniReads = 0, spotReads = 0;
  await page.route("**/api/operator/v1/**", async route => {
    const p = new URL(route.request().url()).pathname;
    if (p === "/api/operator/v1/scanner-universe") {
      const make = sc.uni[Math.min(uniReads++, sc.uni.length - 1)];
      const r = make();
      if (r === null) return; // never answered: LOADING
      await new Promise(x => setTimeout(x, sc.uniDelay));
      return route.fulfill(r.status ? { status: r.status, json: r.json } : { json: r.json });
    }
    if (p.startsWith("/api/operator/v1/spot-radar/scanner")) { spotReads++; await new Promise(x => setTimeout(x, sc.spotDelay)); return route.fulfill({ json: scanner }); }
    return route.fulfill({ status: 503, json: { error_code: "LOCAL_CAPTURE_NOT_CONFIGURED" } });
  });
  const probe = () => page.evaluate(() => {
    const de = document.documentElement;
    const mon = document.querySelector('section[aria-label="Moniteur de marché"]');
    const summary = document.querySelector(".symbol-summary")?.textContent ?? null;
    const coverage = document.querySelector(".intraday-coverage")?.textContent ?? null;
    const state = document.querySelector(".scanner-universe")?.getAttribute("data-state") ?? null;
    const fold = document.querySelector("[data-testid=asset-list-fold]");
    return { sw: de.scrollWidth, cw: de.clientWidth, iw: innerWidth, vv: visualViewport ? +visualViewport.scale.toFixed(3) : null,
      monitorTop: mon ? Math.round(mon.getBoundingClientRect().top + scrollY) : null, state, summary, coverage,
      foldOpen: fold ? fold.open : null, foldSummary: fold?.querySelector("summary")?.textContent ?? null };
  });
  const samples = [];
  const falseZero = s => s.state !== "VERIFIED" && s.state !== "VERIFIED_EMPTY" && /\b0 admis|\b0 instrument admis/.test((s.summary ?? "") + (s.coverage ?? ""));
  await page.goto(base + "/paper-live/market/radar" + (sc.search || ""), { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".scanner-universe");
  await page.clock.runFor(150);
  const first = await probe(); samples.push({ t: "start", ...first });
  const firstMonitor = await page.waitForSelector('section[aria-label="Moniteur de marché"]').then(probe);
  // Let both reads arrive (real time: route delays are host timers).
  let elapsed = 0;
  for (const t of [250, 500, 800, 1200, 1700, 2300]) { await page.waitForTimeout(t - elapsed); elapsed = t; await page.clock.runFor(1); samples.push({ t, ...await probe() }); }
  // Repeated refreshes: universe poll is 60 s, Moniteur Live cadence is 5 s.
  for (let k = 0; k < (sc.refresh || 0); k++) { await page.clock.runFor(61_000); await page.waitForTimeout(sc.uniDelay + 400); await page.clock.runFor(1); samples.push({ t: `refresh-${k + 1}`, ...await probe() }); }
  for (let k = 0; k < (sc.moniteurReads || 0); k++) { await page.clock.runFor(5_000); await page.waitForTimeout(sc.spotDelay + 200); }
  const end = await probe(); samples.push({ t: "end", ...end });
  const tag = `${label}-${sc.id}-${theme}-${w}`;
  const files = [];
  if (shots && (sc.main || w === 384)) { await page.screenshot({ path: `${out}/${tag}-ecran.png` }); files.push(`${tag}-ecran.png`); }

  // Dialogs: asset with 22 quotes (catalogue opened first if folded), then the Moniteur sheet.
  const dialogs = [];
  const measureDialog = async kind => page.evaluate(kind => {
    const d = document.querySelector("dialog[open]"); if (!d) return { kind, open: false };
    const r = d.getBoundingClientRect(); const btn = d.querySelector("form button"); d.scrollTop = d.scrollHeight;
    const b = btn?.getBoundingClientRect();
    return { kind, open: true, w: Math.round(r.width), h: Math.round(r.height), left: Math.round(r.left), right: Math.round(r.right), vw: document.documentElement.clientWidth, vh: innerHeight,
      internalScroll: d.scrollHeight > d.clientHeight, closeVisibleAfterScroll: !!b && b.top >= r.top - 1 && b.bottom <= r.bottom + 1, closeW: b ? Math.round(b.width) : null, closeH: b ? Math.round(b.height) : null,
      pageSw: document.documentElement.scrollWidth };
  }, kind);
  try {
  const assetRow = page.locator(".su-asset-row").first();
  if (sc.main || sc.id === "url-recherche") {
    const fold = page.locator("[data-testid=asset-list-fold] > summary");
    if (await fold.count() && !(await page.locator("[data-testid=asset-list-fold]").evaluate(e => e.open))) await fold.click();
    await page.waitForTimeout(100);
    if (await assetRow.count()) {
      await assetRow.click({ timeout: 4000 }); await page.waitForTimeout(150);
      const m = await measureDialog("actif-22-devises"); dialogs.push(m);
      if (shots && sc.main) { await page.screenshot({ path: `${out}/${tag}-fiche-actif.png` }); files.push(`${tag}-fiche-actif.png`); }
      await page.locator("dialog[open] form button").click({ timeout: 4000 }); await page.waitForTimeout(100);
      dialogs.push({ kind: "actif-fermee", open: await page.locator("dialog[open]").count() > 0 });
      if (sc.main && w === 384) { samples.push({ t: "catalogue-ouvert", ...await probe() }); }
    }
  }
  const monBtn = page.locator(".symbol-table tbody button").last();
  if (await monBtn.count()) {
    await monBtn.scrollIntoViewIfNeeded(); await monBtn.click({ timeout: 4000 }); await page.waitForTimeout(150);
    dialogs.push(await measureDialog("moniteur"));
    if (shots && (sc.main) && (w === 384 || w === 360)) { await page.screenshot({ path: `${out}/${tag}-fiche-moniteur.png` }); files.push(`${tag}-fiche-moniteur.png`); }
    await page.keyboard.press("Escape"); await page.waitForTimeout(100);
    dialogs.push({ kind: "moniteur-fermee", open: await page.locator("dialog[open]").count() > 0 });
  }
  } catch (e) { dialogs.push({ kind: "erreur-interaction", open: false, error: e.message.split("\n")[0] }); }
  const loaded = samples.filter(s => s.monitorTop !== null && typeof s.t === "number");
  const shift = firstMonitor.monitorTop !== null && end.monitorTop !== null ? end.monitorTop - firstMonitor.monitorTop : null;
  const res = {
    scenario: sc.id, theme, width: w, height: h, url: new URL(page.url()).search, uniReads, spotReads,
    overflowAny: samples.some(s => s.sw !== s.cw), innerWidthStable: samples.every(s => s.iw === w), falseZero: samples.some(falseZero),
    monitorTopStart: firstMonitor.monitorTop, monitorTopEnd: end.monitorTop, verticalShift: shift,
    maxMonitorTopWhileLoading: Math.max(...loaded.map(s => s.monitorTop)), endState: end.state, foldOpenEnd: end.foldOpen,
    dialogs, dialogTooWide: dialogs.some(d => d.open && (d.w > d.vw || d.left < 0 || d.right > d.vw)), samples, files,
  };
  results.push(res);
  console.log([sc.id, theme, w, `state=${end.state}`, `sw=${end.sw}/${end.cw}`, `iwStable=${res.innerWidthStable}`, `overflow=${res.overflowAny}`, `falseZero=${res.falseZero}`, `mon=${res.monitorTopStart}->${res.monitorTopEnd}`, `shift=${shift}`, `fold=${end.foldOpen}`,
    `dlg=${dialogs.filter(d => d.open).map(d => `${d.kind}:${d.w}x${d.h}/vw${d.vw} close${d.closeW}x${d.closeH} vis=${d.closeVisibleAfterScroll}`).join(" ")}`, `url=${res.url}`].join(" | "));
  await ctx.close();
}
await browser.close();
await writeFile(`${out}/${label}-results.json`, JSON.stringify(results, null, 2));
