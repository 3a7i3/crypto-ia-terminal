import { chromium } from "playwright";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
const base = process.env.APP_UNIFY_U4_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const out = process.env.APP_UNIFY_U4_VISUAL_OUT_DIR || "artifacts/app-unify-u4";
const fixture = JSON.parse(await readFile(".cross-stack-fixtures/N_research_publication.json", "utf8"));
const assert = (ok, message) => { if (!ok) throw new Error(message); };
assert(fixture.http_status === 200 && fixture._proof.builder_invoked, "Missing real builder/API fixture");
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const errors = [], requests = [];
try {
  for (const width of [1440, 390]) for (const scenario of ["published", "historical", "empty", "missing", "invalid", "network"]) {
    const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 } });
    page.on("pageerror", e => errors.push(String(e)));
    page.on("request", r => { if (new URL(r.url()).pathname.startsWith("/api/")) requests.push(`${r.method()} ${new URL(r.url()).pathname}`); });
    await page.route("**/api/**", route => {
      if (new URL(route.request().url()).pathname !== "/api/operator/v1/research-lab") return route.fulfill({ status: 503, contentType: "application/json", body: '{"error_code":"SOURCE_NOT_DEPLOYED"}' });
      if (scenario === "network") return route.abort();
      const body = structuredClone(fixture.body);
      if (scenario === "historical") body.generated_at_utc = "2020-01-01T00:00:00Z";
      if (scenario === "empty") { body.research_state = "EMPTY"; body.population.n = body.provenance.primary_context.n = 0; for (const k of ["performance", "risk_stability", "costs", "attribution"]) body[k] = []; }
      if (scenario === "invalid") body.provenance.primary_context.n = 999;
      return route.fulfill({ status: scenario === "missing" ? 503 : 200, contentType: "application/json", body: JSON.stringify(scenario === "missing" ? { error_code: "RESEARCH_LAB_SNAPSHOT_MISSING" } : body) });
    });
    assert((await page.goto(`${base}/research`, { waitUntil: "networkidle" }))?.ok(), "Navigation failed");
    const view = page.getByTestId("research-lab-view");
    await view.waitFor();
    if (["missing", "invalid", "network"].includes(scenario)) {
      assert((await view.innerText()).includes(scenario === "missing" ? "unavailable" : "contract/transport error"), "Failure hidden");
      assert(await page.getByTestId("research-metric-card").count() === 0, "Error retained metrics");
    } else {
      const text = await view.innerText();
      for (const required of ["NON-AUTHORITATIVE", "LOW_SAMPLE", "Candidate catalog NOT_AVAILABLE"]) assert(text.includes(required), `Missing ${required}`);
      if (scenario === "empty") assert(text.includes("EMPTY") && await page.getByTestId("research-metric-card").count() === 0, "Empty population fabricated metrics");
      else assert(text.toLowerCase().includes("closed_population_fees_usd") && text.toLowerCase().includes("mark_to_market_max_drawdown") && text.includes("NOT_AVAILABLE"), "Costs/limitations lost");
      await page.getByText("Full Research provenance").click();
      const sources = await page.getByTestId("research-source-artifacts").innerText();
      assert(sources.includes(fixture._proof.manifest_sha256) && sources.includes(fixture._proof.diagnostic_sha256), "Source digest lost");
      if (scenario === "historical") assert((await view.innerText()).includes("2020-01-01T00:00:00Z"), "Historical evidence rejuvenated");
    }
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `${scenario}/${width}: overflow`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(out, `research-${scenario}-${width}.png`), fullPage: true });
    if (["published", "missing"].includes(scenario)) {
      await page.goto(`${base}/direction`, { waitUntil: "networkidle" });
      const card = page.getByTestId("direction-research-card"); await card.waitFor();
      assert((await card.innerText()).includes(scenario === "published" ? "AVAILABLE" : "ERREUR SOURCE"), "Direction hides independent Research");
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), "Direction overflow");
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(out, `direction-full-${scenario}-${width}.png`), fullPage: true });
      await card.screenshot({ path: path.join(out, `direction-research-${scenario}-${width}.png`), style: ".operator-header, .direction-header { visibility: hidden !important; }" });
    }
    await page.close();
  }
  assert(errors.length === 0, `Browser errors: ${errors.join(", ")}`);
  assert(requests.every(r => r.startsWith("GET /api/operator/v1/")), "Unexpected mutation/transport");
  console.log("APP_UNIFY_U4_RESEARCH_DESKTOP_MOBILE_PROVENANCE_FAILURES_DIRECTION_GET_ONLY=PASS");
} finally { await browser.close(); }
