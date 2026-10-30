// Synthetic source-only proof. Static assets and API responses are fulfilled in
// the browser; UI_PREVIEW_DIST starts no HTTP service and reaches no live API.
import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const dist = path.resolve(process.env.UI_PREVIEW_DIST || "dist");
const fixtureDir = process.env.CROSS_STACK_FIXTURES_DIR || ".cross-stack-fixtures";
const out = process.env.MARKET_CATALOGUE_VISUAL_OUT_DIR || "artifacts/market-catalogue";
const origin = "http://127.0.0.1:4173";
const full = JSON.parse(await readFile(path.join(fixtureDir, "R_market_catalogue.json"), "utf8"));
const legacy = structuredClone(full);
legacy.body.schema_version = "1.0.0";
delete legacy.body.catalogue;
const empty = structuredClone(full);
Object.assign(empty.body, { universe_size: 0, actionable_count: 0, watchlist_count: 0, packets_observed: 0, source_updated_at_utc: null, market_regime: null, top_opportunities: [] });
Object.assign(empty.body.catalogue, { rows: [], qualified_rows: [] });
Object.assign(empty.body.catalogue.coverage, { input_packets: 0, included_packets: 0, outside_window_packets: 0, future_packets: 0, unresolved_timestamp_packets: 0 });
const mime = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".png": "image/png", ".webmanifest": "application/manifest+json" };
let assertions = 0;
const layouts = [], errors = [], blocked = [], requests = [], contrast = [];
function assert(ok, text) { assertions++; if (!ok) throw new Error(text); }
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true, chromiumSandbox: true });
try {
  for (const theme of ["light", "dark"]) for (const width of [1440, 768, 393]) {
    for (const scenario of ["catalogue", "legacy", ...(width === 393 ? ["empty", "missing", "invalid", "network"] : [])]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, locale: "fr-FR", serviceWorkers: "block" });
      await context.addInitScript(t => localStorage.setItem("crypto-terminal.theme", t), theme);
      await context.route("**/*", async route => {
        const request = route.request(), url = new URL(request.url());
        if (url.origin !== origin || !["GET", "HEAD"].includes(request.method())) {
          blocked.push(request.method() + " " + url.origin + url.pathname);
          return route.abort();
        }
        if (url.pathname.startsWith("/api/")) {
          requests.push(request.method() + " " + url.pathname);
          if (!url.pathname.endsWith("/market")) return route.fulfill({ status: 503, contentType: "application/json", body: '{"error_code":"SYNTHETIC_SOURCE_ABSENT"}' });
          if (scenario === "network") return route.abort();
          const fixture = scenario === "legacy" ? legacy : scenario === "empty" ? empty : full;
          const body = scenario === "invalid" ? { ...fixture.body, catalogue: {} } : scenario === "missing" ? { error_code: "MARKET_SNAPSHOT_MISSING" } : fixture.body;
          return route.fulfill({ status: scenario === "missing" ? 503 : 200, contentType: "application/json", body: JSON.stringify(body) });
        }
        const target = request.isNavigationRequest() ? path.join(dist, "index.html") : path.resolve(dist, "." + url.pathname);
        assert(target.startsWith(dist + path.sep), "Static path outside preview");
        return route.fulfill({ status: 200, contentType: mime[path.extname(target)] || "application/octet-stream", body: await readFile(target) });
      });
      const page = await context.newPage();
      page.setDefaultTimeout(10000);
      page.on("pageerror", e => errors.push(String(e)));
      const label = [theme, width, scenario].join("-");
      async function layout(suffix) {
        const g = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: innerWidth }));
        assert(g.scroll <= g.width + 1, label + ": horizontal overflow " + JSON.stringify(g));
        layouts.push({ label: label + suffix, ...g });
      }
      async function capture(suffix) {
        await layout(suffix);
        await page.evaluate(() => {
          if (document.querySelector("#synthetic-proof")) return;
          const e = document.createElement("div"); e.id = "synthetic-proof";
          e.textContent = "APERÇU SYNTHÉTIQUE · NON DÉPLOYÉ";
          e.style.cssText = "position:fixed;bottom:6px;right:6px;background:#183e3d;color:white;padding:5px 8px;font:10px sans-serif;z-index:200;pointer-events:none";
          document.body.append(e);
        });
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(out, label + suffix + ".png"), fullPage: true });
      }
      await page.goto(origin + "/paper-live/market", { waitUntil: "domcontentloaded" });
      await page.getByTestId("market-view").waitFor();
      assert(await page.locator("html").getAttribute("data-theme") === theme, "Theme mismatch");
      if (["missing", "invalid", "network"].includes(scenario)) {
        await page.locator(".market-error-title").waitFor();
        assert(await page.getByTestId("market-opportunity-row").count() === 0, "Error fabricated rows");
        assert(await page.getByTestId("market-heatmap").count() === 0, "Error fabricated heatmap");
      } else if (scenario === "empty") {
        await page.getByTestId("market-empty").waitFor();
        assert(await page.getByTestId("market-opportunity-row").count() === 0, "Empty fabricated rows");
        await page.getByLabel("Population", { exact: true }).selectOption("all");
        assert((await page.getByTestId("market-empty").innerText()).includes("Aucune observation datée"), "Wrong empty population");
      } else {
        await page.getByTestId("market-opportunity-row").first().waitFor();
        assert(await page.getByTestId("market-opportunity-row").count() === 20, "First page is not 20");
        assert((await page.getByTestId("market-freshness").innerText()).includes("périmé"), "Stale warning absent");
        await page.getByText("Provenance et dates des sources", { exact: true }).click();
        assert((await page.getByTestId("market-view").innerText()).includes("2026-10-30 12:00:00Z"), "Publication date absent");
        if (scenario === "catalogue") {
          assert((await page.locator(".market-catalogue-window").innerText()).includes("48 observations incluses sur 51"), "Coverage accounting hidden");
          await page.getByRole("button", { name: "Page suivante", exact: true }).click();
          assert((await page.getByTestId("market-opportunity-row").first().innerText()).includes("COIN20/USDT"), "Pagination reordered rows");
          await page.getByRole("button", { name: "Page suivante", exact: true }).click();
          assert(await page.getByTestId("market-opportunity-row").count() === 6, "Last page incorrect");
          assert(await page.getByRole("button", { name: "Détail BTC/USDT", exact: true }).isVisible(), "BTC outside first 20 missing");
          await page.getByLabel("Recherche symbole", { exact: true }).fill("btc");
          assert((await page.getByTestId("market-opportunity-row").innerText()).includes("49.0"), "Global population score changed");
          assert(await page.getByLabel("Population", { exact: true }).isDisabled(), "Global search population ambiguous");
          await page.getByRole("button", { name: "Détail BTC/USDT", exact: true }).click();
          assert(await page.getByTestId("market-symbol-detail").evaluate(e => e === document.activeElement), "Detail focus absent");
          await page.keyboard.press("Escape");
          assert(await page.getByRole("button", { name: "Détail BTC/USDT", exact: true }).evaluate(e => e === document.activeElement), "Detail focus not restored");
          await page.getByLabel("Recherche symbole", { exact: true }).fill("ETH");
          assert((await page.getByTestId("market-opportunity-row").innerText()).includes("55.0"), "Below-threshold ETH missing");
          await capture("-search-eth");
          await page.getByRole("button", { name: "Réinitialiser", exact: true }).click();
        } else {
          assert((await page.getByTestId("market-scanner-coverage").innerText()).includes("Couverture partielle"), "Legacy limitation hidden");
          await page.getByLabel("Recherche symbole", { exact: true }).fill("BTC");
          await page.getByTestId("market-filter-empty").waitFor();
          assert(await page.getByLabel("Population", { exact: true }).count() === 0, "Legacy invented full catalogue");
          await page.getByRole("button", { name: "Réinitialiser", exact: true }).click();
        }
        await capture("-table");
        await page.getByRole("button", { name: "Carte des symboles", exact: true }).click();
        assert(await page.getByRole("table").count() === 0, "Table duplicated in heatmap");
        assert(await page.locator(".market-heat-cell").count() === 20, "Heatmap population differs");
        const names = await page.locator(".market-heat-cell strong").allTextContents();
        assert(names.join("|") === full.body.top_opportunities.map(r => r.symbol).join("|"), "Heatmap source order changed");
        await page.locator(".market-heat-cell").first().focus();
        await page.keyboard.press("Enter");
        assert((await page.getByTestId("market-symbol-detail").innerText()).includes("90.0"), "Keyboard detail changed source score");
        await page.keyboard.press("Escape");
        assert(await page.locator(".market-heat-cell").first().evaluate(e => e === document.activeElement), "Heatmap focus not restored");
        const ratios = await page.locator(".market-heat-cell").evaluateAll(elements => {
          function luminance(color) {
            const normalized = color.startsWith("color(srgb");
            const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => normalized ? v : v / 255);
            const l = rgb.map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
            return .2126 * l[0] + .7152 * l[1] + .0722 * l[2];
          }
          return elements.map(e => { const s = getComputedStyle(e), a = luminance(s.color), b = luminance(s.backgroundColor); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); });
        });
        contrast.push({ label, minimum: Math.min(...ratios) });
        assert(ratios.every(r => r >= 4.5), "Heatmap text contrast below AA: " + JSON.stringify(ratios));
        await capture("-map");
        if (scenario === "catalogue") {
          await page.getByLabel("Régime publié", { exact: true }).selectOption("VOLATILE");
          assert(await page.locator(".market-heat-cell").count() === 15, "Regime filter incorrect");
        }
        await page.getByText("Timing, volume et limites du scanner", { exact: true }).click();
        assert((await page.locator(".market-analysis-notes").innerText()).includes("Non disponible : les volumes de marché"), "Missing volume falsely available");
      }
      await capture("-final");
      await context.close();
      console.log(label + " PASS");
    }
  }
  assert(errors.length === 0, "Browser errors: " + errors.join("\n"));
  assert(blocked.length === 0, "External/mutating requests: " + blocked.join("\n"));
  assert(requests.every(r => r.startsWith("GET /api/operator/v1/")), "Unexpected API method");
  await writeFile(path.join(out, "checks.json"), JSON.stringify({
    scope: "SYNTHETIC_SOURCE_ONLY_NOT_DEPLOYED", assertions, layouts, contrast,
    errors, blocked, requests: [...new Set(requests)], chromiumSandbox: true,
    serviceWorkers: "blocked", liveApiReached: false, httpServerStarted: false,
  }, null, 2));
  console.log("MARKET_CATALOGUE_BROWSER=PASS", assertions, layouts.length);
} finally { await browser.close(); }
