import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.WEB01_VISUAL_BASE_URL || "http://127.0.0.1:3000";
const outDir = process.env.WEB01_VISUAL_OUT_DIR || "artifacts";
const desktopPath = path.join(outDir, "web01-market.png");
const tabletPath = path.join(outDir, "web01-market-tablet.png");
const mobilePath = path.join(outDir, "web01-market-mobile.png");
const shellDesktopPath = path.join(outDir, "web01-app-shell-desktop.png");
const shellMobilePath = path.join(outDir, "web01-app-shell-mobile.png");
// M1-C5 (EO-026, D3): CryptoRadar historique is withdrawn from the application
// (M1-C3). The real-path proof is kept on the CI-only legacy proof page, served
// by the same Vite dev server and therefore through the same loopback proxy to
// the Operator API on 127.0.0.1:8090 (GET /api/operator/v1/market). The
// application shell is checked separately on its actual Market route.
const LEGACY_PAGE = "/legacy-proof/market-scanner.html";

await mkdir(outDir, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function assertNoPageOverflow(page, label) {
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
  const marketResponses = [];
  page.on("response", (r) => { const u = new URL(r.url()); if (u.pathname === "/api/operator/v1/market") marketResponses.push({ origin: u.origin, method: r.request().method(), status: r.status() }); });
  const response = await page.goto(`${baseUrl}${LEGACY_PAGE}`, { waitUntil: "networkidle" });
  if (!response || !response.ok()) {
    throw new Error(`legacy proof navigation failed: ${response?.status() ?? "no-response"}`);
  }
  assert(await page.locator("html").getAttribute("data-proof") === "legacy-market-scanner", "legacy proof page not identified");
  assert((await page.getByTestId("legacy-proof-banner").innerText()).includes("composant legacy non exposé"), "legacy proof banner missing");

  await page.getByTestId("market-view").waitFor({ state: "visible" });
  // Real path: the browser read /market from the dev server origin (Vite proxy
  // to the loopback Operator API), GET only, HTTP 200 from the generated artifact.
  assert(marketResponses.length > 0 && marketResponses.every((r) => r.origin === new URL(baseUrl).origin && r.method === "GET" && r.status === 200), "MARKET not read through the local proxy: " + JSON.stringify(marketResponses));
  await page.getByTestId("market-opportunity-row").first().waitFor({ state: "visible" });

  await page.getByText("Provenance et dates des sources").click();
  const marketText = await page.getByTestId("market-view").innerText();
  assert(marketText.includes("CryptoRadar"), "CryptoRadar label missing from MarketView");
  assert(marketText.includes("BTC/USDT"), "expected MARKET symbol missing from MarketView");
  assert(
    marketText.includes("OBSERVATIONAL_TELEMETRY"),
    "MARKET authority provenance missing from MarketView",
  );
  assert(!marketText.includes("NOT_EXPOSED"), "MarketView still reports NOT_EXPOSED");
  assert(!/\bLIVE\b/.test(marketText), "generated artifact presented as LIVE");
  for (const forbidden of ["Entry", "Stop Loss", "Take Profit"]) {
    assert(!marketText.includes(forbidden), `forbidden execution presentation leaked: ${forbidden}`);
  }

  // Desktop — four summary cards in one row and full table visible.
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

  await assertNoPageOverflow(page, "desktop");
  await page.screenshot({ path: desktopPath, fullPage: true });

  // Tablet — stats become a 2x2 grid while the desktop table remains usable
  // inside its own horizontal scroller, never forcing page-level overflow.
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.waitForTimeout(100);
  const tabletBoxes = [];
  for (let i = 0; i < 4; i += 1) {
    const box = await statCards.nth(i).boundingBox();
    assert(box !== null, `tablet MARKET stat card ${i} has no layout box`);
    tabletBoxes.push(box);
  }
  assert(Math.abs(tabletBoxes[0].y - tabletBoxes[1].y) <= 2, "tablet first stat row is not aligned");
  assert(Math.abs(tabletBoxes[2].y - tabletBoxes[3].y) <= 2, "tablet second stat row is not aligned");
  assert(tabletBoxes[2].y > tabletBoxes[0].y + 20, "tablet stats did not form two rows");
  assert(await page.locator(".market-table-desktop").isVisible(), "desktop MARKET table should remain visible at tablet width");
  await assertNoPageOverflow(page, "tablet");
  await page.screenshot({ path: tabletPath, fullPage: true });

  // Phone — table is replaced by cards carrying the same already-exposed
  // values. Navigation may scroll internally, but the page itself must not.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(100);
  assert(await page.locator(".market-table-desktop").isVisible(), "compact MARKET table must remain visible at phone width");
  const mobileCards = page.getByTestId("market-opportunity-row");
  assert((await mobileCards.count()) > 0, "phone MARKET opportunity cards are missing");
  assert(await mobileCards.first().isVisible(), "first phone MARKET opportunity card is not visible");
  const mobileCardText = (await mobileCards.first().innerText()).toLowerCase();
  for (const expected of ["btc/usdt", "acheteur", "100%"]) {
    assert(mobileCardText.includes(expected), `phone MARKET card missing ${expected}`);
  }
  for (const label of ["Symbole", "Score moyen", "Score maximal", "Dominance", "Signaux", "Régime"]) assert((await tableHeaders.allTextContents()).includes(label), `mobile table missing column ${label}`);
  const freshnessBox = await page.getByTestId("market-freshness").boundingBox();
  assert(freshnessBox !== null && freshnessBox.y < 844, "phone freshness state is not visible above the initial fold");
  await assertNoPageOverflow(page, "phone");
  await page.screenshot({ path: mobilePath, fullPage: true });

  // Application shell on the actual Market route (Radar Spot by default): the
  // Market module tab keeps usable spacing and the phone navigation fits.
  const app = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const appResponse = await app.goto(`${baseUrl}/paper-live/market`, { waitUntil: "networkidle" });
  assert(appResponse?.ok(), "application Market navigation failed");
  await app.waitForURL(/\/paper-live\/market\/radar$/);
  await app.getByTestId("market-workspace").waitFor();
  assert(await app.getByTestId("market-view").count() === 0, "CryptoRadar historique mounted in the application");
  const activeMarketTab = await app.getByTestId("tab-market").boundingBox();
  assert(activeMarketTab !== null && activeMarketTab.width >= 65, "MARKET nav tab lacks usable spacing");
  await assertNoPageOverflow(app, "app desktop");
  await app.screenshot({ path: shellDesktopPath, fullPage: true });
  await app.setViewportSize({ width: 390, height: 844 });
  await app.waitForTimeout(100);
  const navBox = await app.locator(".app-topbar").boundingBox();
  assert(navBox !== null && navBox.width <= 390, "phone navigation exceeds viewport width");
  await assertNoPageOverflow(app, "app phone");
  await app.screenshot({ path: shellMobilePath, fullPage: true });

  console.log(`WEB01_MARKET_VISUAL_PROOF_DESKTOP=${desktopPath}`);
  console.log(`WEB01_MARKET_VISUAL_PROOF_TABLET=${tabletPath}`);
  console.log(`WEB01_MARKET_VISUAL_PROOF_MOBILE=${mobilePath}`);
  console.log(`WEB01_APP_SHELL_PROOF=${shellDesktopPath},${shellMobilePath}`);
  console.log("WEB01_MARKET_REAL_PROXY_8090_LEGACY_PROOF_PAGE=PASS");
  console.log("WEB01_MARKET_VISUAL_ASSERTIONS=PASS");
} finally {
  await browser.close();
}
