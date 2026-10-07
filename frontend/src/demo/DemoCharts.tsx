import React, { useState } from "react";

// Independent illustration, not inferred from FIN/PPL snapshots. Values and
// capital shares are explicitly supplied by this fictitious scenario.
const samples = [
  { date: "01 oct.", capital: 1000, realized: 0 },
  { date: "02 oct.", capital: 1005, realized: 2 },
  { date: "03 oct.", capital: 1002, realized: 1 },
  { date: "04 oct.", capital: 1012, realized: 6 },
  { date: "05 oct.", capital: 1008, realized: 4 },
  { date: "06 oct.", capital: 1018, realized: 10 },
  { date: "07 oct.", capital: 1020, realized: 12 },
];
const allocation = [
  { label: "Disponible", amount: 850, percent: 85, color: "var(--accent)" },
  { label: "Principal réservé", amount: 140, percent: 14, color: "var(--violet)" },
  { label: "Principal non résolu", amount: 10, percent: 1, color: "var(--warn)" },
];
export const DemoCharts: React.FC = () => {
  const [metric, setMetric] = useState<"capital" | "realized">("capital");
  const low = metric === "capital" ? 1000 : 0, high = metric === "capital" ? 1020 : 12;
  const points = samples.map((p, i) => `${40 + i * 80},${140 - (p[metric] - low) / (high - low) * 100}`).join(" ");
  return <section className="demo-charts" aria-label="Graphiques fictifs indépendants">
    <h3>Illustration fictive · scénario indépendant</h3>
    <p>Ces séries et parts sont inventées pour examiner la présentation. Elles ne décrivent ni les snapshots ci-dessus ni une expérience réelle.</p>
    <div className="category-links" role="group" aria-label="Série fictive affichée">
      <button aria-pressed={metric === "capital"} onClick={() => setMetric("capital")}>Portefeuille fictif</button>
      <button aria-pressed={metric === "realized"} onClick={() => setMetric("realized")}>Résultat réalisé fictif</button>
    </div>
    <figure><figcaption>{metric === "capital" ? "Évolution du portefeuille" : "Résultat réalisé cumulé"} · USDT fictifs · 1–7 octobre 2026</figcaption>
      <svg viewBox="0 0 560 180" role="img" aria-label={`${metric === "capital" ? "Capital" : "Résultat réalisé"} fictif de ${low} à ${high} USDT`}>
        <line x1="40" y1="140" x2="520" y2="140" stroke="var(--bg-border)"/>
        <line x1="40" y1="40" x2="520" y2="40" stroke="var(--bg-border)"/>
        <text x="0" y="44">{high}</text><text x="0" y="144">{low}</text>
        <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth="3"/>
        {samples.map((p, i) => <circle key={p.date} cx={40+i*80} cy={140-(p[metric]-low)/(high-low)*100} r="4" fill="var(--accent)"><title>{p.date} : {p[metric]} USDT fictifs</title></circle>)}
        <text x="40" y="174">1 oct.</text><text x="460" y="174">7 oct.</text>
      </svg>
    </figure>
    <h4>Répartition fictive · dénominateur : 1 000 USDT au coût historique</h4>
    <div className="demo-allocation" role="img" aria-label="Capital fictif : 85 % disponible, 14 % réservé, 1 % non résolu">{allocation.map((a) => <span key={a.label} style={{ width:`${a.percent}%`, background:a.color }}/>)}</div>
    <ul className="demo-allocation-legend">{allocation.map((a) => <li key={a.label}>{a.label} : {a.amount} USDT · {a.percent} %</li>)}</ul>
    <p>Catégories disjointes. Capital déployé exclu des parts supplémentaires ; PnL et frais hors répartition. Capital disponible ≠ liquidité du marché.</p>
    <details><summary>Points fictifs exacts</summary><table><thead><tr><th>Date</th><th>Portefeuille</th><th>Réalisé cumulé</th></tr></thead><tbody>{samples.map((p) => <tr key={p.date}><td>{p.date}</td><td>{p.capital}</td><td>{p.realized}</td></tr>)}</tbody></table></details>
  </section>;
};
