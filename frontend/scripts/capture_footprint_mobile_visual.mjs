// Preuve visuelle locale du panneau Footprint (vue Microstructure).
// Vérifie l'absence de défilement horizontal de PAGE aux largeurs mobiles et
// capture les états : non alimenté, démo historique (clair/sombre), plein écran,
// fichier absent. Le rejeu servi ici est SYNTHÉTIQUE et marqué comme tel :
// il ne constitue ni une preuve runtime ni une donnée de marché.
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const base = process.env.FOOTPRINT_VISUAL_BASE_URL || "http://127.0.0.1:4173";
const out = process.env.FOOTPRINT_VISUAL_OUT_DIR || "artifacts/footprint-mobile";
const REPLAY = "/observations/footprint/mexc-btc_usdt-perp-replay-v1.json";
const assert = (ok, message) => { if (!ok) throw new Error(message); };

// Marche aléatoire déterministe : 3 h de transactions synthétiques, couverture partielle.
function syntheticReplay() {
  let seed = 42; const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  const from = Date.UTC(2026, 10, 20, 9, 37, 0); const to = from + 3 * 3_600_000;
  const trades = []; let price = 91_250;
  for (let ts = from + 500; ts < to; ts += 400 + Math.floor(rnd() * 1600)) {
    price = Math.round((price + (rnd() - 0.5) * 6) * 10) / 10;
    const r = rnd();
    trades.push({ ts, price, qty: 1 + Math.floor(rnd() * 400), side: r < 0.48 ? "buy" : r < 0.97 ? "sell" : null });
  }
  return {
    schema: "cat.footprint.replay.v1",
    provenance: {
      venue: "MEXC", market_type: "perpetual", symbol: "BTC_USDT", source: "FIXTURE SYNTHÉTIQUE · capture visuelle locale",
      collected_at_utc: new Date(to + 60_000).toISOString(), coverage_from_utc: new Date(from).toISOString(), coverage_to_utc: new Date(to).toISOString(),
      qty_unit: "contracts", side_semantics: "aggressor",
      gaps: [{ from_utc: new Date(from + 3_600_000).toISOString(), to_utc: new Date(from + 3_660_000).toISOString() }],
      notes: "Données fictives pour vérifier la mise en page.",
    },
    tick_size: 0.1, trades,
  };
}

const viewports = [
  { name: "360x800", width: 360, height: 800 }, { name: "384x832-s24plus", width: 384, height: 832 },
  { name: "390x844", width: 390, height: 844 }, { name: "412x915", width: 412, height: 915 },
  { name: "832x384-paysage", width: 832, height: 384 }, { name: "1440x900", width: 1440, height: 900 },
];
const body = JSON.stringify(syntheticReplay());
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const results = []; const errors = [];
try {
  for (const vp of viewports) {
    for (const scenario of ["unfed", "demo", "demo-dark", "fullscreen", "absent"]) {
      const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1, isMobile: vp.width < 800, hasTouch: vp.width < 800 });
      page.on("pageerror", (e) => errors.push(`${vp.name}/${scenario}: ${e}`));
      await page.route("**/api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"error_code":"SOURCE_NOT_DEPLOYED"}' }));
      await page.route(`**${REPLAY}`, (route) => scenario === "absent"
        ? route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>SPA</title>" })
        : route.fulfill({ status: 200, contentType: "application/json", body }));
      assert((await page.goto(`${base}/paper-live/market/lmi`, { waitUntil: "networkidle" }))?.ok(), "navigation");
      const panel = page.getByTestId("footprint-panel");
      await panel.waitFor();
      if (scenario !== "unfed") {
        await page.getByRole("radio", { name: "Démo historique" }).click();
        await page.getByTestId(scenario === "absent" ? "footprint-replay-absent" : "footprint-table").waitFor();
      }
      if (scenario === "demo-dark") await page.getByRole("button", { name: "Thème sombre" }).click();
      if (scenario === "fullscreen") await page.getByRole("button", { name: "Plein écran" }).click();
      await page.waitForTimeout(150);
      const m = await page.evaluate(() => {
        const doc = document.documentElement; const scroller = document.querySelector('[data-testid="footprint-scroll"]');
        const p = document.querySelector('[data-testid="footprint-panel"]').getBoundingClientRect();
        return { pageScrollWidth: doc.scrollWidth, viewport: doc.clientWidth, panelRight: Math.round(p.right), panelLeft: Math.round(p.left),
          tableScrollWidth: scroller?.scrollWidth ?? null, tableClientWidth: scroller?.clientWidth ?? null,
          theme: document.querySelector('[data-testid="footprint-panel"]').dataset.footprintTheme };
      });
      const ok = m.pageScrollWidth <= m.viewport && m.panelLeft >= 0 && m.panelRight <= m.viewport;
      results.push({ viewport: vp.name, scenario, ok, ...m });
      if (scenario !== "fullscreen") await panel.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${out}/${vp.name}-${scenario}.png`, fullPage: scenario !== "fullscreen" });
      await page.close();
    }
  }
} finally { await browser.close(); }
console.log(JSON.stringify(results, null, 1));
const bad = results.filter((r) => !r.ok);
assert(errors.length === 0, `Erreurs de page : ${errors.join(" | ")}`);
assert(bad.length === 0, `Défilement horizontal de page : ${bad.map((r) => `${r.viewport}/${r.scenario} ${r.pageScrollWidth}>${r.viewport}`).join(", ")}`);
console.log(`FOOTPRINT_MOBILE_VISUAL_PASS ${results.length} captures`);
