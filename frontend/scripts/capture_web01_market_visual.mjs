import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.WEB01_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.WEB01_VISUAL_OUT_DIR || "artifacts";
const outPath = path.join(outDir, "web01-market.png");

await mkdir(outDir, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

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
  assert(marketText.includes("CryptoRadar"), "CryptoRadar label missing from MarketView");
  assert(marketText.includes("BTC/USDT"), "expected MARKET symbol missing from MarketView");
  assert(
    marketText.includes("OBSERVATIONAL_TELEMETRY"),
    "MARKET authority provenance missing from MarketView",
  );
  assert(!marketText.includes("NOT_EXPOSED"), "MarketView still reports NOT_EXPOSED");
  for (const forbidden of ["Entry", "Stop Loss", "Take Profit"]) {
    assert(!marketText.includes(forbidden), `forbidden execution presentation leaked: ${forbidden}`);
  }

  // Geometry assertions turn the screenshot into an executable visual gate.
  // At the certified 1440px viewport the four stat cards must form one row,
  // not collapse into the pre-fix unstyled vertical stack.
  const statCards = page.locator(".market-stat");
  assert((await statCards.count()) === 4, "expected exactly four MARKET stat cards");
  const statBoxes = [];
  for (let i = 0; i < 4; i += 1) {
    const box = await statCards.nth(i).boundingBox();
    assert(box !== null, `MARKET stat card ${i} has no layout box`);
    statBoxes.push(box);
  }
  const firstY = statBoxes[0].y;
  assert(statBoxes.every((box) => Math.abs(box.y - firstY) <= 2), "MARKET stat cards are not aligned on one row");
  assert(statBoxes.every((box) => box.width >= 200), "MARKET stat cards are too narrow at desktop viewport");
  for (let i = 1; i < statBoxes.length; i += 1) {
    assert(statBoxes[i].x - (statBoxes[i - 1].x + statBoxes[i - 1].width) >= 7, "MARKET stat card gap collapsed");
  }

  const tableHeaders = page.locator(".market-table th");
  assert((await tableHeaders.count()) === 7, "expected seven MARKET table columns");
  const headerBoxes = [];
  for (let i = 0; i < 7; i += 1) {
    const box = await tableHeaders.nth(i).boundingBox();
    assert(box !== null, `MARKET table header ${i} has no layout box`);
    headerBoxes.push(box);
  }
  for (let i = 1; i < headerBoxes.length; i += 1) {
    assert(headerBoxes[i].x > headerBoxes[i - 1].x + 25, "MARKET table columns visually collapsed");
  }

  const activeMarketTab = await page.getByTestId("tab-market").boundingBox();
  assert(activeMarketTab !== null && activeMarketTab.width >= 65, "MARKET nav tab lacks usable spacing");

  await page.screenshot({ path: outPath, fullPage: true });
  console.log(`WEB01_MARKET_VISUAL_PROOF=${outPath}`);
  console.log("WEB01_MARKET_VISUAL_ASSERTIONS=PASS");
} finally {
  await browser.close();
}
