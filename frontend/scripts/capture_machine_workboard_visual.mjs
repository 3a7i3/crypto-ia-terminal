import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";

const base = process.env.WORKBOARD_VISUAL_BASE_URL || "http://127.0.0.1:3018";
const out = process.env.WORKBOARD_VISUAL_OUT_DIR || "artifacts/machine-workboard";
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const checks = [];
try {
  for (const width of [1440, 820, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    const errors = [], api = [];
    page.on("pageerror", error => errors.push(String(error)));
    page.on("request", request => {
      if (new URL(request.url()).pathname.startsWith("/api/")) api.push(request.url());
    });
    await page.goto(`${base}/direction/travaux`, { waitUntil: "networkidle" });
    await page.getByTestId("machine-workboard").waitFor();
    if (await page.locator("tbody tr").count() !== 29) throw new Error("Register rows missing");
    if (!await page.getByText("U8 · non certifié", { exact: true }).isVisible()) throw new Error("Runtime scope missing");
    if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) throw new Error(`Page overflow at ${width}`);
    await page.screenshot({ path: `${out}/workboard-${width}.png` });
    if (width === 390 || width === 1440) {
      await page.getByRole("heading", { name: "Tableau des travaux" }).evaluate(element => element.scrollIntoView({ block: "start" }));
      await page.screenshot({ path: `${out}/workboard-table-${width}.png` });
    }
    await page.getByLabel("État", { exact: true }).selectOption("paused");
    if (await page.locator("tbody tr").count() !== 2) throw new Error("Pause filter failed");
    await page.getByRole("button", { name: "Réinitialiser" }).click();
    await page.getByLabel("Rechercher", { exact: true }).fill("durabilite de chaque");
    if (await page.locator("tbody tr").count() !== 1) throw new Error("Accent-insensitive search failed");
    await page.getByRole("button", { name: "Réinitialiser" }).click();
    if (api.length || errors.length) throw new Error(JSON.stringify({ api, errors }));
    checks.push({ width, rows: 29, page_overflow: false, api_requests: 0, page_errors: 0, filters: "PASS" });
    await page.close();
  }
  await writeFile(`${out}/checks.json`, JSON.stringify({ scope: "LOCAL_SOURCE_PRESENTATION_ONLY", checks }, null, 2));
} finally {
  await browser.close();
}
