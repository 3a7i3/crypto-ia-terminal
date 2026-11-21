// Isolated PWA transition proof: Footprint V3-L1 dist -> current dist on the
// same loopback origin, through the real service worker. Static files only;
// /api/* answers 503 and is never proxied. No VPS, no exchange, no runtime.
import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const need = (name) => {
  if (!process.env[name]) throw Error(`${name} is required`);
  return path.resolve(process.env[name]);
};
const oldDist = need("FOOTPRINT_V3_DIST");
const newDist = need("FOOTPRINT_CURRENT_DIST");
const out = path.resolve(process.env.FOOTPRINT_SW_OUT_DIR || "artifacts/footprint-sw-transition");
fs.mkdirSync(out, { recursive: true });

const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const cacheName = (dist) => {
  const m = fs.readFileSync(path.join(dist, "sw.js"), "utf8").match(/SHELL_CACHE = `\$\{SHELL_CACHE_PREFIX\}([^`]+)`/);
  if (!m) throw Error(`cache name not found in ${dist}/sw.js`);
  return `crypto-ai-operator-shell-${m[1]}`;
};
const entryJs = (dist) => fs.readFileSync(path.join(dist, "index.html"), "utf8").match(/src="(\/assets\/[^"]+\.js)"/)[1];

const OLD = { dist: oldDist, cache: cacheName(oldDist), js: entryJs(oldDist), sw: sha(fs.readFileSync(path.join(oldDist, "sw.js"))) };
const NEW = { dist: newDist, cache: cacheName(newDist), js: entryJs(newDist), sw: sha(fs.readFileSync(path.join(newDist, "sw.js"))) };
if (OLD.cache === NEW.cache || OLD.js === NEW.js) throw Error("Les deux builds doivent différer (cache et bundle)");

let selected = OLD;
const requests = [];
const blocked = [];
const errors = [];
const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".json": "application/json", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml" };
const server = http.createServer((req, res) => {
  const u = new URL(req.url, "http://127.0.0.1");
  if (!["GET", "HEAD"].includes(req.method)) { res.writeHead(405); return res.end(); }
  requests.push({ path: u.pathname, release: selected === OLD ? "v3" : "current" });
  if (u.pathname.startsWith("/api/")) {
    res.writeHead(503, { "content-type": "application/json", "cache-control": "no-store" });
    return res.end('{"error_code":"SOURCE_NOT_DEPLOYED"}');
  }
  if (u.pathname === "/healthz") {
    res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
    return res.end('{"transport_ready":true}');
  }
  const root = selected.dist;
  let p = path.resolve(root, "." + u.pathname);
  if (!p.startsWith(root + path.sep) || !fs.existsSync(p) || !fs.statSync(p).isFile()) p = path.join(root, "index.html");
  res.writeHead(200, { "content-type": mime[path.extname(p)] || "application/octet-stream", "cache-control": "no-store" });
  res.end(req.method === "HEAD" ? undefined : fs.readFileSync(p));
});

const state = (page) => page.evaluate(async () => ({
  caches: (await caches.keys()).sort(),
  controller: navigator.serviceWorker.controller?.scriptURL ?? null,
  entry: [...document.querySelectorAll('script[type="module"][src]')].map((s) => new URL(s.src).pathname),
  chart: !!document.querySelector('[data-testid="footprint-chart"]'),
  profileHeader: document.querySelector('[data-testid="footprint-chart"] [data-profile]')?.textContent ?? null,
  liveStatus: document.querySelector('[data-testid="footprint-live-status"]')?.textContent ?? null,
  aggressorOrigin: !!document.querySelector('[data-testid="footprint-aggressor-origin"]'),
}));

(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  const result = { at_utc: new Date().toISOString(), scope: "LOCAL_LOOPBACK_V3_TO_CURRENT_SERVICE_WORKER", api_contacted: false, old: { cache: OLD.cache, entry: OLD.js, sw_sha256: OLD.sw }, current: { cache: NEW.cache, entry: NEW.js, sw_sha256: NEW.sw } };
  try {
    const context = await browser.newContext({ viewport: { width: 412, height: 915 }, serviceWorkers: "allow" });
    await context.route("**/*", (route) => {
      const req = route.request();
      const url = new URL(req.url());
      if (url.origin === base && ["GET", "HEAD"].includes(req.method())) return route.continue();
      blocked.push(req.url());
      return route.abort();
    });
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(String(e)));

    // 1. V3 installed: the production bundle registers its own worker.
    await page.goto(`${base}/paper-live/market/lmi`, { waitUntil: "load" });
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null, null, { timeout: 30000 });
    await page.getByTestId("footprint-chart").waitFor();
    await page.reload({ waitUntil: "load" });
    await page.getByTestId("footprint-chart").waitFor();
    const before = await state(page);
    result.before = before;
    if (!before.caches.includes(OLD.cache) || before.entry[0] !== OLD.js) throw Error(`V3 non établie : ${JSON.stringify(before)}`);
    if (before.liveStatus !== null) throw Error("La V3 ne devait pas avoir la ligne Temps réel");
    await page.screenshot({ path: path.join(out, "avant-v3.png") });

    // 2. Publish the current dist on the same origin. The open page must pick
    //    the new worker (update check), reload once and serve the new bundle.
    selected = NEW;
    await page.goto(`${base}/paper-live/market/lmi`, { waitUntil: "load" });
    await page.waitForFunction((name) => caches.keys().then((k) => k.includes(name)), NEW.cache, { timeout: 30000 });
    await page.waitForFunction((js) => [...document.querySelectorAll('script[type="module"][src]')].some((s) => new URL(s.src).pathname === js), NEW.js, { timeout: 30000 });
    await page.getByTestId("footprint-live-status").waitFor({ timeout: 30000 });
    await page.waitForFunction((old) => caches.keys().then((k) => !k.includes(old)), OLD.cache, { timeout: 30000 });
    const after = await state(page);
    result.after = after;
    const swNow = await (await context.request.get(`${base}/sw.js`)).body();
    const checks = {
      new_cache_present: after.caches.includes(NEW.cache),
      old_cache_deleted: !after.caches.includes(OLD.cache),
      new_entry_loaded: after.entry[0] === NEW.js,
      new_worker_served: sha(swNow) === NEW.sw,
      chart_rendered: after.chart,
      delta_profile_header: /Ask − Bid/.test(after.profileHeader ?? ""),
      live_unavailable_visible: /Temps réel indisponible/.test(after.liveStatus ?? ""),
      aggressor_origin_visible: after.aggressorOrigin,
    };
    // 3. Offline navigation must come from the new shell, not the V3 one.
    await context.setOffline(true);
    await page.reload({ waitUntil: "load" }).catch(() => {});
    const offline = await page.evaluate(() => [...document.querySelectorAll('script[type="module"][src]')].map((s) => new URL(s.src).pathname));
    checks.offline_shell_is_new = offline[0] === NEW.js;
    await context.setOffline(false);
    result.checks = checks;
    await page.screenshot({ path: path.join(out, "apres-graphique.png") });
    result.blocked = blocked;
    result.errors = errors;
    result.requests = requests.length;
    fs.writeFileSync(path.join(out, "FOOTPRINT_SW_TRANSITION.json"), JSON.stringify(result, null, 2) + "\n");
    console.log(JSON.stringify(result, null, 2));
    const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
    if (failed.length || blocked.length || errors.length) throw Error(`Échec : ${JSON.stringify({ failed, blocked, errors })}`);
    console.log("FOOTPRINT_SW_TRANSITION_PASS");
    await context.close();
  } finally {
    await browser.close();
    await new Promise((r) => server.close(r));
  }
})().catch((e) => { console.error(e); process.exitCode = 1; });
