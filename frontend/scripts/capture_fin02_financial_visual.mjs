import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.FIN02_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.FIN02_VISUAL_OUT_DIR || "artifacts";
await mkdir(outDir, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function noPageOverflow(page, label) {
  const g = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(
    g.scrollWidth <= g.clientWidth + 1,
    label + " page overflow: " + g.scrollWidth + " > " + g.clientWidth,
  );
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const response = await page.goto(baseUrl, { waitUntil: "networkidle" });
  assert(response?.ok(), "frontend navigation failed");

  await page.getByTestId("overview-view").waitFor({ state: "visible" });
  await page.getByTestId("tab-finance").click();
  await page.getByTestId("financial-reconciliation-view").waitFor({ state: "visible" });
  await page
    .getByRole("heading", { name: "Financial Truth", exact: true })
    .waitFor({ state: "visible" });

  const text = await page.getByTestId("financial-reconciliation-view").innerText();
  for (const required of [
    "Financial Truth",
    "DIVERGENT",
    "UNAVAILABLE",
    "Unreconciled capital",
    "1",
    "no auto-correction",
  ]) {
    assert(text.includes(required), "FIN-02 visual evidence missing: " + required);
  }

  assert(
    (await page.getByTestId("fin-reconciliation-row").count()) > 0,
    "FIN-02 reconciliation rows missing",
  );
  await noPageOverflow(page, "desktop");
  await page.screenshot({
    path: path.join(outDir, "fin02-financial-desktop.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 820, height: 1180 });
  await page.waitForTimeout(100);
  await noPageOverflow(page, "tablet");
  await page.screenshot({
    path: path.join(outDir, "fin02-financial-tablet.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(100);
  const nav = await page.locator(".operator-nav").boundingBox();
  assert(nav !== null && nav.width <= 390, "mobile navigation exceeds viewport");
  await noPageOverflow(page, "mobile");
  await page.screenshot({
    path: path.join(outDir, "fin02-financial-mobile.png"),
    fullPage: true,
  });

  console.log("FIN02_FINANCIAL_VISUAL_ASSERTIONS=PASS");
} finally {
  await browser.close();
}
