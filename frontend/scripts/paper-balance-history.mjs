import { readFile, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";

const retention = 30 * 86_400_000;
const maxPoints = 43_201;

function pointFrom(snapshot, now) {
  const at = Date.parse(snapshot?.generated_at_utc);
  const value = snapshot?.financial?.cash_available;
  if (snapshot?.product !== "FIN02FinancialCockpit" || snapshot.authority !== "FINANCIAL_OBSERVATION"
    || snapshot.asset !== "USDT" || !/^PAPER-[\w-]+$/.test(snapshot.paper_epoch_id ?? "")
    || !/^[a-f0-9]{64}$/.test(snapshot.financial_snapshot_id ?? "")
    || !Number.isFinite(at) || at > now || !Number.isFinite(value)) return null;
  return { at, value, id: snapshot.financial_snapshot_id, epoch: snapshot.paper_epoch_id };
}

export function startPaperBalanceHistory(directory, apiTarget) {
  const file = join(directory, "observations.json");
  let points = [];
  let status = "UNAVAILABLE";
  let epoch = null;
  const initial = readFile(file, "utf8").then(raw => {
    const saved = JSON.parse(raw);
    if (!Array.isArray(saved) || saved.length > maxPoints) throw Error("Invalid balance history");
    points = saved;
    epoch = points.at(-1)?.epoch ?? null;
  }).catch(error => {
    if (error.code !== "ENOENT") throw error;
  });
  const poll = async () => {
    try {
      await initial;
      const response = await fetch(new URL("/api/operator/v1/financial-reconciliation", apiTarget), {
        signal: AbortSignal.timeout(5000), headers: { accept: "application/json" },
      });
      if (!response.ok) throw Error("FIN02 unavailable");
      const snapshot = await response.json();
      const now = Date.now();
      const point = pointFrom(snapshot, now);
      if (!point) throw Error("Invalid FIN02 observation");
      const next = points.filter(p => p.at >= now - retention);
      if (point.at >= now - retention && !next.some(p => p.id === point.id || (p.epoch === point.epoch && p.at === point.at))) next.push(point);
      next.sort((a, b) => a.at - b.at);
      const bounded = next.slice(-maxPoints);
      if (JSON.stringify(bounded) !== JSON.stringify(points)) {
        await writeFile(file + ".tmp", JSON.stringify(bounded), { mode: 0o600 });
        await rename(file + ".tmp", file);
        points = bounded;
      }
      epoch = point.epoch;
      status = snapshot.freshness_classification === "STALE" ? "STALE"
        : snapshot.freshness_classification === "FRESH" ? "FRESH" : "UNAVAILABLE";
    } catch {
      status = "UNAVAILABLE";
    } finally {
      setTimeout(poll, 60_000).unref();
    }
  };
  void poll();
  return (days) => ({ status, unit: "USDT", latest: points.findLast(p => p.epoch === epoch) ?? null, points: points
    .filter(p => p.epoch === epoch && p.at >= Date.now() - days * 86_400_000)
    .map(({ at, value }) => ({ at, value })) });
}
