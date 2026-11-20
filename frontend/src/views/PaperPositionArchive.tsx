import { useEffect, useState } from "react";

type Position = {
  epoch_id: string;
  trade_id: string;
  decision_id: string | null;
  symbol: string;
  side: string;
  state: "OPEN" | "CLOSED" | "UNRESOLVED";
  history: { event_id: string; timestamp: string; event_type: string }[];
};

const states = { OPEN: "Ouverte", CLOSED: "Clôturée", UNRESOLVED: "Non résolue" };
const events: Record<string, string> = {
  POSITION_OPENED: "Ouverture",
  POSITION_CLOSED: "Clôture",
  POSITION_UNRESOLVED: "Issue non résolue",
};

export function PaperPositionArchive() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "missing">("loading");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch("/paper-archive-282.json", { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("Archive unavailable");
      const data = await response.json();
      if (data.source_sha256 !== "1db9814b843d6cf267736cfa434955e3e0359596779c24b2fb7976e0b88d0e4d"
          || !Array.isArray(data.register) || data.register.length !== 252) {
        throw new Error("Unexpected archive");
      }
      if (!controller.signal.aborted) {
        setPositions([...data.register].reverse());
        setStatus("ready");
      }
    }).catch(() => {
      if (!controller.signal.aborted) setStatus("missing");
    });
    return () => controller.abort();
  }, []);

  const needle = query.trim().toLowerCase();
  const matches = positions.filter(position =>
    [position.symbol, position.trade_id, position.decision_id ?? ""]
      .some(value => value.toLowerCase().includes(needle)));

  return (
    <section aria-labelledby="paper-archive-title">
      <h2 id="paper-archive-title">PAPER · Archive #282</h2>
      {status === "loading" && <p role="status">Chargement de l’historique…</p>}
      {status === "missing" && <p role="status">Historique PAPER indisponible.</p>}
      {status === "ready" && <>
        <label>Rechercher une position{" "}
          <input type="search" value={query} onChange={event => setQuery(event.target.value)} />
        </label>
        <p role="status">{matches.length} position(s)</p>
        {matches.map(position => (
          <details key={`${position.epoch_id}/${position.trade_id}`}>
            <summary>
              {position.symbol} · {position.side} · {states[position.state]} · {position.history.at(-1)?.timestamp.slice(0, 10)}
            </summary>
            <p>Position {position.trade_id}</p>
            <p>Décision {position.decision_id ?? "indisponible"}</p>
            <ol>{position.history.map(event => <li key={event.event_id}>
              <time dateTime={event.timestamp}>{event.timestamp}</time> · {events[event.event_type] ?? event.event_type}
            </li>)}</ol>
          </details>
        ))}
      </>}
    </section>
  );
}
