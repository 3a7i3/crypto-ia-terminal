// Preuve visuelle locale — Radar de signaux · Démo (Marché → Scanner), fixture SYNTHÉTIQUE
// cat.signals.indicators.v1 BTC. Deux états à 384 px : quatre marchés, puis MEXC seul.
// Vérifie : aucun défilement horizontal (page ET tableau), en-têtes non tronqués, aucune
// requête vers un service de signaux. L'univers Scanner est servi VIDE VÉRIFIÉ (synthétique).
// Usage : npm run build && npx vite preview --port 4173 &
//         [PLAYWRIGHT_MODULE=/chemin/playwright/index.js] node scripts/capture_signals_demo_mobile.mjs
const pw = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const { chromium } = pw.default ?? pw;
import { mkdir, writeFile } from "node:fs/promises";

const base = process.env.SIGNALS_VISUAL_BASE_URL || "http://127.0.0.1:4173";
const out = process.env.SIGNALS_VISUAL_OUT_DIR || "artifacts/signals-demo-mobile";
const assert = (ok, message) => { if (!ok) throw new Error(message); };
const MARKETS = ["MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_SPOT", "KRAKEN_PERPETUAL"];
const emptyUniverse = now => ({
  schema_version: "scanner-universe/1.0.0", product: "ScannerCommonUniverse", authority: "OBSERVATIONAL_TELEMETRY", execution_authority: false,
  rule: "SYNTHETIC", status: "VERIFIED_EMPTY", computed_ms: now, served_ms: now, freshness_max_age_ms: 2_100_000, cadence_ms: 900_000, blocking_sources: [],
  sources: MARKETS.map(m => ({ market: m, state: "COMPLETE", catalogue_state: "COMPLETE", reason: null, collected_ms: now - 120_000, age_ms: 120_000,
    current: true, instruments: 100, admissible: 90, excluded: {}, raw_sha256: {} })),
  pairs: [], pair_count: 0, exclusions: [], exclusions_truncated: false, reference: null, universe_sha256: "e".repeat(64),
});

await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 384, height: 832 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
const page = await context.newPage();
const requests = [];
page.on("request", r => requests.push(new URL(r.url()).pathname));
await page.route("**/api/operator/v1/**", route => {
  const url = new URL(route.request().url()).pathname;
  if (url === "/api/operator/v1/scanner-universe") return route.fulfill({ json: emptyUniverse(Date.now()) });
  return route.fulfill({ status: 503, json: { error_code: "LOCAL_CAPTURE_NOT_CONFIGURED" } });
});
await page.goto(`${base}/paper-live/market/radar?product=signals-demo`);
await page.getByRole("table", { name: "Indicateurs BTC" }).waitFor();
await page.getByText(/Univers vide vérifié/).first().waitFor();

const measure = () => page.evaluate(() => {
  const scroller = document.querySelector(".signals-scroll");
  const clipped = [...document.querySelectorAll(".signals-table thead th")].filter(th => th.scrollWidth > th.clientWidth + 1).map(th => th.textContent);
  return { page: [document.documentElement.scrollWidth, innerWidth], table: [scroller.scrollWidth, scroller.clientWidth],
    headers: [...document.querySelectorAll(".signals-table thead th")].map(th => th.textContent), clipped };
});
const results = [];
for (const [state, hide] of [["quatre-marches", []], ["mexc-seul", ["KR·S", "KR·P"]]]) {
  for (const m of hide) await page.getByRole("button", { name: m, exact: true }).click();
  const r = await measure();
  assert(r.page[0] <= r.page[1], `${state}: défilement horizontal de page ${r.page}`);
  assert(r.table[0] <= r.table[1], `${state}: défilement horizontal du tableau ${r.table}`);
  assert(r.clipped.length === 0, `${state}: en-têtes tronqués ${r.clipped}`);
  const file = `${out}/radar-signaux-demo-${state}-384x832.png`;
  await page.screenshot({ path: file, fullPage: true });
  results.push({ state, ...r, file });
}
const signalRequests = requests.filter(u => /signal/i.test(u));
assert(signalRequests.length === 0, `requêtes signaux inattendues : ${signalRequests}`);
await writeFile(`${out}/result.json`, JSON.stringify({ base, results, api_requests: [...new Set(requests.filter(u => u.startsWith("/api/")))], signal_requests: signalRequests }, null, 2));
console.log(JSON.stringify(results.map(({ state, page, table, headers, clipped }) => ({ state, page, table, headers, clipped }))));
await browser.close();
