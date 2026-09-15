import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.WEB01_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.WEB01_VISUAL_OUT_DIR || "artifacts";
const outPath = path.join(outDir, "web01-market.png");

await mkdir(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const response = await page.goto(baseUrl, { waitUntil: "networkidle" });
  if (!response || !response.ok()) {
    throw new Error(`frontend navigation failed: ${response?.status() ?? "no-response"}`);
  }

  await page.getByTestId("overview-view").waitFor({ state: "visible" });
  await page.getByTestId("tab-market").click();
  await page.getByTestId("market-view").waitFor({ state: "visible" });

  const marketText = await page.getByTestId("market-view").innerText();
  if (!marketText.includes("CryptoRadar")) throw new Error("CryptoRadar label missing from MarketView");
  if (!marketText.includes("BTC/USDT")) throw new Error("expected MARKET symbol missing from MarketView");
  if (!marketText.includes("OBSERVATIONAL_TELEMETRY")) {
    throw new Error("MARKET authority provenance missing from MarketView");
  }
  if (marketText.includes("NOT_EXPOSED")) throw new Error("MarketView still reports NOT_EXPOSED");
  for (const forbidden of ["Entry", "Stop Loss", "Take Profit"]) {
    if (marketText.includes(forbidden)) throw new Error(`forbidden execution presentation leaked: ${forbidden}`);
  }

  await page.screenshot({ path: outPath, fullPage: true });
  console.log(`WEB01_MARKET_VISUAL_PROOF=${outPath}`);
  console.log("WEB01_MARKET_VISUAL_ASSERTIONS=PASS");
} finally {
  await browser.close();
}
