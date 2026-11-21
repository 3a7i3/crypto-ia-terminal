import { createRequire } from "node:module";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const { chromium } = createRequire(import.meta.url)("playwright");
const here = path.dirname(fileURLToPath(import.meta.url)), root = path.resolve(here, "../dist");
const fixtures = process.env.CROSS_STACK_FIXTURES_DIR;
if (!fixtures) throw Error("CROSS_STACK_FIXTURES_DIR required; no fixture skips");
const out = path.resolve(here, "../artifacts/market-stress"), origin = "http://127.0.0.1:4173";
const read = async name => JSON.parse(await readFile(path.join(fixtures, name + ".json"), "utf8"));
const cases = [
  ["synthetic", await read("S_derivatives_stress")], ["stale", await read("S_derivatives_stress_stale")],
  ["partial", await read("S_derivatives_stress_partial")], ["unresolved", await read("S_derivatives_stress_unresolved")],
  ["missing", { http_status: 503, body: { error_code: "DERIVATIVES_STRESS_NOT_CONFIGURED" } }],
  ["invalid", { http_status: 200, body: { ...(await read("S_derivatives_stress")).body, execution_authority: true } }],
];
let assertions = 0; const views = [], errors = [], blocked = [], requests = [];
const assert = (ok, m) => { assertions++; if (!ok) throw Error(m); };
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true, chromiumSandbox: true });
try {
  for (const theme of ["light", "dark"]) for (const width of [1440, 768, 393]) for (const [name, fixture] of cases) for (const tab of ["venues", "flow"]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, locale: "fr-FR", serviceWorkers: "block" });
    await context.addInitScript(t => localStorage.setItem("crypto-terminal.theme", t), theme);
    await context.route("**/*", async route => {
      const q = route.request(), u = new URL(q.url());
      if (u.origin !== origin || !["GET", "HEAD"].includes(q.method())) { blocked.push(q.method() + " " + u.href); return route.abort(); }
      if (u.pathname.startsWith("/api/")) {
        requests.push(q.method() + " " + u.pathname);
        const f = u.pathname.endsWith("/derivatives-stress") ? fixture : { http_status: 503, body: { error_code: "SYNTHETIC_NOT_AVAILABLE" } };
        return route.fulfill({ status: f.http_status, contentType: "application/json", body: JSON.stringify(f.body) });
      }
      const target = q.isNavigationRequest() ? path.join(root, "index.html") : path.resolve(root, "." + u.pathname);
      assert(target.startsWith(root + path.sep), "static path remains in build");
      const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".webmanifest": "application/manifest+json" };
      return route.fulfill({ status: 200, contentType: mime[path.extname(target)] || "application/octet-stream", body: await readFile(target) });
    });
    const page = await context.newPage(); page.setDefaultTimeout(10000); page.on("pageerror", e => errors.push(String(e)));
    await page.goto(origin + "/paper-live/market/" + tab, { waitUntil: "networkidle" });
    const id = tab === "venues" ? "stress-panel" : "timing-panel", panel = page.getByTestId(id);
    await panel.waitFor();
    const text = await panel.innerText();
    if (name === "missing" || name === "invalid") {
      assert(/Aucune publication de (dérivés|périodicité) disponible/.test(text), name + ": unavailable is stated");
      assert(await panel.getByRole("table").count() === 0, name + ": unavailable is not an empty numeric table");
      assert((await panel.getByTestId("market-source-not-configured").count()) === (name === "missing" ? 1 : 0), name + ": unconfigured is distinct from a contract failure");
    } else if (tab === "venues") {
      assert(await panel.getByTestId("stress-synthetic").count() === 1, "synthetic evidence is stated");
      assert(await panel.getByTestId("stress-leg").count() === 4, name + ": every expected leg stays visible, even without observation");
      if (name === "synthetic") {
        assert(text.includes("12.997401") && text.includes("0.0001000000"), "exact published premium and funding");
        assert(/aucun score, seuil ni signal/.test(text), "no score claim");
        await panel.getByLabel("Sous-jacent observé", { exact: true }).selectOption({ index: 1 });
        assert((await panel.innerText()).includes("-0.0000500000"), "second underlying shows its own funding");
      }
      if (name === "stale") assert(text.includes("INCONNUES"), "stale is visible");
    } else {
      assert(await panel.getByTestId("timing-synthetic").count() === 1, "synthetic evidence is stated");
      if (name === "synthetic") {
        assert(await panel.getByTestId("timing-scan-row").count() === 7, "baseline and placebo beside every scan row");
        assert(await panel.getByRole("img").count() === 1, "folded histogram is exposed");
      }
    }
    const geometry = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
    assert(geometry.scroll <= geometry.width + 1, name + "/" + tab + "/" + width + ": no page overflow");
    const label = theme + "-" + width + "-" + tab + "-" + name;
    await panel.screenshot({ path: path.join(out, label + ".png") });
    views.push({ label, ...geometry });
    await context.close();
  }
  assert(!errors.length && !blocked.length, "no page errors or external/mutation requests");
  assert(requests.every(r => r.startsWith("GET /api/operator/v1/")), "GET-only artifact reads");
  await writeFile(path.join(out, "checks.json"), JSON.stringify({ disposition: "SOURCE_ONLY_SYNTHETIC_STRESS_UI_PASS", assertions, views, errors, blocked, requests: [...new Set(requests)], fixtures_used: true, sandbox: true, service_workers: "blocked", active_api_reached: false, server_started: false }, null, 2) + "\n");
  console.log("DERIVATIVES_STRESS_BROWSER_PASS", assertions, views.length);
} catch (error) { await writeFile(path.join(out, "checks.json"), JSON.stringify({ disposition: "SOURCE_ONLY_SYNTHETIC_STRESS_UI_FAIL", assertions, views, errors, blocked, error: String(error) }, null, 2) + "\n"); throw error; } finally { await browser.close(); }
