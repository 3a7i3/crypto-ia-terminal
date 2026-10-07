import React, { useEffect, useState } from "react";
import { useDemoCharts } from "./DemoContext";
import { validAccountingHistory } from "../lib/pplAccountingHistory";
import type {
  AccountingHistory,
  AccountingSample,
} from "../lib/pplAccountingHistory";
import "../accounting-history.css";
export const ACCOUNTING_HISTORY_ENDPOINT =
  "/api/operator/v1/ppl-accounting-history";
const colors = ["#34c6ce", "#a292ed", "#eab56a"];
const labels: Record<string, string> = {
  available_cash: "Disponible",
  reserved_principal: "Réservé",
  unresolved_capital: "Non résolu",
};
const num = (v: string | number) =>
  Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 2 });
const date = (v: string) =>
  new Date(v).toLocaleString("fr-FR", {
    timeZone: "UTC",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
export function AccountingPlot({
  samples,
  metric,
}: {
  samples: AccountingSample[];
  metric: "available_cash" | "realized_pnl";
}) {
  const values = samples.map((s) => Number(s[metric]));
  const min = Math.min(...values),
    max = Math.max(...values);
  const pad =
    max === min ? Math.max(Math.abs(min) * 0.01, 0.01) : (max - min) * 0.08;
  const low = min - pad,
    high = max + pad;
  const first = samples[0],
    last = samples[samples.length - 1];
  const begin = Date.parse(first.timestamp_utc),
    end = Date.parse(last.timestamp_utc);
  const x = (s: AccountingSample) =>
    end === begin
      ? 285
      : 65 + ((Date.parse(s.timestamp_utc) - begin) / (end - begin)) * 435;
  const y = (v: number) => 190 - ((v - low) / (high - low)) * 160;
  const path = samples
    .map((s, i) =>
      i === 0 ? `M${x(s)},${y(values[i])}` : `H${x(s)}V${y(values[i])}`,
    )
    .join(" ");
  return (
    <svg
      viewBox="0 0 535 230"
      role="img"
      aria-label={
        metric === "realized_pnl"
          ? "Résultat réalisé cumulé aux événements PPL"
          : "Capital disponible aux événements PPL"
      }
    >
      {[low, (low + high) / 2, high].map((v) => (
        <g key={v}>
          <line
            x1="65"
            x2="500"
            y1={y(v)}
            y2={y(v)}
            stroke="currentColor"
            opacity=".15"
          />
          <text x="58" y={y(v) + 4} textAnchor="end">
            {num(v)}
          </text>
        </g>
      ))}
      {low <= 0 && high >= 0 && (
        <line
          x1="65"
          x2="500"
          y1={y(0)}
          y2={y(0)}
          stroke="currentColor"
          opacity=".4"
          strokeDasharray="4 4"
        />
      )}
      {samples.length > 1 && (
        <path d={path} fill="none" stroke={colors[0]} strokeWidth="2.5" />
      )}
      <circle
        cx={x(last)}
        cy={y(values[values.length - 1])}
        r="4"
        fill={colors[0]}
      />
      <text x="65" y="216">
        {date(first.timestamp_utc)}
      </text>
      <text x="500" y="216" textAnchor="end">
        {date(last.timestamp_utc)}
      </text>
    </svg>
  );
}
export const FinancialHistory: React.FC = () => {
  const demo = useDemoCharts();
  const [history, setHistory] = useState<AccountingHistory | null>(null);
  const [message, setMessage] = useState("Chargement de l’historique publié…");
  const [tab, setTab] = useState<
    "realized_pnl" | "available_cash" | "allocation"
  >("realized_pnl");
  useEffect(() => {
    if (demo) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(ACCOUNTING_HISTORY_ENDPOINT, {
          method: "GET",
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok)
          throw new Error(
            `Historique non disponible · HTTP ${response.status}`,
          );
        const text = await response.text();
        if (text.length > 2_000_000)
          throw new Error("Historique trop volumineux");
        const payload: unknown = JSON.parse(text);
        if (!validAccountingHistory(payload))
          throw new Error("Historique rejeté : contrat invalide");
        if (alive) {
          setHistory(payload);
          setMessage("");
        }
      } catch (error) {
        if (alive) {
          setHistory(null);
          setMessage(
            "Historique non disponible · " +
              (error instanceof Error &&
              /^(Historique|HTTP)/.test(error.message)
                ? error.message
                : "transport indisponible"),
          );
        }
      } finally {
        if (alive) timer = setTimeout(load, 20_000);
      }
    }
    void load();
    return () => {
      alive = false;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [demo]);
  if (demo)
    return (
      <section className="financial-history">
        <h3>Évolution et répartition du capital</h3>
        {demo}
      </section>
    );
  if (!history)
    return (
      <section
        className="financial-history"
        aria-label="Évolution et répartition"
      >
        <h3>Historique comptable PAPER</h3>
        <p>{message}</p>
        <p>
          Répartition proportionnelle non disponible sans publication validée.
        </p>
      </section>
    );
  const last = history.samples[history.samples.length - 1];
  return (
    <section
      className="financial-history accounting-history"
      aria-label="Évolution et répartition"
    >
      <h3>Historique comptable PAPER</h3>
      <p>
        Une seule expérience · unité comptable PAPER · aucune conversion de
        devise
      </p>
      <p className="accounting-capture">
        Capture{" "}
        {history.freshness_classification === "STALE" ? "périmée" : "récente"} :{" "}
        {date(history.source_generated_at_utc)} UTC · séquence{" "}
        {history.last_sequence}
      </p>
      <p className="accounting-epoch">{history.paper_epoch_id}</p>
      <div className="accounting-tabs" aria-label="Choix du graphique">
        {(["realized_pnl", "available_cash", "allocation"] as const).map(
          (key) => (
            <button
              type="button"
              key={key}
              aria-pressed={tab === key}
              onClick={() => setTab(key)}
            >
              {key === "realized_pnl"
                ? "Résultat réalisé"
                : key === "available_cash"
                  ? "Capital disponible"
                  : "Répartition"}
            </button>
          ),
        )}
      </div>
      {tab !== "allocation" ? (
        <>
          <p className="accounting-value">
            {num(last[tab])}
            <small> unités PAPER</small>
          </p>
          <AccountingPlot samples={history.samples} metric={tab} />
          <p>
            États aux événements PPL, sans interpolation de prix.
            {history.samples.length === 1
              ? " Une seule observation : point isolé."
              : ""}
          </p>
        </>
      ) : history.allocation ? (
        <div className="accounting-allocation">
          <svg
            viewBox="0 0 200 200"
            role="img"
            aria-label="Répartition du principal comptable"
          >
            <circle
              cx="100"
              cy="100"
              r="70"
              fill="none"
              stroke="currentColor"
              opacity=".12"
              strokeWidth="25"
            />
            {history.allocation.segments.map((s, i, rows) => (
              <circle
                key={s.id}
                cx="100"
                cy="100"
                r="70"
                fill="none"
                stroke={colors[i]}
                strokeWidth="25"
                pathLength="1"
                strokeDasharray={`${s.share} 1`}
                strokeDashoffset={
                  -rows.slice(0, i).reduce((v, row) => v + Number(row.share), 0)
                }
                transform="rotate(-90 100 100)"
              />
            ))}
            <text x="100" y="100" textAnchor="middle">
              {num(history.allocation.denominator)}
            </text>
            <text x="100" y="122" textAnchor="middle">
              unités PAPER
            </text>
          </svg>
          <ul>
            {history.allocation.segments.map((s, i) => (
              <li key={s.id}>
                <span style={{ color: colors[i] }}>{labels[s.id]}</span>
                <strong>{num(Number(s.share) * 100)} %</strong>
                <span>{num(s.amount)}</span>
              </li>
            ))}
          </ul>
          <p>
            Total = disponible + réservé + non résolu. Le non résolu ne certifie
            pas une valeur récupérable.
          </p>
        </div>
      ) : (
        <p>Répartition non disponible : dénominateur absent ou invalide.</p>
      )}
      <p>
        Le capital disponible ne représente pas la valeur totale du
        portefeuille. PnL latent et financement non établis ; aucune
        certification FIN.
      </p>
      <details>
        <summary>Valeurs et preuves</summary>
        <p>
          Projecteur PPL v2 existant ; résultat réalisé après frais d’entrée et
          de sortie. Replay validé ; aucun recoupement comptable indépendant
          disponible.
        </p>
        <p>Source : {history.source_snapshot_sha256}</p>
        <p>Producteur : {history.producer_source_sha}</p>
        <div className="accounting-table">
          <table>
            <thead>
              <tr>
                <th>Séquence</th>
                <th>Date UTC</th>
                <th>Disponible</th>
                <th>Réalisé</th>
                <th>Réservé</th>
                <th>Non résolu</th>
                <th>Frais</th>
              </tr>
            </thead>
            <tbody>
              {history.samples.map((s) => (
                <tr key={s.event_id}>
                  <td>{s.sequence}</td>
                  <td>{s.timestamp_utc}</td>
                  {[
                    s.available_cash,
                    s.realized_pnl,
                    s.reserved_principal,
                    s.unresolved_capital,
                    s.fees_paid,
                  ].map((v, i) => (
                    <td key={i}>{v}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
};
