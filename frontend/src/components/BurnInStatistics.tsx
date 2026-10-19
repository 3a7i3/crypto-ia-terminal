import React, { useEffect, useState } from "react";
import type { BurnInStatusSnapshot } from "../lib/burnInStatusTypes";

const labels = {
  net_realized_pnl_usd: "PnL net réalisé · USD",
  gross_pnl_usd: "PnL brut · USD",
  closed_fees_usd: "Frais des clôtures · USD",
  win_rate_pct: "Taux de réussite · %",
  profit_factor: "Profit factor · net",
  average_gain_usd: "Gain net moyen · USD",
  average_loss_usd: "Perte nette moyenne · USD",
  average_net_pnl_usd: "Résultat net moyen · USD",
};
interface Statistics {
  metrics: Record<keyof typeof labels, string | null>;
  population: { total: number; closed: number; open: number; unresolved: number; wins: number; losses: number; breakeven: number };
  freshness_classification: "FRESH" | "STALE";
}
function valid(value: unknown, snapshot: BurnInStatusSnapshot): value is Statistics {
  if (typeof value !== "object" || value === null) return false;
  const d = value as Record<string, unknown>;
  if (d.product !== "BurnInDescriptiveStatistics" || d.schema_version !== "1.0.0" || d.mode !== "READ_ONLY" || d.authority !== "PPL_AUTHORITY_PRESENTATION") return false;
  for (const key of ["paper_epoch_id", "config_snapshot_hash", "ppl_stream_sha256", "last_sequence"] as const) if (d[key] !== snapshot[key]) return false;
  if (d.freshness_classification !== "FRESH" && d.freshness_classification !== "STALE") return false;
  if (typeof d.snapshot_age_s !== "number" || !Number.isFinite(d.snapshot_age_s) || d.snapshot_age_s < 0 || typeof d.generated_at_utc !== "string" || !Number.isFinite(Date.parse(d.generated_at_utc))) return false;
  if (typeof d.metrics !== "object" || d.metrics === null || Array.isArray(d.metrics) || typeof d.population !== "object" || d.population === null || Array.isArray(d.population)) return false;
  const m = d.metrics as Record<string, unknown>;
  if (Object.keys(m).length !== Object.keys(labels).length || !Object.keys(labels).every(key => m[key] === null || (typeof m[key] === "string" && /^-?\d+(?:\.\d+)?(?:E[+-]?\d+)?$/.test(m[key] as string) && Number.isFinite(Number(m[key]))))) return false;
  const p = d.population as Record<string, number>;
  if (Object.keys(p).length !== 7 || !["total", "closed", "open", "unresolved", "wins", "losses", "breakeven"].every(key => Number.isSafeInteger(p[key]) && p[key] >= 0)) return false;
  if (p.wins + p.losses + p.breakeven !== p.closed) return false;
  if (p.closed === 0 && Object.values(m).some(value => value !== null)) return false;
  if (p.closed > 0 && ["net_realized_pnl_usd", "gross_pnl_usd", "closed_fees_usd", "win_rate_pct", "average_net_pnl_usd"].some(key => m[key] === null)) return false;
  if (m.win_rate_pct !== null && (Number(m.win_rate_pct) < 0 || Number(m.win_rate_pct) > 100)) return false;
  if (m.closed_fees_usd !== null && Number(m.closed_fees_usd) < 0) return false;
  if (m.profit_factor !== null && Number(m.profit_factor) < 0) return false;
  if ((p.losses === 0) !== (m.profit_factor === null) || (p.losses === 0) !== (m.average_loss_usd === null)) return false;
  if ((p.wins === 0) !== (m.average_gain_usd === null)) return false;
  if (m.average_gain_usd !== null && Number(m.average_gain_usd) <= 0) return false;
  if (m.average_loss_usd !== null && Number(m.average_loss_usd) >= 0) return false;
  return (["total", "closed", "open", "unresolved"] as const).every(key => p[key] === snapshot.lifecycle_counts[key]);
}
export const BurnInStatistics: React.FC<{ snapshot: BurnInStatusSnapshot }> = ({ snapshot }) => {
  const [data, setData] = useState<Statistics | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    setData(null); setFailed(false);
    fetch("/api/operator/v1/burn-in/statistics", { method: "GET" })
      .then(async response => {
        if (!response.ok) throw new Error("Unavailable");
        const body: unknown = await response.json();
        if (!valid(body, snapshot)) throw new Error("Boundary or contract mismatch");
        if (alive) setData(body);
      }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [snapshot]);
  return <section className="burnin-panel" aria-label="Statistiques descriptives PPL">
    <h3>Statistiques des ordres clôturés</h3>
    <p>Résultats PAPER issus de PPL, non réconciliés avec FIN. Positions ouvertes et non résolues exclues ; aucune certification de performance.</p>
    {!data ? <p role="status">{failed ? "Statistiques indisponibles ou frontière différente. Aucune valeur remplacée par zéro." : "Lecture des statistiques…"}</p> : <>
      <p>{data.population.closed} clôtures · {data.population.wins} gagnantes · {data.population.losses} perdantes · {data.population.breakeven} nulles · {data.freshness_classification === "FRESH" ? "Capture récente" : "Capture périmée"}</p>
      <dl className="burnin-provenance-grid">{Object.entries(labels).map(([key, label]) => {
        const value = data.metrics[key as keyof typeof labels];
        return <div key={key}><dt>{label}</dt><dd>{value === null ? "Non disponible" : <><strong>{new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(Number(value))}</strong><details><summary>Valeur exacte publiée</summary><code>{value}</code></details></>}</dd></div>;
      })}</dl>
      <p>Taux de réussite : gagnantes / toutes les clôtures, résultats nuls inclus. Profit factor : somme des gains nets / valeur absolue des pertes nettes. Sans perte observée, ce ratio reste non disponible.</p>
    </>}
  </section>;
};
