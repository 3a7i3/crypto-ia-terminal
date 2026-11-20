import { useState } from "react";
import { paperOrderEvents } from "../fixtures/paperOrderEvents";
import { buildPaperOrderRegister, findPaperOrders, type PaperOrderEvent } from "../lib/paperOrderRegister";

const labels: Record<PaperOrderEvent["kind"], string> = {
  decision: "Décision enregistrée",
  approved: "Ordre approuvé",
  refused: "Ordre refusé",
  submitted: "Ordre soumis",
  cancelled: "Ordre annulé",
  executed: "Exécution simulée",
  updated: "Position mise à jour",
  closed: "Position clôturée",
  unresolved: "Position non résolue",
};

const register = buildPaperOrderRegister(paperOrderEvents);

export function PaperOrderRegisterView() {
  const [query, setQuery] = useState("");
  const orders = findPaperOrders(register, query);

  return (
    <section aria-labelledby="paper-test-register">
      <h2 id="paper-test-register">Registre PAPER de test</h2>
      <p>Données synthétiques · horaires UTC</p>
      <label htmlFor="paper-test-search">Ordre, décision ou position</label>{" "}
      <input id="paper-test-search" type="search" value={query}
        onChange={event => setQuery(event.target.value)} />
      <p role="status">{orders.length === 0 ? "Aucun ordre trouvé." : `${orders.length} ordre(s)`}</p>
      {orders.map(order => (
        <details key={order.id} className="snapshot-source-details">
          <summary>{order.id} · {labels[order.lastEvent.kind]}</summary>
          <ol>
            {order.timeline.map(event => (
              <li key={event.sequence}>
                <time dateTime={event.at}>{event.at}</time> · {labels[event.kind]}
                {event.decisionId && <div>Décision {event.decisionId}</div>}
                {event.positionId && <div>Position {event.positionId}</div>}
                {event.detail && <div>{event.detail}</div>}
              </li>
            ))}
          </ol>
        </details>
      ))}
    </section>
  );
}
