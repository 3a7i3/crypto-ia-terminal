import { chromium } from "playwright";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";

const base = process.env.APP_UNIFY_U3A_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const out = process.env.APP_UNIFY_U3A_VISUAL_OUT_DIR || "artifacts/app-unify-u3a";
const fixture = JSON.parse(await readFile(".cross-stack-fixtures/L_scanner.json", "utf8"));
const assert = (ok, message) => { if (!ok) throw new Error(message); };
assert(fixture.http_status === 200 && fixture.body.top_opportunities.length === 50, "Invalid producer fixture");
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const errors = [], requests = [];
try {
  for (const width of [1440, 390]) {
    for (const scenario of ["fresh", "stale", "empty", "missing", "invalid", "network"]) {
      const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 } });
      page.on("pageerror", (error) => errors.push(String(error)));
      const scenarioRequests = [];
      page.on("request", (request) => {
        const pathname = new URL(request.url()).pathname;
        if (pathname.startsWith("/api/")) {
          const record = `${request.method()} ${pathname}`;
          requests.push(record); scenarioRequests.push(record);
        }
      });
      await page.route("**/api/**", (route) => {
        if (new URL(route.request().url()).pathname !== "/api/operator/v1/market") return route.fulfill({ status: 503, contentType: "application/json", body: '{"error_code":"SOURCE_NOT_DEPLOYED"}' });
        if (scenario === "network") return route.abort();
        const body = structuredClone(fixture.body);
        if (scenario === "stale") { body.freshness_classification = "STALE"; body.snapshot_age_s = 120; }
        if (scenario === "empty") { body.top_opportunities = []; body.actionable_count = 0; }
        if (scenario === "invalid") body.top_opportunities[0].entry = 100;
        return route.fulfill({ status: scenario === "missing" ? 503 : 200, contentType: "application/json", body: JSON.stringify(scenario === "missing" ? { error_code: "MARKET_SNAPSHOT_MISSING" } : body) });
      });
      assert((await page.goto(`${base}/paper-live/market`, { waitUntil: "networkidle" }))?.ok(), "Navigation failed");
      const view = page.getByTestId("market-view");
      if (["fresh", "stale"].includes(scenario)) {
        await page.getByTestId("market-scanner-coverage").waitFor();
        assert((await view.innerText()).includes("50 ligne(s) publiée(s) sur 60"), "Coverage missing");
        const initialMarketRequests = scenarioRequests.filter((r) => r.endsWith("/market")).length;
        await page.getByLabel("Recherche symbole").fill("  s25  ");
        await page.getByLabel("Biais dominant").selectOption("SHORT");
        const item = width === 390 ? page.getByTestId("market-opportunity-card") : page.getByTestId("market-opportunity-row");
        assert(await item.count() === 1 && (await item.innerText()).includes("S25/USDT"), "Combined filter failed");
        await item.getByRole("button", { name: "Détail S25/USDT" }).click();
        const detail = page.getByTestId("market-symbol-detail");
        assert((await detail.innerText()).includes("86.7"), "Source aggregate changed");
        assert((await detail.innerText()).includes("exacts non disponibles"), "Unavailable counts missing");
        if (scenario === "stale") assert((await view.innerText()).includes("état actuel du marché INCONNU"), "Stale current state missing");
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(out, `scanner-${scenario}-${width}.png`), fullPage: true });
        await page.getByLabel("Recherche symbole").fill("absent");
        await page.getByTestId("market-filter-empty").waitFor();
        assert(await detail.count() === 0, "Old detail retained after filter");
        await page.screenshot({ path: path.join(out, `scanner-no-match-${scenario}-${width}.png`), fullPage: true });
        await page.getByRole("button", { name: "Réinitialiser" }).click();
        assert(await page.getByTestId("market-opportunity-row").count() === 50, "Reset lost ranking");
        await page.getByLabel("Biais dominant").selectOption("MIXED");
        assert((await view.innerText()).includes("S02/USDT"), "MIXED filter missing");
        assert(scenarioRequests.filter((r) => r.endsWith("/market")).length === initialMarketRequests, "Filters triggered API request");
      } else if (scenario === "empty") {
        await page.getByTestId("market-empty").waitFor();
        assert(await page.getByTestId("market-filter-empty").count() === 0, "Source-empty conflated with filter-empty");
      } else {
        await page.getByTestId("market-error").waitFor();
        assert(await page.getByTestId("market-symbol-detail").count() === 0, "Error retained detail");
        assert(await page.getByTestId("market-scanner-coverage").count() === 0, "Error fabricated coverage");
      }
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `${scenario}/${width}: horizontal overflow`);
      for (const forbidden of ["Entry", "Stop Loss", "Take Profit"]) assert(!(await view.innerText()).includes(forbidden), `Execution field ${forbidden}`);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(out, `scanner-final-${scenario}-${width}.png`), fullPage: true });
      await page.close();
    }
  }
  assert(errors.length === 0, `Browser errors: ${errors.join(", ")}`);
  assert(requests.every((r) => r.startsWith("GET /api/operator/v1/")), "Unexpected/mutating request");
  console.log("APP_UNIFY_U3A_SCANNER_DESKTOP_MOBILE_FILTERS_DETAIL_ERRORS_GET_ONLY=PASS");
} finally { await browser.close(); }
