// Vérification locale de la version candidate Footprint + Finance V6.
// Sert dist/ avec le VRAI serveur web01 (comme sur crypto-restore-01), un
// StateDirectory temporaire pour l'historique PAPER, et une fausse Operator API
// sur 127.0.0.1:8090 (FIN02 seulement ; tout le reste répond 503).
// Aucune donnée de marché n'est inventée : les fichiers d'observation et le
// rejeu MEXC sont ceux du build. Prouve la présence des six fonctions exigées.
import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { startPaperBalanceHistory } from "./paper-balance-history.mjs";
import { createServer, OPERATOR_API_TARGET } from "./web01_local_frontend_server.mjs";

const out = process.env.RC_VERIFY_OUT_DIR || "artifacts/rc-preservation";
const PORT = Number(process.env.RC_VERIFY_PORT || 4181);
const DAY = 86_400_000;
const EPOCH = "PAPER-RC-VERIFY";
const EXPECTED = {
  "/observations/footprint/mexc-btc_usdt-perp-replay-v1.json": "a41c608814c02a10e5a9369b11806196b770ad578db0d5037368413c4cce391f",
  "/observations/btc-atom-book-v1.json": "0488e8390645d429a60fb43ae6adfe5a8fa4d1a31b43c538ff5e729d78f47bfe",
};
const assert = (ok, message) => { if (!ok) throw new Error(message); };
const hex = (n) => n.toString(16).padStart(64, "0");
const listen = (server, port, host = "127.0.0.1") => new Promise((resolve, reject) => server.once("error", reject).listen(port, host, resolve));

await mkdir(out, { recursive: true });
const now = Date.now();
const state = await mkdtemp(path.join(tmpdir(), "cat-paper-balance-"));
await writeFile(path.join(state, "observations.json"), JSON.stringify([20, 3, 0.5].map((d, i) => ({ at: now - d * DAY, value: 10_000 + i * 25, id: hex(i + 1), epoch: EPOCH }))));
const api = http.createServer((req, res) => {
  if (req.url === "/api/operator/v1/financial-reconciliation") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ product: "FIN02FinancialCockpit", authority: "FINANCIAL_OBSERVATION", asset: "USDT", paper_epoch_id: EPOCH,
      financial_snapshot_id: hex(77), generated_at_utc: new Date(Date.now() - 5000).toISOString(), freshness_classification: "FRESH", financial: { cash_available: "10090.00" } }));
  }
  res.writeHead(503, { "content-type": "application/json" }); res.end('{"error_code":"SOURCE_NOT_DEPLOYED"}');
});
await listen(api, Number(new URL(OPERATOR_API_TARGET).port));
const web = createServer({ port: PORT, balanceHistory: startPaperBalanceHistory(state, OPERATOR_API_TARGET) });
await listen(web, PORT);
const base = `http://127.0.0.1:${PORT}`;

const results = []; const errors = [];
const browser = await chromium.launch();
const check = (name, ok, detail = {}) => { results.push({ name, ok: !!ok, ...detail }); };
try {
  for (const [file, sha] of Object.entries(EXPECTED)) {
    const res = await fetch(base + file);
    const digest = createHash("sha256").update(Buffer.from(await res.arrayBuffer())).digest("hex");
    check(`fichier servi ${file}`, res.ok && /json/.test(res.headers.get("content-type") ?? "") && digest === sha, { digest });
  }
  for (const vp of [{ name: "384", width: 384, height: 832 }, { name: "1440", width: 1440, height: 900 }]) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height }, isMobile: vp.width < 800, hasTouch: vp.width < 800 });
    const external = [];
    page.on("pageerror", (e) => errors.push(`${vp.name}: ${e}`));
    page.on("request", (r) => { if (!r.url().startsWith(base)) external.push(r.url()); });
    // GitHub : pas de réseau sortant pendant la vérification ; l'état « indisponible » reste affiché.
    await page.route("https://api.github.com/**", (route) => route.fulfill({ status: 503, body: "{}" }));
    const noHScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    const shot = (n) => page.screenshot({ path: `${out}/${vp.name}-${n}.png`, fullPage: true });

    await page.goto(`${base}/paper-live/finance`, { waitUntil: "load" });
    const chart = page.getByRole("region", { name: "Solde PAPER disponible" });
    await chart.waitFor();
    const counts = {};
    for (const d of [1, 7, 30]) {
      await chart.getByRole("button", { name: `${d} j` }).click();
      const img = chart.getByRole("img", { name: new RegExp(`sur ${d} jour`) });
      await img.waitFor();
      counts[d] = Number((await img.getAttribute("aria-label")).match(/(\d+) point/)[1]);
    }
    check(`${vp.name} solde PAPER 1/7/30 j`, counts[1] === 2 && counts[7] === 3 && counts[30] === 4 && await noHScroll(), { counts });
    await shot("finance-solde-30j");

    await page.goto(`${base}/paper-live/decisions`, { waitUntil: "load" });
    check(`${vp.name} tableau des décisions`, await page.getByRole("region", { name: "Tableau des décisions" }).isVisible() && await noHScroll());
    await shot("decisions");

    await page.goto(`${base}/paper-live/portfolio`, { waitUntil: "load" });
    check(`${vp.name} tableau des ordres en attente`, await page.getByRole("region", { name: "Tableau des ordres en attente" }).isVisible() && await noHScroll());
    await shot("positions-ordres");

    await page.goto(`${base}/paper-live/market/flow`, { waitUntil: "load" });
    await page.getByRole("heading", { name: "Flux de carnet · historique" }).waitFor();
    const bookTable = page.getByRole("region", { name: "Observations par plateforme" });
    await page.getByText("Capture historique · BTC/USDT").waitFor();
    const btc = await bookTable.textContent();
    await page.getByLabel("Instrument de la capture").selectOption("ATOM");
    await page.getByText("Capture historique · ATOM/USDT").waitFor();
    const atom = await bookTable.textContent();
    check(`${vp.name} observation carnet BTC/ATOM`, /60 \/ 60/.test(btc) && /90 \/ 90/.test(atom) && await noHScroll());
    await shot("flux-carnet");

    await page.goto(`${base}/paper-live/market/radar?product=spot-radar`, { waitUntil: "load" });
    await page.getByRole("button", { name: "Composite historique" }).click();
    await page.getByRole("region", { name: "Composite historique BBO Spot" }).waitFor();
    check(`${vp.name} aperçu BBO historique`, await noHScroll());
    await shot("bbo-historique");

    await page.goto(`${base}/direction/travaux`, { waitUntil: "load" });
    check(`${vp.name} Workboard synchronisation GitHub`, await page.getByRole("heading", { name: "Synchronisation GitHub" }).isVisible() && await noHScroll(), { url: page.url() });
    await shot("workboard");

    const footprintRequests = [];
    page.on("request", (r) => { if (/footprint/i.test(r.url())) footprintRequests.push(r.url()); });
    await page.goto(`${base}/paper-live/market/lmi`, { waitUntil: "load" });
    const panel = page.getByTestId("footprint-panel");
    await panel.waitFor();
    const unfed = (await panel.textContent()).includes("Panneau non alimenté") && footprintRequests.length === 0;
    await page.getByRole("radio", { name: "Démo historique" }).click();
    await page.getByTestId("footprint-table").waitFor();
    const text = await panel.textContent();
    check(`${vp.name} Footprint (non alimenté puis rejeu MEXC réel)`, unfed && /100 transactions/.test(text) && /contrats \(source\)/.test(text)
      && /COUVERTURE PARTIELLE/.test(text) && /DltaDay partiel/.test(text) && await noHScroll(), { footprintRequests });
    await shot("footprint-demo");
    check(`${vp.name} aucune requête externe`, external.filter((u) => !u.startsWith("https://api.github.com/")).length === 0, { external });
    await page.close();
  }
} finally { await browser.close(); web.close(); api.close(); }
console.log(JSON.stringify(results, null, 1));
assert(errors.length === 0, `Erreurs de page : ${errors.join(" | ")}`);
const bad = results.filter((r) => !r.ok);
assert(bad.length === 0, `Contrôles en échec : ${bad.map((r) => r.name).join(", ")}`);
console.log(`RC_PRESERVATION_PASS ${results.length} contrôles`);
process.exit(0);
