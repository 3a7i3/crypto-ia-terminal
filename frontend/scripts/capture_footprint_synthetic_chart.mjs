// Banc SYNTHETIC : 20 bougies M1 (fixture de test, aucune donnée réelle) rendues par
// FootprintChart via le serveur de développement Vite. Vérifie les espacements et les
// alignements à 384, 412, 832 × 384 (paysage) et 1440 px, en clair et en sombre.
// Usage : npx vite --port 5174 --strictPort & ; node scripts/capture_footprint_synthetic_chart.mjs
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const base = process.env.FOOTPRINT_SYNTHETIC_BASE_URL || "http://127.0.0.1:5174";
const out = process.env.FOOTPRINT_VISUAL_OUT_DIR || "artifacts/footprint-mobile";
const assert = (ok, message) => { if (!ok) throw new Error(message); };
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
const results = []; const errors = [];
try {
  for (const vp of [{ name: "384x832", width: 384, height: 832 }, { name: "412x915", width: 412, height: 915 },
    { name: "832x384-paysage", width: 832, height: 384 }, { name: "1440x900", width: 1440, height: 900 }]) {
    for (const theme of ["light", "dark"]) {
      const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1, isMobile: vp.width < 1000, hasTouch: vp.width < 1000 });
      page.on("pageerror", (e) => errors.push(`${vp.name}/${theme}: ${e}`));
      await page.goto(`${base}/test-harness/footprint-chart.html?theme=${theme}`, { waitUntil: "load" });
      await page.getByTestId("footprint-chart").waitFor();
      const m = await page.evaluate(() => {
        const doc = document.documentElement;
        const scroller = document.querySelector('[data-testid="footprint-chart-scroll"]');
        const grid = scroller.querySelector(".fp-chart-grid");
        const near = (a, b) => Math.abs(a - b) <= 1;
        const cells = [...grid.querySelectorAll(".fp-chart-cell")];
        const firstRow = cells.filter((c) => c.dataset.idx === cells[0].dataset.idx);
        const rowTops = cells.filter((c, i) => i === 0 || c.dataset.idx !== cells[i - 1].dataset.idx).map((c) => c.getBoundingClientRect().top);
        const profTops = [...grid.querySelectorAll(".fp-profile-track")].map((e) => e.getBoundingClientRect().top);
        const statsAligned = ["DeltaChg", "Delta", "DltaDay", "Volume", "UTC"].every((label) => {
          const s = [...grid.querySelectorAll(`strong.fp-stat[data-stat="${label}"]`)];
          return s.length === 20 && s.every((e, i) => near(e.getBoundingClientRect().left, firstRow[i].getBoundingClientRect().left) && near(e.getBoundingClientRect().width, firstRow[i].getBoundingClientRect().width));
        });
        const widths = firstRow.map((c) => Math.round(c.getBoundingClientRect().width));
        const sr = scroller.getBoundingClientRect();
        scroller.scrollLeft = scroller.scrollWidth;
        const axisAfter = grid.querySelector("b.fp-price[data-idx]").getBoundingClientRect().left;
        const profAfter = grid.querySelector(".fp-profile-track").getBoundingClientRect().right;
        const lastCellRight = firstRow.at(-1).getBoundingClientRect().right;
        const ok = {
          vingtColonnes: firstRow.length === 20,
          pasDeDebordementPage: doc.scrollWidth <= doc.clientWidth,
          profilAligneSurPrix: rowTops.length === profTops.length && rowTops.every((t, i) => near(t, profTops[i])),
          statistiquesSousBougies: statsAligned,
          espacementRegulier: Math.max(...widths) - Math.min(...widths) <= 1 && Math.min(...widths) >= 82,
          axeVisibleApresDeplacement: axisAfter >= sr.left - 1,
          profilVisibleApresDeplacement: profAfter <= sr.right + 1,
          derniereBougieAtteignable: lastCellRight <= axisAfter + 1,
          banniereSynthetic: document.querySelector('[data-testid="synthetic-banner"]').textContent.startsWith("SYNTHETIC"),
        };
        scroller.scrollLeft = 0;
        return { ok, widths: [Math.min(...widths), Math.max(...widths)], scrollWidth: scroller.scrollWidth, clientWidth: scroller.clientWidth };
      });
      results.push({ viewport: vp.name, theme, ...m, pass: Object.values(m.ok).every(Boolean) });
      await page.screenshot({ path: `${out}/synthetic-20-bougies-${theme === "light" ? "clair" : "sombre"}-${vp.name}.png` });
      await page.close();
    }
  }
} finally { await browser.close(); }
console.log(JSON.stringify(results, null, 1));
assert(errors.length === 0, `Erreurs de page : ${errors.join(" | ")}`);
const bad = results.filter((r) => !r.pass);
assert(bad.length === 0, `Contrôles en échec : ${bad.map((r) => `${r.viewport}/${r.theme}`).join(", ")}`);
console.log(`FOOTPRINT_SYNTHETIC_CHART_PASS ${results.length} captures`);
