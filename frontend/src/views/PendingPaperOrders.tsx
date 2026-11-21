import type { PendingPaperOrder } from "../types";

const labels = { PENDING: "En attente", SUBMITTED: "Soumis", PARTIALLY_FILLED: "Exécuté en partie" };
const numericFields = ["size_usd", "planned_entry_price", "tp_price", "sl_price"] as const;

function isPendingOrder(value: unknown): value is PendingPaperOrder {
  if (!value || typeof value !== "object") return false;
  const order = value as Record<string, unknown>;
  return ["order_id", "decision_id", "symbol", "updated_at_utc"].every(
    key => typeof order[key] === "string" && order[key].trim() !== "",
  ) && typeof order.updated_at_utc === "string" && order.updated_at_utc.endsWith("Z")
    && Number.isFinite(Date.parse(order.updated_at_utc))
    && (order.side === "LONG" || order.side === "SHORT")
    && (order.state === "PENDING" || order.state === "SUBMITTED" || order.state === "PARTIALLY_FILLED")
    && numericFields.every(key => order[key] === null ||
      (typeof order[key] === "number" && Number.isFinite(order[key]) && order[key] > 0));
}

export function PendingPaperOrders({ publication }: { publication?: unknown }) {
  const orders = Array.isArray(publication) && publication.every(isPendingOrder)
    && new Set(publication.map(order => order.order_id)).size === publication.length
    ? publication : null;
  const message = publication === undefined ? "En attente de la publication des ordres PAPER."
    : orders === null ? "Publication des ordres indisponible."
    : "Aucun ordre en attente dans cette publication.";

  return (
    <section className="paper-pending-section" aria-labelledby="pending-paper-orders">
      <h2 id="pending-paper-orders">Ordres PAPER en attente</h2>
      <div className="technical-table" role="region" aria-label="Tableau des ordres en attente" tabIndex={0}>
        <table>
          <thead><tr>
            {["Symbole", "Sens", "État", "Taille (USD)", "Entrée prévue", "TP", "SL", "Mise à jour UTC"].map(
              label => <th key={label} scope="col" className="p-2">{label}</th>,
            )}
          </tr></thead>
          <tbody>{orders?.length ? orders.map(order => (
            <tr key={order.order_id} className="border-b">
              <th scope="row" className="p-2">
                <details><summary>{order.symbol}</summary>
                  <div>Ordre {order.order_id}</div>
                  <div>Décision {order.decision_id}</div>
                </details>
              </th>
              <td className="p-2">{order.side}</td>
              <td className="p-2">{labels[order.state]}</td>
              {numericFields.map(key => <td key={key} className="p-2">{order[key] ?? "—"}</td>)}
              <td className="p-2"><time dateTime={order.updated_at_utc}>{order.updated_at_utc}</time></td>
            </tr>
          )) : <tr><td colSpan={8} className="p-2">{message}</td></tr>}</tbody>
        </table>
      </div>
    </section>
  );
}
