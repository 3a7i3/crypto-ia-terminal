// Node-native contract for the persistent PAPER balance history (Finance V6).
// Proves the 1/7/30-day periods, the 30-day retention, persistence across a
// restart (StateDirectory file), epoch isolation and the GET-only route.
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { startPaperBalanceHistory } from "./paper-balance-history.mjs";
import { createServer } from "./web01_local_frontend_server.mjs";

const DAY = 86_400_000;
const EPOCH = "PAPER-TEST-EPOCH";
const listen = (server) => new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
const close = (server) => new Promise((resolve) => server.close(resolve));
const hex = (n) => n.toString(16).padStart(64, "0");

function fakeFin02(value) {
  return http.createServer((req, res) => {
    assert.equal(req.method, "GET");
    assert.equal(req.url, "/api/operator/v1/financial-reconciliation");
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      product: "FIN02FinancialCockpit", authority: "FINANCIAL_OBSERVATION", asset: "USDT",
      paper_epoch_id: EPOCH, financial_snapshot_id: hex(999), generated_at_utc: new Date(Date.now() - 1000).toISOString(),
      freshness_classification: "FRESH", financial: { cash_available: value },
    }));
  });
}

async function waitFor(read, predicate) {
  for (let i = 0; i < 100; i += 1) { const v = read(); if (predicate(v)) return v; await new Promise((r) => setTimeout(r, 20)); }
  throw new Error("timeout");
}

test("keeps 1/7/30-day periods, prunes beyond 30 days and survives a restart", async (t) => {
  const dir = await mkdtemp(path.join(tmpdir(), "paper-balance-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const now = Date.now();
  // Saved history: 40, 20, 5 and 0.5 days old, plus a point from another epoch.
  const saved = [40, 20, 5, 0.5].map((d, i) => ({ at: now - d * DAY, value: 1000 + i, id: hex(i + 1), epoch: EPOCH }));
  saved.push({ at: now - 0.2 * DAY, value: 1, id: hex(50), epoch: "PAPER-OTHER" });
  saved.sort((a, b) => a.at - b.at);
  await writeFile(path.join(dir, "observations.json"), JSON.stringify(saved));
  // FIN02 réel : montant en chaîne décimale (constaté sur crypto-restore-01).
  const api = fakeFin02("1234.50"); const apiPort = await listen(api);
  t.after(() => close(api));

  const history = startPaperBalanceHistory(dir, `http://127.0.0.1:${apiPort}`);
  const day1 = await waitFor(() => history(1), (h) => h.status === "FRESH");
  assert.deepEqual(day1.points.map((p) => p.value), [1003, 1234.5]);
  assert.equal(history(7).points.length, 3);
  assert.equal(history(30).points.length, 4, "40-day-old point is outside retention");
  assert.equal(day1.latest.value, 1234.5);
  assert.equal(day1.unit, "USDT");

  const file = path.join(dir, "observations.json");
  const persisted = JSON.parse(await readFile(file, "utf8"));
  assert.ok(!persisted.some((p) => p.at < now - 30 * DAY), "pruned on disk");
  assert.equal((await stat(file)).mode & 0o777, 0o600);

  // Restart: a new instance reads the same StateDirectory file.
  const restarted = startPaperBalanceHistory(dir, "http://127.0.0.1:9");
  const after = await waitFor(() => restarted(30), (h) => h.points.length > 0);
  assert.equal(after.points.length, 4);
  assert.equal(after.status, "UNAVAILABLE", "an unreachable FIN02 is reported, not hidden");
});

test("refuses non-decimal FIN02 amounts instead of guessing", async (t) => {
  for (const bad of ["1e3", "1 000,0", "", null, "NaN"]) {
    const dir = await mkdtemp(path.join(tmpdir(), "paper-balance-bad-"));
    t.after(() => rm(dir, { recursive: true, force: true }));
    const api = fakeFin02(bad); const port = await listen(api);
    const history = startPaperBalanceHistory(dir, `http://127.0.0.1:${port}`);
    await new Promise((r) => setTimeout(r, 150));
    assert.equal(history(30).points.length, 0, `amount ${JSON.stringify(bad)} must be refused`);
    assert.equal(history(30).status, "UNAVAILABLE");
    await close(api);
  }
});

test("serves only GET/HEAD periods 1, 7 and 30 on the history route", async (t) => {
  const server = createServer({ port: 0, distRoot: tmpdir(), balanceHistory: (days) => ({ status: "FRESH", unit: "USDT", latest: null, points: [{ at: 0, value: days }] }) });
  const port = await listen(server);
  t.after(() => close(server));
  for (const days of ["1", "7", "30"]) {
    const res = await fetch(`http://127.0.0.1:${port}/api/operator/v1/paper-balance-history?days=${days}`);
    assert.equal(res.status, 200);
    assert.equal(res.headers.get("cache-control"), "no-store");
    assert.equal((await res.json()).points[0].value, Number(days));
  }
  assert.equal((await fetch(`http://127.0.0.1:${port}/api/operator/v1/paper-balance-history?days=90`)).status, 400);
  assert.equal((await fetch(`http://127.0.0.1:${port}/api/operator/v1/paper-balance-history?days=7`, { method: "POST" })).status, 405);
});
