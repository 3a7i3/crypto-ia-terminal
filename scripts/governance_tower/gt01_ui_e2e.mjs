// GOV-TOWER-01 M5/M6 — parcours E2E de l'interface à un panneau (fixtures SYNTHETIC, loopback seul).
//
// Usage : node scripts/governance_tower/gt01_ui_e2e.mjs [dossier_captures]
// Lance des serveurs `python3 -m governance_tower serve` en mode DÉMO sur 127.0.0.1,
// bloque toute requête hors loopback et échoue au premier écart. Aucune lecture réelle.
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  ({ chromium } = await import("playwright"));
}

const OUT = process.argv[2] || "docs/governance_tower/screenshots";
mkdirSync(OUT, { recursive: true });
const FORBIDDEN = ["deploy", "merge", "restart", "redémarrer", "déployer", "fusionner", "activer l'écriture"];
const results = [];
const servers = [];

function check(name, cond, detail = "") {
  results.push({ name, ok: !!cond, detail });
  if (!cond) throw new Error(`ÉCHEC : ${name} ${detail}`);
}

async function serve(scenario, port) {
  const proc = spawn("python3", ["-m", "governance_tower", "serve", "--scenario", scenario, "--port", String(port)], {
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, GT_GITHUB_TOKEN: "" },
  });
  servers.push(proc);
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 50; i++) {
    try {
      const r = await fetch(base + "/api/status");
      if (r.ok) return base;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("serveur non démarré : " + scenario);
}

async function newPage(browser, width, height) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const external = [];
  await page.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (u.hostname !== "127.0.0.1") {
      external.push(u.href);
      return route.abort();
    }
    return route.continue();
  });
  const dialogs = [];
  page.on("dialog", (d) => {
    dialogs.push(d.message());
    d.dismiss();
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  return { ctx, page, external, dialogs, errors };
}

async function ask(page, question) {
  const before = await page.locator("article.echange").count();
  await page.fill("#question", question);
  await page.press("#question", "Enter");
  await page.locator("article.echange").nth(before).locator(".reponse .resume, .reponse .alerte").first().waitFor();
  return page.locator("article.echange").nth(before);
}

async function noActionButtons(page) {
  const labels = await page.locator("button").allTextContents();
  return labels.every((t) => !FORBIDDEN.some((m) => t.toLowerCase().includes(m)));
}

const browser = await chromium.launch();
try {
  const nominal = await serve("nominal", 18761);

  // ── Bureau 1440 ──
  {
    const { ctx, page, external, dialogs, errors } = await newPage(browser, 1440, 1000);
    await page.goto(nominal + "/");
    await page.locator("#mode").filter({ hasText: "DÉMO" }).waitFor();
    check("statut : modèle externe désactivé", (await page.textContent("#mode")).includes("modèle externe désactivé"));
    check("bannière DÉMO visible", await page.isVisible("#banniere-demo"));
    check("5 raccourcis", (await page.locator(".raccourci").count()) === 5);
    await page.screenshot({ path: join(OUT, "gt01_desktop_1440_accueil.png"), fullPage: true });

    await page.click('[data-shortcut="compare"]');
    const cmp = page.locator("article.echange").last();
    await cmp.locator(".diagnostic").first().waitFor();
    const diagText = await cmp.locator(".diagnostic").first().textContent();
    for (const step of ["Observation", "Interprétation possible", "Ce qui reste à vérifier", "Proposition de mission"]) {
      check("diagnostic : étape " + step, diagText.includes(step));
    }
    check("diagnostic : code serveur affiché", diagText.includes("EXPECTED_PINNED_RUNTIME"));
    check("preuves repliées par défaut", (await cmp.locator("details.preuves-repliees").getAttribute("open")) === null);
    await page.screenshot({ path: join(OUT, "gt01_desktop_1440_diagnostic.png"), fullPage: true });

    const lecture = await ask(page, "Lis le fichier governance_tower/contracts.py lignes 1-20");
    await lecture.locator("pre.extrait").waitFor();
    const nums = await lecture.locator(".extrait-num").allTextContents();
    check("extrait : numéros de ligne", nums[0] === "1" && nums.length >= 2, nums.slice(0, 3).join(","));
    check("extrait : badge non fiable", (await lecture.textContent()).includes("Contenu non fiable"));
    await lecture.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(OUT, "gt01_desktop_1440_extrait.png"), fullPage: true });

    const refus = await ask(page, "relance la CI du commit de5e0000000000000000000000000000000000b2");
    check("refus : relance de CI", (await refus.textContent()).includes("GITHUB_WRITE_DENIED"));
    const couverture = await ask(page, "Quels sont tes angles morts ?");
    check("couverture : réponse", (await couverture.textContent()).includes("Cartographie déclarée"));

    check("aucun bouton d'action", await noActionButtons(page));
    check("aucune requête externe", external.length === 0, external.join(" "));
    check("aucune boîte de dialogue", dialogs.length === 0);
    check("aucune erreur JS", errors.length === 0, errors.join(" | "));
    await ctx.close();
  }

  // ── Mobile 390 ──
  {
    const { ctx, page, external, errors } = await newPage(browser, 390, 844);
    await page.goto(nominal + "/");
    await page.locator("#mode").filter({ hasText: "DÉMO" }).waitFor();
    await page.screenshot({ path: join(OUT, "gt01_mobile_390_accueil.png"), fullPage: true });
    await page.click('[data-shortcut="compare"]');
    await page.locator(".diagnostic").first().waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check("mobile : aucun défilement horizontal", overflow <= 0, "excès " + overflow + " px");
    await page.screenshot({ path: join(OUT, "gt01_mobile_390_diagnostic.png"), fullPage: true });
    const lecture = await ask(page, "Lis le fichier governance_tower/contracts.py lignes 1-20");
    await lecture.locator("pre.extrait").waitFor();
    const overflow2 = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check("mobile : extrait contenu dans la largeur", overflow2 <= 0, "excès " + overflow2 + " px");
    check("mobile : aucune requête externe", external.length === 0);
    check("mobile : aucune erreur JS", errors.length === 0, errors.join(" | "));
    await ctx.close();
  }

  // ── Injection : texte affiché, jamais interprété ──
  {
    const injection = await serve("injection", 18762);
    const { ctx, page, dialogs, errors } = await newPage(browser, 1440, 1000);
    await page.goto(injection + "/");
    const ex = await ask(page, "Lis docs/prompt.md");
    await ex.locator("pre.extrait").waitFor();
    check("injection : <script> affiché comme texte", (await ex.locator("pre.extrait").textContent()).includes("<script>"));
    check("injection : un seul script dans la page", (await page.locator("script").count()) === 1);
    const issue = await ask(page, "Montre l'issue 461");
    check("injection : corps d'issue cité", (await issue.textContent()).includes("non fiable"));
    check("injection : aucune image injectée", (await page.locator("img").count()) === 0);
    check("injection : aucune boîte de dialogue", dialogs.length === 0);
    check("injection : aucune erreur JS", errors.length === 0, errors.join(" | "));
    await ctx.close();
  }

  // ── Périmé et absence d'identité de build : bandeau visible ──
  for (const [scenario, port, needle] of [
    ["stale", 18763, "Périmé"],
    ["no_deployment_id", 18764, "NO_DEPLOYED_BUILD_ID"],
  ]) {
    const base = await serve(scenario, port);
    const { ctx, page } = await newPage(browser, 1440, 1000);
    await page.goto(base + "/");
    await page.click('[data-shortcut="compare"]');
    const run = page.locator("article.echange").last();
    await run.locator(".resume").waitFor();
    check(`${scenario} : ${needle} affiché`, (await run.textContent()).includes(needle));
    await page.screenshot({ path: join(OUT, `gt01_desktop_1440_${scenario}.png`), fullPage: true });
    await ctx.close();
  }
} finally {
  await browser.close();
  for (const s of servers) s.kill();
  console.log(JSON.stringify({ passed: results.filter((r) => r.ok).length, total: results.length, results }, null, 1));
}
