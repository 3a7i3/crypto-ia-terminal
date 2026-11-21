// Preuve visuelle locale du panneau Footprint (vue Microstructure).
// Vue unique BTC_USDT : arrivée directe dans Microstructure, tableau affiché dès la
// lecture de la capture figée, sans clic. Vérifie l'absence de défilement horizontal
// de PAGE, le thème clair/sombre, le plein écran et le fichier absent, puis le
// parcours Marché → Microstructure à 384 px.
// La capture lue est le rejeu MEXC RÉEL servi par le build
// (public/observations/footprint) ; aucune donnée synthétique n'est injectée.
// Le scénario « absent » remplace seulement la réponse par le repli HTML de la SPA.
// Les API sont simulées indisponibles (503) : la capture ne dépend pas de LMI.
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
      mention: document.querySelector('[data-testid="footprint-mention"]')?.textContent ?? null,
      tables: panel.querySelectorAll("table").length,
      contracts: panel.textContent.includes("contrats (source)") && panel.textContent.includes("quantités en contrats"),
      dltaDayPartial: panel.textContent.includes("DltaDay partiel"),
      oldModes: /Temps réel|Démo historique|Panneau non alimenté/.test(panel.textContent),
      controlsFit: [...panel.querySelectorAll("button, select")].every((el) => { const r = el.getBoundingClientRect(); return r.width === 0 || (r.left >= 0 && r.right <= doc.clientWidth); }) };
  });
}

// Requêtes externes ou temps réel : aucune n'est admise (le seul fichier lu est le rejeu statique).
const liveRequests = (requests) => requests.filter((u) => !u.startsWith(origin) || /^wss?:/.test(u) || /api\.mexc|contract\/deals|footprint\/(live|stream)/i.test(u));

try {
  for (const vp of viewports) {
    for (const scenario of ["clair", "sombre", "plein-ecran", "absent"]) {
      const { page, requests } = await open(vp, scenario);
      assert((await page.goto(`${base}/paper-live/market/lmi`, { waitUntil: "load" }))?.ok(), "navigation");
      const panel = page.getByTestId("footprint-panel");
      await panel.waitFor();
      // Aucun clic : le tableau (ou « Capture indisponible ») doit apparaître seul.
      await page.getByTestId(scenario === "absent" ? "footprint-capture-unavailable" : "footprint-table").waitFor();
      if (scenario === "sombre") await page.getByRole("combobox", { name: "Thème" }).selectOption("dark");
      if (scenario === "plein-ecran") await page.getByRole("button", { name: "Plein écran" }).click();
      await page.waitForTimeout(150);
      const m = await measure(page);
      const live = liveRequests(requests);
      const replayReads = requests.filter((u) => u.includes(REPLAY)).length;
      let ok = m.pageScrollWidth <= m.viewport && m.panelLeft >= 0 && m.panelRight <= m.viewport && live.length === 0
        && !m.oldModes && m.controlsFit && replayReads === 1;
      if (scenario === "absent") ok &&= m.tables === 0 && (await panel.textContent()).includes("Capture indisponible");
      else ok &&= m.tables === 1 && /^Capture figée · Couverture partielle$/.test((m.mention ?? "").trim()) && m.partialBadge && m.contracts
        && m.dltaDayPartial && /100 transactions/.test(m.coverage ?? "") && /\(15 s\)/.test(m.coverage ?? "");
      results.push({ ...m, viewport: vp.name, clientWidth: m.viewport, scenario, ok, replayReads, liveRequests: live });
      if (scenario !== "plein-ecran") await panel.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${out}/${vp.name}-${scenario}.png`, fullPage: scenario !== "plein-ecran" });
      await page.close();
    }
  }
  // Parcours exigé : Marché → Microstructure à 384 px, tableau affiché sans clic.
  {
    const vp = { name: "384x832-s24plus-parcours", width: 384, height: 832 };
    const { page, requests } = await open(vp, "path");
    assert((await page.goto(`${base}/`, { waitUntil: "load" }))?.ok(), "navigation accueil");
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
    await page.getByTestId("footprint-table").waitFor();
    await page.screenshot({ path: `${out}/parcours-3-microstructure.png`, fullPage: true });
    await page.waitForTimeout(150);
    const m = await measure(page);
    const live = liveRequests(requests);
    const ok = m.pageScrollWidth <= m.viewport && m.panelRight <= m.viewport && m.footprintBelowLmi === true && live.length === 0
      && m.partialBadge && m.contracts && m.dltaDayPartial && m.tables === 1 && !m.oldModes;
    results.push({ ...m, viewport: vp.name, clientWidth: m.viewport, scenario: "marche-microstructure-direct", ok, url: page.url(), liveRequests: live });
    await panel.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${out}/parcours-4-footprint-capture-cadre.png` });
    await page.close();
  }
  // Vue unique à 384 px (référence S24+) puis en desktop : tableau dès le chargement,
  // clair par défaut, sombre, plein écran ; même tableau partout, une seule lecture.
  for (const vp of [{ name: "384x832", width: 384, height: 832 }, { name: "1440x900", width: 1440, height: 900 }]) {
    const { page, requests } = await open(vp, "vue-unique");
    assert((await page.goto(`${base}/paper-live/market/lmi`, { waitUntil: "load" }))?.ok(), "navigation vue unique");
    const panel = page.getByTestId("footprint-panel");
    const table = page.getByTestId("footprint-table");
    await table.waitFor();
    const select = page.getByRole("combobox", { name: "Thème" });
    const themeOf = () => panel.getAttribute("data-footprint-theme");
    const tableHtml = () => table.innerHTML();
    const fits = () => page.evaluate(() => {
      const doc = document.documentElement; const panel = document.querySelector('[data-testid="footprint-panel"]');
      const inside = [...panel.querySelectorAll("button, select")].every((el) => { const r = el.getBoundingClientRect(); return r.width === 0 || (r.left >= 0 && r.right <= window.innerWidth && r.height >= 40); });
      return inside && doc.scrollWidth <= doc.clientWidth;
    });
    const replayReads = () => requests.filter((u) => u.includes(REPLAY)).length;
    const steps = {};
    steps.tableSansClic = true;
    steps.unSeulTableau = (await panel.locator("table").count()) === 1;
    steps.anciensModesRetires = !/Temps réel|Démo historique|Panneau non alimenté/.test(await panel.textContent()) && (await panel.getByRole("radio").count()) === 0;
    steps.mention = ((await page.getByTestId("footprint-mention").textContent()) ?? "").trim() === "Capture figée · Couverture partielle";
    steps.defaultClair = (await themeOf()) === "light" && (await select.locator("option:checked").textContent()) === "Clair";
    steps.options = JSON.stringify(await select.locator("option").allTextContents()) === JSON.stringify(["Clair", "Sombre"]);
    steps.besideFullscreen = await page.evaluate(() => {
      const next = document.querySelector('[data-testid="footprint-theme-select"]').closest("label").nextElementSibling;
      return next?.tagName === "BUTTON" && /Plein écran/.test(next.textContent);
    });
    steps.pleinEcranNonEtire = await page.evaluate(() => {
      const b = [...document.querySelectorAll('[data-testid="footprint-panel"] button')].find((x) => /Plein écran/.test(x.textContent));
      return b.getBoundingClientRect().width < 160;
    });
    steps.commandesTiennentClair = await fits();
    const reference = await tableHtml();
    await panel.scrollIntoViewIfNeeded();
    if (vp.width < 800) await page.screenshot({ path: `${out}/vue-unique-1-clair-384.png` });
    await select.focus();
    steps.focusVisible = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle !== "none");
    await select.selectOption({ label: "Sombre" });
    steps.sombre = (await themeOf()) === "dark";
    steps.memeTableauSombre = (await tableHtml()) === reference;
    steps.commandesTiennentSombre = await fits();
    await page.evaluate(() => document.activeElement?.blur());
    if (vp.width < 800) await page.screenshot({ path: `${out}/vue-unique-2-sombre-384.png` });
    await page.getByRole("button", { name: "Plein écran" }).click();
    await page.waitForTimeout(150);
    steps.pleinEcran = (await themeOf()) === "dark" && await page.evaluate(() => {
      const p = document.querySelector('[data-testid="footprint-panel"]');
      return p.classList.contains("footprint-fullscreen") || document.fullscreenElement === p;
    });
    steps.memeTableauPleinEcran = (await tableHtml()) === reference && (await panel.locator("table").count()) === 1;
    steps.commandesTiennentPleinEcran = await fits();
    if (vp.width < 800) await page.screenshot({ path: `${out}/vue-unique-3-plein-ecran-sombre-384.png` });
    await page.getByRole("button", { name: "Quitter le plein écran" }).click();
    await select.selectOption({ label: "Clair" });
    steps.retourClair = (await themeOf()) === "light" && (await tableHtml()) === reference;
    await page.waitForTimeout(150);
    steps.uneSeuleLecture = replayReads() === 1;
    steps.pasDeDebordement = await fits();
    const live = liveRequests(requests);
    steps.aucunFluxTempsReel = live.length === 0;
    const ok = Object.values(steps).every(Boolean);
    results.push({ viewport: vp.name, scenario: "vue-unique", ok, steps, liveRequests: live, requests: requests.filter((u) => !/\.(js|css|png|svg|webmanifest)$|\/$/.test(u)) });
    await page.close();
  }
} finally { await browser.close(); }
console.log(JSON.stringify(results, null, 1));
const bad = results.filter((r) => !r.ok);
assert(errors.length === 0, `Erreurs de page : ${errors.join(" | ")}`);
assert(bad.length === 0, `Contrôles en échec : ${bad.map((r) => `${r.viewport}/${r.scenario}`).join(", ")}`);
console.log(`FOOTPRINT_MOBILE_VISUAL_PASS ${results.length} captures`);
