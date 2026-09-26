import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.WEB02_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.WEB02_VISUAL_OUT_DIR || "artifacts";
const desktopPath = path.join(outDir, "web02-ppl-desktop.png");
const tabletPath = path.join(outDir, "web02-ppl-tablet.png");
const mobilePath = path.join(outDir, "web02-ppl-mobile.png");

await mkdir(outDir, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function assertNoOverflow(page, label) {
  const geometry = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(
    geometry.scrollWidth <= geometry.clientWidth + 1,
    `${label} page overflows horizontally: ${geometry.scrollWidth}px > ${geometry.clientWidth}px`,
  );
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const response = await page.goto(baseUrl, { waitUntil: "networkidle" });
  assert(response?.ok(), `frontend navigation failed: ${response?.status() ?? "no-response"}`);

  await page.getByTestId("overview-view").waitFor({ state: "visible" });
  await page.getByTestId("tab-paper").click();
  await page.getByTestId("tab-ppl").click();
  await page.getByTestId("ppl-comparison-view").waitFor({ state: "visible" });
  await page.getByTestId("ppl-comparison-row").first().waitFor({ state: "visible" });

  const text = await page.getByTestId("ppl-comparison-view").innerText();
  for (const required of [
    "Legacy PAPER",
    "PPL",
    "PAPER_AUTHORITY",
    "NONE",
    "OBSERVATIONAL_TELEMETRY",
    "99.99",
    "100",
    "DIFFERENT",
  ]) {
    assert(text.includes(required), `WEB-02 evidence missing: ${required}`);
  }
  assert(!text.includes("NOT_EXPOSED"), "PPL comparator still reports NOT_EXPOSED");
  assert(
    text.includes("Raw source values") || text.includes("Raw"),
    "raw-value doctrine is not visible",
  );

  // Desktop: evidence summary is a single six-card row and full table is visible.
  const metrics = page.locator(".ppl-metric");
  assert((await metrics.count()) === 6, "expected six WEB-02 summary metrics");
  const desktopBoxes = [];
  for (let i = 0; i < 6; i += 1) {
    const box = await metrics.nth(i).boundingBox();
    assert(box !== null, `desktop metric ${i} missing layout box`);
    desktopBoxes.push(box);
  }
  const firstY = desktopBoxes[0].y;
  assert(
    desktopBoxes.every((box) => Math.abs(box.y - firstY) <= 2),
    "desktop WEB-02 metrics are not aligned on one row",
  );
  assert(await page.locator(".ppl-table-wrap").first().isVisible(), "desktop comparison table hidden");
  await assertNoOverflow(page, "desktop");
  await page.screenshot({ path: desktopPath, fullPage: true });

  // Tablet: summary becomes 3x2, table remains in its bounded horizontal scroller.
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.waitForTimeout(100);
  const tabletBoxes = [];
  for (let i = 0; i < 6; i += 1) {
    const box = await metrics.nth(i).boundingBox();
    assert(box !== null, `tablet metric ${i} missing layout box`);
    tabletBoxes.push(box);
  }
  assert(Math.abs(tabletBoxes[0].y - tabletBoxes[1].y) <= 2, "tablet first metric row misaligned");
  assert(tabletBoxes[3].y > tabletBoxes[0].y + 20, "tablet metrics did not wrap");
  await assertNoOverflow(page, "tablet");
  await page.screenshot({ path: tabletPath, fullPage: true });

  // Phone: comparison table is replaced by cards with the same producer values.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(100);
  assert(!(await page.locator(".ppl-table-wrap").first().isVisible()), "phone table should be hidden");
  const cards = page.locator(".ppl-comparison-card");
  assert((await cards.count()) > 0, "phone comparison cards missing");
  const cardText = await cards.first().innerText();
  assert(cardText.includes("Legacy"), "phone card lacks Legacy raw side");
  assert(cardText.includes("PPL"), "phone card lacks PPL raw side");
  assert(cardText.includes("DIFFERENT"), "phone card lacks relation");
  const navBox = await page.locator(".operator-nav").boundingBox();
  assert(navBox !== null && navBox.width <= 390, "phone navigation exceeds viewport");
  await assertNoOverflow(page, "phone");
  await page.screenshot({ path: mobilePath, fullPage: true });

  console.log(`WEB02_PPL_VISUAL_DESKTOP=${desktopPath}`);
  console.log(`WEB02_PPL_VISUAL_TABLET=${tabletPath}`);
  console.log(`WEB02_PPL_VISUAL_MOBILE=${mobilePath}`);
  console.log("WEB02_PPL_VISUAL_ASSERTIONS=PASS");
} finally {
  await browser.close();
}
