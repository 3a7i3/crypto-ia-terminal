import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.WEB_DIR_D3_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.WEB_DIR_D3_VISUAL_OUT_DIR || "artifacts/web-dir-d3";
const desktopPath = path.join(outDir, "direction-desktop-1440.png");
const mobilePath = path.join(outDir, "direction-mobile-390.png");

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
  const apiRequests = [];
  const mutationRequests = [];

  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/") || url.pathname === "/healthz") {
      apiRequests.push(`${request.method()} ${url.pathname}`);
    }
    if (!["GET", "HEAD"].includes(request.method())) {
      mutationRequests.push(`${request.method()} ${url.pathname}`);
    }
  });

  const response = await page.goto(`${baseUrl}/direction`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Direction navigation failed: ${response?.status() ?? "no-response"}`);

  await page.getByTestId("direction-shell").waitFor({ state: "visible" });
  await page.getByTestId("direction-authority-strip").waitFor({ state: "visible" });

  const shellText = await page.getByTestId("direction-shell").innerText();
  for (const required of [
    "DIRECTION",
    "SURFACE PROPRIÉTAIRE",
    "Synthèse, gouvernance et décisions humaines",
    "PRÉSENTATION",
    "LECTURE SEULE",
    "AUCUNE AUTORITÉ PAPER",
    "ÉTAT GLOBAL · INCONNU",
  ]) {
    assert(shellText.includes(required), `D3 Direction evidence missing: ${required}`);
  }

  assert(
    (await page.getByText("NON DÉPLOYÉ", { exact: true }).count()) === 6,
    "Direction must expose exactly six honest NON DÉPLOYÉ capability cards",
  );
  assert(apiRequests.length === 0, `Direction unexpectedly requested runtime data: ${apiRequests.join(", ")}`);
  assert(mutationRequests.length === 0, `Direction issued mutation requests: ${mutationRequests.join(", ")}`);

  const returnControl = page.getByTestId("return-paper-live");
  const returnBox = await returnControl.boundingBox();
  assert(returnBox !== null && returnBox.height >= 44, "Direction return control is smaller than 44px");
  assert(await returnControl.getAttribute("href") === "/paper-live", "Direction return target is not /paper-live");

  await assertNoOverflow(page, "desktop");
  await page.screenshot({ path: desktopPath, fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(150);
  assert(await returnControl.isVisible(), "mobile Direction return control is not visible");
  assert(await page.getByTestId("direction-authority-strip").isVisible(), "mobile authority strip is not visible");
  const mobileReturnBox = await returnControl.boundingBox();
  assert(mobileReturnBox !== null && mobileReturnBox.height >= 44, "mobile return control is smaller than 44px");
  assert(mobileReturnBox !== null && mobileReturnBox.width <= 390, "mobile return control exceeds viewport");
  await assertNoOverflow(page, "mobile");
  await page.screenshot({ path: mobilePath, fullPage: true });

  console.log(`WEB_DIR_D3_VISUAL_DESKTOP=${desktopPath}`);
  console.log(`WEB_DIR_D3_VISUAL_MOBILE=${mobilePath}`);
  console.log("WEB_DIR_D3_NO_API_REQUESTS=PASS");
  console.log("WEB_DIR_D3_NO_MUTATION_REQUESTS=PASS");
  console.log("WEB_DIR_D3_VISUAL_ASSERTIONS=PASS");
} finally {
  await browser.close();
}
