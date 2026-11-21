// Preuve visuelle locale du panneau Footprint (vue Microstructure).
// Vérifie l'absence de défilement horizontal de PAGE aux largeurs mobiles et
// capture les états : non alimenté, démo historique (clair/sombre), plein écran,
// fichier absent, et le parcours Marché → Microstructure à 384 px.
// La démo historique lit le rejeu MEXC RÉEL servi par le build
// (public/observations/footprint) ; aucune donnée synthétique n'est injectée.
// Le scénario « absent » remplace seulement la réponse par le repli HTML de la SPA.
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";

const base = process.env.FOOTPRINT_VISUAL_BASE_URL || "http://127.0.0.1:4173";
const out = process.env.FOOTPRINT_VISUAL_OUT_DIR || "artifacts/footprint-mobile";
const REPLAY = "/observations/footprint/mexc-btc_usdt-perp-replay-v1.json";
const REPLAY_SHA256 = "a41c608814c02a10e5a9369b11806196b770ad578db0d5037368413c4cce391f";
const assert = (ok, message) => { if (!ok) throw new Error(message); };

const viewports = [
  { name: "360x800", width: 360, height: 800 }, { name: "384x832-s24plus", width: 384, height: 832 },
  { name: "390x844", width: 390, height: 844 }, { name: "412x915", width: 412, height: 915 },
  { name: "832x384-paysage", width: 832, height: 384 }, { name: "1440x900", width: 1440, height: 900 },
];
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const results = []; const errors = [];
const origin = new URL(base).origin;

// Le fichier servi par le build doit être exactement le rejeu attendu.
{
  const page = await browser.newPage();
  const res = await page.request.get(`${base}${REPLAY}`);
  assert(res.ok() && /json/.test(res.headers()["content-type"] ?? ""), `rejeu non servi en JSON : ${res.status()} ${res.headers()["content-type"]}`);
  const digest = createHash("sha256").update(await res.body()).digest("hex");
  assert(digest === REPLAY_SHA256, `SHA-256 du rejeu servi ${digest} ≠ ${REPLAY_SHA256}`);
  await page.close();
}

async function open(vp, scenario) {
  const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1, isMobile: vp.width < 800, hasTouch: vp.width < 800 });
  const requests = [];
  page.on("pageerror", (e) => errors.push(`${vp.name}/${scenario}: ${e}`));
  page.on("request", (r) => requests.push(r.url()));
  await page.route("**/api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"error_code":"SOURCE_NOT_DEPLOYED"}' }));
  if (scenario === "absent") await page.route(`**${REPLAY}`, (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>SPA</title>" }));
  return { page, requests };
}

async function measure(page) {
  return page.evaluate(() => {
    const doc = document.documentElement; const scroller = document.querySelector('[data-testid="footprint-scroll"]');
    const panel = document.querySelector('[data-testid="footprint-panel"]');
    const p = panel.getBoundingClientRect();
    const lmi = document.querySelector('[data-testid="market-panel"]')?.firstElementChild?.getBoundingClientRect();
    return { pageScrollWidth: doc.scrollWidth, viewport: doc.clientWidth, panelRight: Math.round(p.right), panelLeft: Math.round(p.left),
      footprintBelowLmi: lmi ? Math.round(p.top) >= Math.round(lmi.top) : null,
      tableScrollWidth: scroller?.scrollWidth ?? null, tableClientWidth: scroller?.clientWidth ?? null,
      theme: panel.dataset.footprintTheme,
      coverage: document.querySelector('[data-testid="footprint-coverage"]')?.textContent ?? null,
      partialBadge: !!document.querySelector('[data-testid="footprint-partial"]'),
      contracts: panel.textContent.includes("contrats (source)"),
      dltaDayPartial: panel.textContent.includes("DltaDay partiel"),
      unfed: panel.textContent.includes("Panneau non alimenté") };
  });
}

// Requêtes externes ou temps réel : aucune n'est admise (le seul fichier lu est le rejeu statique).
const liveRequests = (requests) => requests.filter((u) => !u.startsWith(origin) || /^wss?:/.test(u) || /api\.mexc|contract\/deals|footprint\/(live|stream)/i.test(u));

try {
  for (const vp of viewports) {
    for (const scenario of ["unfed", "demo", "demo-dark", "fullscreen", "absent"]) {
      const { page, requests } = await open(vp, scenario);
      assert((await page.goto(`${base}/paper-live/market/lmi`, { waitUntil: "networkidle" }))?.ok(), "navigation");
      const panel = page.getByTestId("footprint-panel");
      await panel.waitFor();
      if (scenario !== "unfed") {
        await page.getByRole("radio", { name: "Démo historique" }).click();
        await page.getByTestId(scenario === "absent" ? "footprint-replay-absent" : "footprint-table").waitFor();
      }
      if (scenario === "demo-dark") await page.getByRole("combobox", { name: "Thème" }).selectOption("dark");
      if (scenario === "fullscreen") await page.getByRole("button", { name: "Plein écran" }).click();
      await page.waitForTimeout(150);
      const m = await measure(page);
      const live = liveRequests(requests);
      const replayRead = requests.some((u) => u.includes(REPLAY));
      let ok = m.pageScrollWidth <= m.viewport && m.panelLeft >= 0 && m.panelRight <= m.viewport && live.length === 0;
      if (scenario === "unfed") ok &&= m.unfed && !replayRead;
      if (scenario === "demo") ok &&= m.partialBadge && m.contracts && m.dltaDayPartial && /100 transactions/.test(m.coverage ?? "") && /15 s/.test(m.coverage ?? "");
      results.push({ ...m, viewport: vp.name, clientWidth: m.viewport, scenario, ok, replayRead, liveRequests: live });
      if (scenario !== "fullscreen") await panel.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${out}/${vp.name}-${scenario}.png`, fullPage: scenario !== "fullscreen" });
      await page.close();
    }
  }
  // Parcours exigé : Marché → Microstructure à 384 px, Démo historique avec le rejeu réel.
  {
    const vp = { name: "384x832-s24plus-parcours", width: 384, height: 832 };
    const { page, requests } = await open(vp, "path");
    assert((await page.goto(`${base}/`, { waitUntil: "networkidle" }))?.ok(), "navigation accueil");
    await page.screenshot({ path: `${out}/parcours-1-accueil.png` });
    const toggle = page.locator(".mobile-menu-toggle");
    if (await toggle.isVisible()) await toggle.click();
    await page.getByTestId("tab-market").first().click();
    await page.getByTestId("market-workspace").waitFor();
    await page.screenshot({ path: `${out}/parcours-2-marche.png` });
    await page.getByTestId("market-tab-lmi").click();
    await page.waitForURL("**/paper-live/market/lmi");
    const panel = page.getByTestId("footprint-panel");
    await panel.waitFor();
    await page.screenshot({ path: `${out}/parcours-3-microstructure.png`, fullPage: true });
    await page.getByRole("radio", { name: "Démo historique" }).click();
    await page.getByTestId("footprint-table").waitFor();
    await page.waitForTimeout(150);
    const m = await measure(page);
    const live = liveRequests(requests);
    const ok = m.pageScrollWidth <= m.viewport && m.panelRight <= m.viewport && m.footprintBelowLmi === true && live.length === 0
      && m.partialBadge && m.contracts && m.dltaDayPartial;
    results.push({ ...m, viewport: vp.name, clientWidth: m.viewport, scenario: "marche-microstructure-demo", ok, url: page.url(), liveRequests: live });
    await page.screenshot({ path: `${out}/parcours-4-footprint-demo-reelle.png`, fullPage: true });
    await panel.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${out}/parcours-5-footprint-demo-reelle-cadre.png` });
    await page.close();
  }
  // Menu « Thème » à 384 px (référence S24+) puis en desktop : clair par défaut, sombre,
  // retour clair, plein écran aller-retour, changement de mode ; aucune requête de marché.
  for (const vp of [{ name: "384x832", width: 384, height: 832 }, { name: "1440x900", width: 1440, height: 900 }]) {
    const { page, requests } = await open(vp, "theme");
    assert((await page.goto(`${base}/paper-live/market/lmi`, { waitUntil: "networkidle" }))?.ok(), "navigation thème");
    const panel = page.getByTestId("footprint-panel");
    await panel.waitFor();
    const select = page.getByRole("combobox", { name: "Thème" });
    const themeOf = () => panel.getAttribute("data-footprint-theme");
    const visible = () => page.evaluate(() => {
      const r = document.querySelector('[data-testid="footprint-theme-select"]').getBoundingClientRect();
      const doc = document.documentElement;
      return r.left >= 0 && r.right <= doc.clientWidth && r.width > 0 && r.height >= 40 && doc.scrollWidth <= doc.clientWidth;
    });
    const before = requests.length;
    const steps = {};
    steps.defaultClair = (await themeOf()) === "light" && (await select.inputValue()) === "light"
      && (await select.locator("option:checked").textContent()) === "Clair";
    steps.options = JSON.stringify(await select.locator("option").allTextContents()) === JSON.stringify(["Clair", "Sombre"]);
    steps.besideFullscreen = await page.evaluate(() => {
      const sel = document.querySelector('[data-testid="footprint-theme-select"]').closest("label");
      const next = sel.nextElementSibling;
      return next?.tagName === "BUTTON" && /Plein écran/.test(next.textContent);
    });
    steps.visibleClair = await visible();
    await panel.scrollIntoViewIfNeeded();
    if (vp.width < 800) await page.screenshot({ path: `${out}/theme-1-clair-384.png` });
    // Menu ouvert : le popup natif n'apparaît pas dans une capture headless ; la liste
    // est déployée dans le DOM (attribut size) pour la seule capture, puis rétablie.
    await select.focus();
    steps.focusVisible = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle !== "none");
    if (vp.width < 800) {
      await page.evaluate(() => { const s = document.querySelector('[data-testid="footprint-theme-select"]'); s.size = 2; s.style.height = "auto"; });
      await page.screenshot({ path: `${out}/theme-2-menu-ouvert-384.png` });
      await page.evaluate(() => { const s = document.querySelector('[data-testid="footprint-theme-select"]'); s.removeAttribute("size"); s.style.height = ""; });
    }
    await select.selectOption({ label: "Sombre" });
    steps.sombre = (await themeOf()) === "dark" && (await select.locator("option:checked").textContent()) === "Sombre";
    steps.visibleSombre = await visible();
    if (vp.width < 800) await page.screenshot({ path: `${out}/theme-3-sombre-384.png` });
    await select.selectOption({ label: "Clair" });
    steps.retourClair = (await themeOf()) === "light";
    await select.selectOption({ label: "Sombre" });
    await page.getByRole("button", { name: "Plein écran" }).click();
    steps.pleinEcranSombre = (await themeOf()) === "dark" && await page.evaluate(() => {
      const p = document.querySelector('[data-testid="footprint-panel"]');
      return p.classList.contains("footprint-fullscreen") || document.fullscreenElement === p;
    });
    steps.selectVisiblePleinEcran = await page.evaluate(() => {
      const r = document.querySelector('[data-testid="footprint-theme-select"]').getBoundingClientRect();
      return r.left >= 0 && r.right <= window.innerWidth && r.height >= 40;
    });
    await page.getByRole("button", { name: "Quitter le plein écran" }).click();
    steps.sortiePleinEcranSombre = (await themeOf()) === "dark";
    steps.aucuneRequeteTempsReel = requests.length === before && (await panel.textContent()).includes("Panneau non alimenté");
    await page.getByRole("radio", { name: "Démo historique" }).click();
    await page.getByTestId("footprint-table").waitFor();
    const demo = await panel.textContent();
    steps.demoSombre = (await themeOf()) === "dark" && /COUVERTURE PARTIELLE/.test(demo) && /100 transactions/.test(demo);
    const afterDemo = requests.length;
    await select.selectOption({ label: "Clair" });
    await page.waitForTimeout(150);
    steps.themeSansRequeteEnDemo = requests.length === afterDemo && (await themeOf()) === "light";
    await page.getByRole("radio", { name: "Temps réel" }).click();
    steps.retourTempsReel = (await panel.textContent()).includes("Panneau non alimenté") && (await select.inputValue()) === "light";
    steps.pasDeDebordement = await visible();
    const live = liveRequests(requests);
    const ok = Object.values(steps).every(Boolean) && live.length === 0;
    results.push({ viewport: vp.name, scenario: "theme-select", ok, steps, liveRequests: live, requests: requests.filter((u) => !/\.(js|css|png|webmanifest)$|\/$/.test(u)) });
    await page.close();
  }
} finally { await browser.close(); }
console.log(JSON.stringify(results, null, 1));
const bad = results.filter((r) => !r.ok);
assert(errors.length === 0, `Erreurs de page : ${errors.join(" | ")}`);
assert(bad.length === 0, `Contrôles en échec : ${bad.map((r) => `${r.viewport}/${r.scenario}`).join(", ")}`);
console.log(`FOOTPRINT_MOBILE_VISUAL_PASS ${results.length} captures`);
