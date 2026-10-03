import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const base = process.env.APP_EVENTS_BASE_URL || "http://127.0.0.1:3000";
const out = process.env.APP_EVENTS_OUT_DIR || "artifacts/app-events";
const fixture = JSON.parse(await readFile(".cross-stack-fixtures/L_events.json", "utf8"));
if (fixture.http_status !== 200) throw new Error("Real producer fixture failed");
const clone = () => structuredClone(fixture.body);
const stale = clone();
stale.snapshot_age_s = 100; stale.freshness_classification = "STALE";
stale.sources[2].source_age_s = 100; stale.sources[2].freshness_classification = "STALE";
const empty = clone(); empty.events = [];
for (const s of empty.sources) { s.records_observed = s.events_observed = s.excluded_records = s.published_count = s.undated_count = 0; }
const partial = clone(); partial.events = partial.events.filter(e => e.source_id !== "p12_alerts");
for (const key of Object.keys(partial.sources[0])) if (!["source_id", "format", "status", "freshness_classification"].includes(key)) partial.sources[0][key] = null;
partial.sources[0].status = "MISSING"; partial.sources[0].freshness_classification = "NOT_AVAILABLE";
const scenarios = [
  { name: "populated", body: clone(), text: "Date inconnue · aucun fuseau déduit" },
  { name: "stale", body: stale, text: "Capture périmée : événements historiques" },
  { name: "empty", body: empty, text: "Aucun événement dans cette capture" },
  { name: "partial", body: partial, text: "Source absente" },
  { name: "missing", body: { error_code: "EVENT_CENTER_MISSING" }, status: 503, text: "EVENT_CENTER_MISSING" },
  { name: "invalid", body: { product: "EventCenterSnapshot" }, text: "EVENT_CENTER_CONTRACT_ERROR" },
  { name: "network", abort: true, text: "EVENT_CENTER_TRANSPORT_ERROR" },
];
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const errors = [], requests = [];
const assert = (ok, text) => { if (!ok) throw new Error(text); };
try {
  for (const width of [1440, 390]) for (const scenario of scenarios) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    page.on("pageerror", e => errors.push(String(e)));
    page.on("request", r => { if (new URL(r.url()).pathname.startsWith("/api/")) requests.push(`${r.method()} ${new URL(r.url()).pathname}`); });
    await page.route("**/api/**", route => {
      if (new URL(route.request().url()).pathname !== "/api/operator/v1/events") return route.fulfill({ status: 503, contentType: "application/json", body: '{"error_code":"SNAPSHOT_MISSING"}' });
      if (scenario.abort) return route.abort();
      return route.fulfill({ status: scenario.status ?? 200, contentType: "application/json", body: JSON.stringify(scenario.body) });
    });
    await page.goto(`${base}/paper-live/events`, { waitUntil: "networkidle" });
    const view = page.getByTestId("events-view");
    await view.locator("summary").evaluateAll(nodes => nodes.forEach(n => n.click()));
    assert((await view.innerText()).includes(scenario.text), `${scenario.name}/${width}: missing state`);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `${scenario.name}/${width}: overflow`);
    assert(!(await view.innerText()).includes("SECRET_CONTEXT"), "Raw context leaked");
    await page.screenshot({ path: path.join(out, `${scenario.name}-${width}.png`), fullPage: true });
    if (scenario.name === "populated") {
      await page.getByLabel("Source", { exact: true }).selectOption("ppl_lifecycles");
      assert(await page.getByTestId("event-row").count() === 5, "Source filter failed");
      await page.getByLabel("Sévérité", { exact: true }).selectOption("CRITICAL");
      assert((await page.getByTestId("events-empty").innerText()).includes("filtres"), "Empty filter missing");
      await page.screenshot({ path: path.join(out, `filters-${width}.png`), fullPage: true });
    }
    await page.close();
  }
  assert(errors.length === 0, "Browser errors");
  assert(requests.includes("GET /api/operator/v1/events") && requests.every(r => r.startsWith("GET /api/operator/v1/")), "Unexpected API method");
  await writeFile(path.join(out, "proof.json"), JSON.stringify({ synthetic: true, screenshots: 16, viewportWidths: [1440, 390], errors, requests }, null, 2));
  console.log("APP_EVENTS_DESKTOP_MOBILE_STATES_FILTERS_GET_ONLY=PASS (16 screenshots)");
} finally { await browser.close(); }
