import { chromium } from "playwright";
import { mkdir, readFile } from "node:fs/promises";
import assert from "node:assert/strict";

const base = "http://127.0.0.1:3000";
const out = "artifacts/market-flux-3b";
const corpus = ".cross-stack-fixtures/F_flux_corpus/bodies";
const native = await readFile(`${corpus}/native_base.body`, "utf8");
const partial = JSON.parse(native);
assert(partial.bars.some(bar => bar.delta_status === "PARTIAL_UNKNOWN_SIDE"));
assert(partial.bars.some(bar => bar.status === "SESSION_BREAK_UNRESOLVED"));
const scenarios = [
  { id: "exact", body: await readFile(`${corpus}/native_ns_30_digits.body`, "utf8"), status: 200, text: "Démonstration synthétique" },
  { id: "base", body: native, status: 200, text: "Démonstration synthétique" },
  { id: "no-snapshot", body: await readFile(`${corpus}/native_no_snapshot.body`, "utf8"), status: 200, text: "NO_SNAPSHOT" },
  { id: "not-found", body: '{"detail":"Not Found"}', status: 404, text: "HTTP 404" },
  { id: "unconfigured", body: '{"error_code":"MARKET_FLOW_NOT_CONFIGURED"}', status: 503, text: "MARKET_FLOW_NOT_CONFIGURED" },
  { id: "invalid", body: '{}', status: 200, text: "CONTRACT_INVALID" },
  { id: "network", text: "NETWORK" },
];
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
try {
  for (const [width, theme] of [[390, "dark"], [390, "light"], [1440, "dark"], [1440, "light"]]) {
    for (const scenario of scenarios) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, colorScheme: theme });
      const errors = [];
      let requests = 0;
      page.on("pageerror", error => errors.push(error.message));
      await page.route("**/*", async route => {
        const url = new URL(route.request().url());
        if (url.origin !== base) return route.abort();
        if (url.pathname === "/api/operator/v1/market-flow") {
          assert.equal(route.request().method(), "GET");
          requests++;
          if (scenario.id === "network") return route.abort();
          return route.fulfill({ status: scenario.status, contentType: "application/json", body: scenario.body });
        }
        if (url.pathname.startsWith("/api/")) return route.fulfill({ status: 503, body: "{}" });
        return route.continue();
      });
      try {
        await page.goto(`${base}/paper-live/market`);
        const tabs = page.getByRole("tab");
        assert.equal(await tabs.count(), 3);
        assert.equal(requests, 0);
        await tabs.first().focus();
        await page.keyboard.press("End");
        assert.equal(await tabs.last().getAttribute("aria-selected"), "true");
        const flux = page.getByRole("region", { name: "Flux", exact: true });
        if (scenario.id === "no-snapshot") await flux.getByText("Carnet · meilleurs prix", { exact: true }).click();
        await flux.getByText(scenario.text, { exact: false }).last().waitFor();
        if (scenario.id === "base") {
          await flux.getByText("Prix, delta et CVD", { exact: true }).click();
          await flux.getByText("Heatmap des quantités affichées", { exact: true }).click();
          await flux.getByRole("img", { name: /CVD par barre/ }).waitFor();
          await flux.getByText(/PARTIAL_UNKNOWN_SIDE/).first().waitFor();
          await flux.getByText(/SESSION_BREAK_UNRESOLVED/).first().waitFor();
          await flux.getByRole("region", { name: "Achats", exact: true }).waitFor();

        }
        if (scenario.id === "exact") {
          await flux.getByText(new RegExp("Coupe " + JSON.parse(scenario.body).as_of_receipt_ns + " ns")).waitFor();
        }
        if (scenario.id === "no-snapshot") {
          await flux.getByText("Heatmap des quantités affichées", { exact: true }).click();
          await flux.locator('[data-flux-cell="unknown"]').first().waitFor();
        }
        assert.equal(requests, 1);
        assert.deepEqual(errors, []);
        assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "Débordement horizontal de la page");
        await page.screenshot({ path: `${out}/${scenario.id}-${width}-${theme}.png`, fullPage: true });
      } finally {
        await page.close();
      }
    }
  }
} finally {
  await browser.close();
}
