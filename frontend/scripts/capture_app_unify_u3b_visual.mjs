import { chromium } from "playwright";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";

const base = process.env.APP_UNIFY_U3B_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const out = process.env.APP_UNIFY_U3B_VISUAL_OUT_DIR || "artifacts/app-unify-u3b";
const fixture = JSON.parse(await readFile(".cross-stack-fixtures/M_microstructure.json", "utf8"));
const scanner = JSON.parse(await readFile(".cross-stack-fixtures/L_scanner.json", "utf8"));
const assert = (ok, message) => { if (!ok) throw new Error(message); };
assert(fixture.http_status === 200 && fixture._proof.source_unchanged, "Invalid actual producer fixture");
await mkdir(out, { recursive: true });
const scenarios = ["fresh", "stale", "degraded", "unknown", "empty", "missing", "invalid", "network", "legacy"];
const browser = await chromium.launch({ headless: true });
const errors = [], requests = [];
try {
  for (const width of [1440, 390]) {
    for (const scenario of scenarios) {
      const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 } });
      page.on("pageerror", (error) => errors.push(String(error)));
      page.on("request", (request) => { if (new URL(request.url()).pathname.startsWith("/api/")) requests.push(`${request.method()} ${new URL(request.url()).pathname}`); });
      await page.route("**/api/**", (route) => {
        const pathname = new URL(route.request().url()).pathname;
        if (pathname === "/api/operator/v1/market" && ["missing", "invalid", "network"].includes(scenario)) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(scanner.body) });
        if (pathname !== "/api/operator/v1/market-microstructure") return route.fulfill({ status: 503, contentType: "application/json", body: '{"error_code":"SOURCE_NOT_DEPLOYED"}' });
        if (scenario === "network") return route.abort();
        const body = structuredClone(fixture.body);
        if (scenario === "stale") {
          body.read_at_utc = "2026-09-14T20:02:00.000Z"; body.source_age_s = 120; body.freshness_classification = "STALE";
          for (const r of body.rows) for (const name of ["flow", "liquidity", "resistance"]) {
            const group = r.detail?.[name];
            if (group?.observed_at_utc !== null && group?.observed_at_utc !== undefined) { group.observation_age_s += 118; group.freshness_classification = "STALE"; }
          }
          for (const r of body.rows) if (r.observed_at_utc !== null) { r.observation_age_s += 118; r.freshness_classification = "STALE"; }
        }
        if (scenario === "legacy") { body.schema_version = "1.0.0"; for (const r of body.rows) delete r.detail; }
        if (scenario === "degraded") { body.unit_contract_source = "fallback"; body.unit_contract_degraded = true; }
        if (scenario === "unknown") { body.rows[0].observed_at_utc = null; body.rows[0].observation_age_s = null; body.rows[0].freshness_classification = "UNKNOWN"; }
        if (scenario === "empty") { body.rows = []; body.coverage = { requested: 0, streamable: 0, observed: 0, unavailable: 0 }; body.pressure_field_count = 0; }
        if (scenario === "invalid") body.rows[0].entry_price = 100;
        return route.fulfill({ status: scenario === "missing" ? 503 : 200, contentType: "application/json", body: JSON.stringify(scenario === "missing" ? { error_code: "MICROSTRUCTURE_MISSING" } : body) });
      });
      assert((await page.goto(`${base}/paper-live/market`, { waitUntil: "networkidle" }))?.ok(), "Navigation failed");
      const view = page.getByTestId("microstructure-view");
      await view.waitFor();
      if (["missing", "invalid", "network"].includes(scenario)) {
        assert((await view.innerText()).includes("INCONNU"), "Failure not explicit");
        assert(await page.getByTestId("microstructure-coverage").count() === 0, "Error fabricated coverage");
        assert((await page.getByTestId("market-view").innerText()).includes("S25/USDT"), "LMI failure hid Scanner");
      } else {
        assert(await page.getByTestId("market-error").count() === 1, "Fixture did not exercise independent scanner error");
        assert((await view.innerText()).includes("Demandés"), "Coverage missing");
        if (scenario === "empty") assert((await view.innerText()).includes("Watchlist explicitement vide"), "Empty population missing");
        else {
          assert((await view.innerText()).includes("BTCUSDT"), "LMI hidden by Advisor/Scanner failure");
          assert((await view.innerText()).includes("WAITUSDT"), "Unavailable symbol hidden");
          if (scenario === "stale") assert((await view.innerText()).includes("mesures historiques"), "Stopped source looks live");
          if (scenario === "degraded") assert((await view.innerText()).includes("DÉGRADÉES"), "Unit quality hidden");
          if (scenario === "unknown") assert((await page.getByTestId("microstructure-row").first().innerText()).includes("UNKNOWN"), "Timestamp fabricated");
          await page.getByRole("checkbox").check();
          assert(await page.getByTestId("microstructure-row").count() === 1, "Notable filter incorrect");
          await page.getByLabel("Recherche LMI").fill("eth");
          await page.getByTestId("microstructure-empty").waitFor();
          await page.getByRole("button", { name: "Réinitialiser LMI" }).click();
          assert(await page.getByTestId("microstructure-row").count() === 3, "Reset lost source population");
        }
        await view.locator("summary").first().click();
        for (const detail of await view.getByTestId("lmi-detail").all()) await detail.locator("summary").click();
        if (scenario === "fresh") {
          assert((await view.getByTestId("lmi-detail-liquidity").first().innerText()).includes("STALE"), "Liquidity inherited field freshness");
          assert((await view.innerText()).includes("-462.375"), "Exact signed liquidity missing");
          assert((await view.innerText()).includes("n’est pas attestée"), "Book evidence limitation missing");
        }
        if (scenario === "legacy") assert((await view.innerText()).includes("Détail non publié"), "Legacy snapshot rejected");
        assert((await view.innerText()).includes("OBSERVATIONAL_TELEMETRY"), "Provenance missing");
      }
      await view.scrollIntoViewIfNeeded();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `${scenario}/${width}: overflow`);
      for (const forbidden of ["Entry", "Stop Loss", "Take Profit", "GHOSTUSDT", "MUST_NOT_ESCAPE"]) assert(!(await view.innerText()).includes(forbidden), `Unexpected source field ${forbidden}`);
      // Capture the independent card at the top; also retain full app layout proof.
      // Hide sticky shell only in the isolated card capture; full-page proof below preserves it.
      await view.screenshot({ path: path.join(out, `lmi-${scenario}-${width}.png`), style: ".operator-header { visibility: hidden !important; }" });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(out, `market-${scenario}-${width}.png`), fullPage: true });
      await page.close();
    }
  }
  assert(errors.length === 0, `Browser errors: ${errors.join(", ")}`);
  assert(requests.every((r) => r.startsWith("GET /api/operator/v1/")), "Unexpected/mutating request");
  console.log("APP_UNIFY_U3B_LMI_DESKTOP_MOBILE_INDEPENDENCE_FRESHNESS_ERRORS_GET_ONLY=PASS");
} finally { await browser.close(); }
