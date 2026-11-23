// Preuve visuelle locale — Scanner V1, univers commun MEXC × Kraken (Marché → Scanner).
// Trois états à 384 px (S24+) et 360/412 px : liste vérifiée (publication SYNTHÉTIQUE),
// univers vide vérifié (publication RÉELLE fournie par SCANNER_UNIVERSE_REAL, jamais
// versionnée) et univers indisponible (publication SYNTHÉTIQUE). Les autres API
// répondent depuis les fixtures de test Radar Spot. Vérifie l'absence de défilement
// horizontal de PAGE et qu'aucune ligne non admise n'apparaît dans les sous-vues.
// Usage : npm run build && npx vite preview --port 4173 &
//         [PLAYWRIGHT_MODULE=/chemin/playwright/index.js] SCANNER_UNIVERSE_REAL=/chemin/scanner-universe.json node scripts/capture_scanner_universe_mobile.mjs
const { chromium } = (await import(process.env.PLAYWRIGHT_MODULE || "playwright")).default ?? await import(process.env.PLAYWRIGHT_MODULE || "playwright");
import { mkdir, readFile, writeFile } from "node:fs/promises";

const base = process.env.SCANNER_VISUAL_BASE_URL || "http://127.0.0.1:4173";
const out = process.env.SCANNER_VISUAL_OUT_DIR || "artifacts/scanner-universe-mobile";
const realPath = process.env.SCANNER_UNIVERSE_REAL;
const assert = (ok, message) => { if (!ok) throw new Error(message); };
const scanner = JSON.parse(await readFile(new URL("../src/test/fixtures/spotRadar-scanner.json", import.meta.url)));
const MARKETS = ["MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_SPOT", "KRAKEN_PERPETUAL"];

function synthetic(keys, status, now) {
  const at = now - 120_000, blocked = status === "UNVERIFIABLE" ? "KRAKEN_PERPETUAL" : null;
  const native = (m, b, q) => ({ MEXC_SPOT: b + q, MEXC_PERPETUAL: `${b}_${q}`, KRAKEN_SPOT: (b === "BTC" ? "XBT" : b) + q, KRAKEN_PERPETUAL: `PF_${b}${q}` })[m];
  return {
    schema_version: "scanner-universe/1.0.0", product: "ScannerCommonUniverse", authority: "OBSERVATIONAL_TELEMETRY", execution_authority: false,
    rule: "SYNTHETIC", status, computed_ms: now, served_ms: now, freshness_max_age_ms: 2_100_000, cadence_ms: 900_000,
    blocking_sources: blocked ? [{ market: blocked, reason: "UNAVAILABLE:HTTP_503" }] : [],
    sources: MARKETS.map(m => ({ market: m, state: m === blocked ? "UNAVAILABLE" : "COMPLETE", catalogue_state: m === blocked ? "UNAVAILABLE" : "COMPLETE",
      reason: m === blocked ? "UNAVAILABLE:HTTP_503" : null, collected_ms: m === blocked ? null : at, age_ms: m === blocked ? null : 120_000,
      current: m !== blocked, instruments: 100, admissible: m === blocked ? 0 : 90, excluded: {}, raw_sha256: {} })),
    pairs: status === "VERIFIED" ? keys.map(([b, q]) => ({ key: `${b}/${q}`, base: b, quote: q, proofs: Object.fromEntries(MARKETS.map(m => [m, {
      exchange: m.startsWith("MEXC") ? "mexc" : "kraken", market_type: m.endsWith("SPOT") ? "SPOT" : "PERPETUAL", native_symbol: native(m, b, q),
      base: b, quote: q, native_base: b, native_quote: q, status: "SYNTHETIC fixture", contract_type: m.endsWith("SPOT") ? "SPOT" : "LINEAR_PERPETUAL",
      settlement_asset: m.endsWith("SPOT") ? null : q, settlement_basis: "SYNTHETIC", collected_ms: at, exclusion: null }])) })) : [],
    pair_count: status === "VERIFIED" ? keys.length : 0, exclusions: [], exclusions_truncated: false,
    reference: blocked ? { universe_sha256: "f".repeat(64), status: "VERIFIED", computed_ms: now - 900_000, keys: keys.map(([b, q]) => `${b}/${q}`), current: false } : null,
    universe_sha256: "e".repeat(64),
  };
}

const viewports = [{ name: "384x832-s24plus", width: 384, height: 832 }, { name: "360x800", width: 360, height: 800 }, { name: "412x915", width: 412, height: 915 }];
const real = realPath ? JSON.parse(await readFile(realPath)) : null;
const states = [
  ["liste-verifiee-synthetique", now => synthetic([["BTC", "USDT"], ["ETH", "USDT"], ["SOL", "USDT"]], "VERIFIED", now)],
  ["vide-verifie-reel-20261123T023238Z", () => { assert(real, "SCANNER_UNIVERSE_REAL requis pour l'état vide réel"); return real; }],
  ["indisponible-synthetique", now => synthetic([["BTC", "USDT"]], "UNVERIFIABLE", now)],
];
const subviews = [["moniteur", ""], ["radar-spot", "?product=spot-radar"]];
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const results = [];
for (const vp of viewports) for (const [state, make] of states) for (const [sub, search] of subviews) {
  if (vp.name !== "384x832-s24plus" && sub !== "moniteur") continue;
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  const now = Number(scanner.server_time_ms);
  await page.addInitScript(t => { const offset = t - Date.now(); const N = Date.now; Date.now = () => N() + offset; }, now);
  await page.route("**/api/operator/v1/**", route => {
    const url = new URL(route.request().url()).pathname;
    if (url === "/api/operator/v1/scanner-universe") return route.fulfill({ json: make(now) });
    if (url.startsWith("/api/operator/v1/spot-radar/scanner")) return route.fulfill({ json: scanner });
    return route.fulfill({ status: 503, json: { error_code: "LOCAL_CAPTURE_NOT_CONFIGURED" } });
  });
  await page.goto(`${base}/paper-live/market/radar${search}`);
  await page.waitForSelector(".scanner-universe[data-state]:not([data-state=LOADING])");
  await page.waitForTimeout(600);
  const metrics = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth,
    state: document.querySelector(".scanner-universe")?.getAttribute("data-state"),
    doge: [...document.querySelectorAll("button")].some(b => /^DOGE\//.test(b.textContent?.trim() ?? "") || /^DOGE\//.test(b.getAttribute("aria-label") ?? "")) }));
  assert(metrics.scroll <= metrics.width, `${vp.name} ${state} ${sub}: défilement horizontal ${metrics.scroll} > ${metrics.width}`);
  assert(!metrics.doge, `${vp.name} ${state} ${sub}: DOGE non admis visible`);
  const file = `${out}/scanner-${state}-${sub}-${vp.name}.png`;
  await page.screenshot({ path: file, fullPage: true });
  results.push({ viewport: vp.name, state, subview: sub, ...metrics, file });
  if (state.startsWith("liste") && sub === "moniteur" && vp.name === "384x832-s24plus") {
    await page.getByRole("button", { name: /^BTC\/USDT · vérifiée/ }).click();
    await page.waitForSelector("dialog.universe-detail[open]");
    await page.screenshot({ path: `${out}/scanner-${state}-detail-${vp.name}.png` });
  }
  await context.close();
}
await browser.close();
await writeFile(`${out}/mobile_layout_results.json`, JSON.stringify(results, null, 1) + "\n");
console.log(`${results.length} captures OK, aucune page plus large que l'écran, aucune ligne non admise visible`);
