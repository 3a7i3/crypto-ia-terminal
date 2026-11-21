// Production-build proof: retired Market routes are silent and lead to Scanner.
import { chromium } from "playwright";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../dist");
const out = path.resolve(root, "../artifacts/market-retirement");
const origin = "http://127.0.0.1:4173";
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
let assertions = 0;
const assert = (ok, message) => { assertions++; if (!ok) throw Error(message); };
try {
  for (const width of [384, 1440]) for (const theme of ["light", "dark"]) {
    const context = await browser.newContext({ viewport: { width, height: 832 }, serviceWorkers: "block" });
    await context.addInitScript(value => localStorage.setItem("crypto-terminal.theme", value), theme);
    const requests = [], errors = [];
    await context.route("**/*", async route => {
      const request = route.request(), url = new URL(request.url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname.startsWith("/api/")) {
        requests.push(url.pathname);
        return route.fulfill({ status: 503, contentType: "application/json", body: '{"error_code":"SOURCE_NOT_CONFIGURED"}' });
      }
      const target = request.isNavigationRequest() ? path.join(root, "index.html") : path.resolve(root, "." + url.pathname);
      assert(target.startsWith(root + path.sep), "static path outside dist");
      const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".webmanifest": "application/manifest+json" };
      return route.fulfill({ status: 200, contentType: mime[path.extname(target)] || "application/octet-stream", body: await readFile(target) });
    });
    const page = await context.newPage();
    page.on("pageerror", e => errors.push(String(e)));
    for (const old of ["flow", "venues"]) {
      requests.length = 0;
      await page.goto(`${origin}/paper-live/market/${old}`);
      await page.waitForURL(`${origin}/paper-live/market/radar`);
      assert(await page.getByRole("tab", { name: "Scanner" }).count() === 1, "Scanner missing");
      assert(await page.getByRole("tab", { name: "Microstructure" }).count() === 1, "Microstructure missing");
      assert(await page.getByRole("tab").count() === 2, "retired Market tab still visible");
      assert(!requests.some(u => /market-flow|venue-comparison|derivatives-stress|derivatives-positioning/.test(u)), "retired source requested");
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "horizontal overflow");
    }
    await page.goto(`${origin}/paper-live/finance`);
    assert(await page.getByTestId("tab-finance").innerText() === "Wallet", "Wallet navigation missing");
    assert(await page.getByRole("heading", { name: "Wallet" }).count() === 1, "Wallet heading missing");
    assert(errors.length === 0, `page errors: ${errors.join(" | ")}`);
    await page.screenshot({ path: path.join(out, `${theme}-${width}-wallet.png`), fullPage: true });
    await context.close();
  }
} finally { await browser.close(); }
console.log(`MARKET_RETIREMENT_VISUAL_PASS ${assertions} assertions`);
