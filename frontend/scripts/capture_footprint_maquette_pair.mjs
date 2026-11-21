// Paire de captures au même cadrage (émulation Playwright, paysage 832 × 384, plein écran) :
//  - rejeu MEXC M5 réel, thème Clair, servi par `vite preview` (build de production) ;
//  - fixture SYNTHETIC 20 bougies, thème Sombre, banc du serveur de développement.
// Les deux vues sont déplacées à la dernière bougie et centrées verticalement sur le POC
// volume, puis la zone du graphique est capturée avec la même taille.
// Usage : npx vite preview --port 4173 & npx vite --port 5174 & node scripts/capture_footprint_maquette_pair.mjs
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";

const preview = process.env.FOOTPRINT_VISUAL_BASE_URL || "http://127.0.0.1:4173";
const dev = process.env.FOOTPRINT_SYNTHETIC_BASE_URL || "http://127.0.0.1:5174";
const out = process.env.FOOTPRINT_PAIR_OUT_DIR || "artifacts/footprint-maquette";
await mkdir(out, { recursive: true });
const viewport = { width: 832, height: 384 };
const browser = await chromium.launch();
const errors = [];
const frame = async (page) => {
  const scroller = page.getByTestId("footprint-chart-scroll");
  await scroller.scrollIntoViewIfNeeded();
  await scroller.evaluate((el) => {
    el.scrollLeft = el.scrollWidth;
    const poc = el.querySelector('.fp-profile-track[data-poc="true"]');
    const row = poc.getBoundingClientRect(), box = el.getBoundingClientRect();
    el.scrollTop += row.top - box.top - (box.height - 100) / 2;
  });
  await page.evaluate(() => document.activeElement?.blur());
  return scroller;
};
const shots = [];
try {
  const m5 = await browser.newPage({ viewport, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  m5.on("pageerror", (e) => errors.push(`m5: ${e}`));
  await m5.goto(`${preview}/paper-live/market/lmi`, { waitUntil: "load" });
  await m5.getByTestId("footprint-chart").waitFor();
  await m5.getByRole("combobox", { name: "Thème" }).selectOption("light");
  await m5.getByRole("button", { name: "Plein écran" }).click();
  await m5.waitForTimeout(250);
  const a = await frame(m5);
  shots.push({ name: "maquette-rejeu-m5-clair-832x384.png", box: await a.boundingBox(), source: "rejeu MEXC BTC_USDT M5 (capture historique partielle)" });
  await a.screenshot({ path: `${out}/${shots[0].name}` });

  const syn = await browser.newPage({ viewport, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  syn.on("pageerror", (e) => errors.push(`syn: ${e}`));
  await syn.goto(`${dev}/test-harness/footprint-chart.html?theme=dark&plein-ecran=1`, { waitUntil: "load" });
  await syn.getByTestId("footprint-chart").waitFor();
  const b = await frame(syn);
  shots.push({ name: "maquette-synthetic-20-bougies-sombre-832x384.png", box: await b.boundingBox(), source: "fixture SYNTHETIC 20 bougies M1 (test uniquement)" });
  await b.screenshot({ path: `${out}/${shots[1].name}` });
} finally { await browser.close(); }
const same = Math.abs(shots[0].box.width - shots[1].box.width) <= 1 && Math.abs(shots[0].box.height - shots[1].box.height) <= 1;
const report = { viewport, emulation: "Playwright Chromium, isMobile, deviceScaleFactor 2 ; pas un appareil physique", shots, memeCadrage: same, errors };
await writeFile(`${out}/MAQUETTE_PAIR.json`, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));
if (!same || errors.length) { console.error("Cadrages différents ou erreurs de page"); process.exit(1); }
console.log("FOOTPRINT_MAQUETTE_PAIR_PASS");
