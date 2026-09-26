import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.WEB_RL_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.WEB_RL_VISUAL_OUT_DIR || "artifacts";
const desktopPath = path.join(outDir, "web-rl-research-desktop.png");
const mobilePath = path.join(outDir, "web-rl-research-mobile.png");

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
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const response = await page.goto(baseUrl, { waitUntil: "networkidle" });
  assert(response?.ok(), `frontend navigation failed: ${response?.status() ?? "no-response"}`);

  await page.getByTestId("overview-view").waitFor({ state: "visible" });
  await page.getByTestId("tab-research").click();
  await page.getByTestId("research-lab-view").waitFor({ state: "visible" });
  await page.getByTestId("research-domain-banner").waitFor({ state: "visible" });

  const text = await page.getByTestId("research-lab-view").innerText();
  for (const required of [
    "RESEARCH LAB",
    "NON-AUTHORITATIVE",
    "RESEARCH_NON_AUTHORITATIVE",
    "LOW_SAMPLE",
    "NOT_AVAILABLE",
    "No certified time-series/annualized return basis.",
    "No substantive candidate",
  ]) {
    assert(text.includes(required), `WEB-RL evidence missing: ${required}`);
  }

  const metricLabels = await page.locator(".research-metric-label").allTextContents();
  assert(
    metricLabels.includes("annualized_sharpe"),
    "WEB-RL evidence missing metric label: annualized_sharpe",
  );

  assert(
    (await page.getByTestId("research-metric-card").count()) >= 5,
    "expected governed Research metric cards",
  );
  assert(
    (await page.getByTestId("research-candidate-card").count()) === 0,
    "fixture must not fabricate a candidate",
  );

  await assertNoOverflow(page, "desktop");
  await page.screenshot({ path: desktopPath, fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(150);
  assert(
    await page.getByTestId("research-domain-banner").isVisible(),
    "mobile Research domain banner is not visible",
  );
  assert(
    await page.getByTestId("research-candidate-empty").isVisible(),
    "mobile empty candidate state is not visible",
  );
  const navBox = await page.locator(".operator-nav").boundingBox();
  assert(navBox !== null && navBox.width <= 390, "mobile navigation exceeds viewport");
  await assertNoOverflow(page, "mobile");
  await page.screenshot({ path: mobilePath, fullPage: true });

  console.log(`WEB_RL_VISUAL_DESKTOP=${desktopPath}`);
  console.log(`WEB_RL_VISUAL_MOBILE=${mobilePath}`);
  console.log("WEB_RL_VISUAL_ASSERTIONS=PASS");
} finally {
  await browser.close();
}
