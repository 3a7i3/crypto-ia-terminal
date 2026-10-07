import React from "react";
import { useDemoCharts } from "./DemoContext";

export const FinancialHistory: React.FC = () => {
  const demo = useDemoCharts();
  return <section className="financial-history" aria-label="Évolution et répartition">
    <h3>Évolution et répartition du capital</h3>
    <p>Historique non disponible · portefeuille et résultat réalisé cumulé.</p>
    <p>Répartition proportionnelle non disponible : aucun dénominateur ni parts de capital publiés. Les montants disponibles restent affichés séparément.</p>
    <details><summary>Sources nécessaires aux graphiques</summary>
      <p>Une série gouvernée par expérience, avec dates, unités, valeurs inconnues, fraîcheur et provenance ; une répartition publiée avec dénominateur explicite et catégories disjointes.</p>
      <p>Le capital réservé et le capital déployé ne s’additionnent pas. PnL et frais restent distincts. Le capital disponible n’est pas la liquidité du marché.</p>
    </details>
    {demo}
  </section>;
};
