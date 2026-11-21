import { createRequire } from "node:module";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const { chromium } = createRequire(import.meta.url)("playwright");
const here = path.dirname(fileURLToPath(import.meta.url)), root = path.resolve(here, "../dist");
const fixtures = process.env.CROSS_STACK_FIXTURES_DIR;
if (!fixtures) throw Error("CROSS_STACK_FIXTURES_DIR required; no fixture skips");
const out = path.resolve(here, "../artifacts/market-positioning"), origin = "http://127.0.0.1:4173";
const read = async name => JSON.parse(await readFile(path.join(fixtures, name + ".json"), "utf8"));
const LEGS = { a: "exchange_a:BTC_USDT:PERPETUAL_LINEAR", b: "exchange_b:PF_XBTUSD:PERPETUAL_LINEAR", c: "exchange_c:BTC-PERP:PERPETUAL_LINEAR", d: "exchange_d:BTCUSDT:PERPETUAL_LINEAR" };
const cases = [
  ["synthetic", await read("S_derivatives_positioning")], ["stale", await read("S_derivatives_positioning_stale")],
  ["missing", { http_status: 503, body: { error_code: "DERIVATIVES_POSITIONING_NOT_CONFIGURED" } }],
  ["invalid", { http_status: 200, body: { ...(await read("S_derivatives_positioning")).body, execution_authority: true } }],
];
let assertions = 0; const views = [], errors = [], blocked = [], requests = [];
const assert = (ok, m) => { assertions++; if (!ok) throw Error(m); };
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true, chromiumSandbox: true });
try {
  for (const theme of ["light", "dark"]) for (const width of [1440, 384]) for (const [name, fixture] of cases) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 2, locale: "fr-FR", serviceWorkers: "block" });
    await context.addInitScript(t => localStorage.setItem("crypto-terminal.theme", t), theme);
    await context.route("**/*", async route => {
      const q = route.request(), u = new URL(q.url());
      if (u.origin !== origin || !["GET", "HEAD"].includes(q.method())) { blocked.push(q.method() + " " + u.href); return route.abort(); }
      if (u.pathname.startsWith("/api/")) {
        requests.push(q.method() + " " + u.pathname);
        const f = u.pathname.endsWith("/derivatives-positioning") ? fixture : { http_status: 503, body: { error_code: "SYNTHETIC_NOT_AVAILABLE" } };
        return route.fulfill({ status: f.http_status, contentType: "application/json", body: JSON.stringify(f.body) });
      }
      const target = q.isNavigationRequest() ? path.join(root, "index.html") : path.resolve(root, "." + u.pathname);
      assert(target.startsWith(root + path.sep), "static path remains in build");
      const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".webmanifest": "application/manifest+json" };
      return route.fulfill({ status: 200, contentType: mime[path.extname(target)] || "application/octet-stream", body: await readFile(target) });
    });
    const page = await context.newPage(); page.setDefaultTimeout(10000); page.on("pageerror", e => errors.push(String(e)));
    await page.goto(origin + "/paper-live/market/venues", { waitUntil: "networkidle" });
    const panel = page.getByTestId("positioning-panel");
    await panel.waitFor();
    const shots = [];
    if (name === "missing" || name === "invalid") {
      const text = await panel.innerText();
      assert(text.includes("Aucune lecture de positionnement disponible"), name + ": unavailable is stated");
      assert(await panel.getByTestId("pos-card-oi").count() === 0, name + ": no card with empty values");
      assert((await panel.getByTestId("market-source-not-configured").count()) === (name === "missing" ? 1 : 0), name + ": unconfigured is distinct from a contract failure");
      shots.push(name);
    } else {
      assert(await panel.getByTestId("pos-synthetic").count() === 1, "synthetic evidence is stated");
      const legs = name === "synthetic" ? ["a", "b", "c", "d"] : ["a"];
      for (const k of legs) {
        await panel.getByLabel("Plateforme et contrat").selectOption(LEGS[k]);
        const text = await panel.innerText();
        if (k !== "d") for (const id of ["pos-card-oi", "pos-card-oi-change", "pos-card-funding", "pos-card-premium-basis"]) assert(await panel.getByTestId(id).count() === 1, k + ": card " + id);
        if (k === "a") { assert(await panel.getByTestId("pos-chart").count() === 1, "a: comparable series drawn"); assert(text.includes("contrats"), "a: OI unit"); assert(text.includes(name === "stale" ? "Périmée" : "Récente"), "freshness"); }
        if (k === "b") { assert(text.includes("INSUFFICIENT_COVERAGE"), "b: partial coverage stated"); assert(text.includes("unités de base"), "b: OI unit"); }
        if (k === "c") { assert(await panel.getByTestId("pos-chart").count() === 0, "c: non-comparable not drawn"); assert(text.includes("CONTRACT_SIZES_DIFFER") || text.includes("Tailles de contrat différentes"), "c: reason"); }
        if (k === "d") { assert(await panel.getByTestId("pos-chart").count() === 0, "d: nothing drawn"); assert(text.includes("Aucune observation enregistrée"), "d: reason"); }
        shots.push(name + "-" + k);
        const label = theme + "-" + width + "-" + name + "-" + k;
        // The app skip link is fixed chrome outside the panel; keep it out of panel crops.
        await page.addStyleTag({ content: ".app-skip{display:none!important}" });
        await panel.screenshot({ path: path.join(out, label + ".png") });
      }
    }
    const geometry = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
    assert(geometry.scroll <= geometry.width + 1, name + "/" + width + ": no page overflow");
    if (name === "missing" || name === "invalid") await panel.screenshot({ path: path.join(out, theme + "-" + width + "-" + name + ".png") });
    views.push({ theme, width, name, shots, ...geometry });
    await context.close();
  }
  assert(!errors.length && !blocked.length, "no page errors or external/mutation requests");
  assert(requests.every(r => r.startsWith("GET /api/operator/v1/")), "GET-only artifact reads");
  await writeFile(path.join(out, "checks.json"), JSON.stringify({ disposition: "SOURCE_ONLY_SYNTHETIC_POSITIONING_UI_PASS", assertions, views, errors, blocked, requests: [...new Set(requests)], fixtures_used: true, sandbox: true, service_workers: "blocked", active_api_reached: false, server_started: false }, null, 2) + "\n");
  console.log("DERIVATIVES_POSITIONING_BROWSER_PASS", assertions, views.length);
} catch (error) { await writeFile(path.join(out, "checks.json"), JSON.stringify({ disposition: "SOURCE_ONLY_SYNTHETIC_POSITIONING_UI_FAIL", assertions, views, errors, blocked, error: String(error) }, null, 2) + "\n"); throw error; } finally { await browser.close(); }
