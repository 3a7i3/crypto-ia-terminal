import React, { useState } from "react";
import { SOURCE_IDS, useEventCenter } from "../lib/eventCenter";
import "../events.css";

const sources: Record<string, string> = { p12_alerts: "Alertes système P12", supervision_alerts: "Audit de supervision", ppl_lifecycles: "Lifecycles PAPER" };
const kinds: Record<string, string> = { DRAWDOWN: "Alerte drawdown", MEMORY: "Alerte mémoire", ERROR_RATE: "Alerte fréquence d’erreurs", RECONCILE: "Alerte réconciliation", BOOT_BLOCKED: "Démarrage bloqué", HIGH_LATENCY: "Alerte latence", EXCEPTION: "Exception signalée", OTHER_ALERT: "Alerte historique", POSITION_OPENED: "Position PAPER ouverte", POSITION_CLOSED: "Position PAPER clôturée", POSITION_UNRESOLVED: "Position PAPER non résolue" };
const severities: Record<string, string> = { INFO: "Information", WARNING: "Avertissement", CRITICAL: "Critique", UNKNOWN: "Sévérité inconnue" };
const statuses: Record<string, string> = { PRESENT: "Capture disponible", NOT_CONFIGURED: "Source non configurée", MISSING: "Source absente", READ_ERROR: "Lecture impossible", INVALID: "Source invalide", OUTPUT_LIMIT: "Limite de lecture dépassée" };

export const EventsView: React.FC = () => {
  const state = useEventCenter();
  const [sourceFilter, setSourceFilter] = useState("ALL");
  const [severityFilter, setSeverityFilter] = useState("ALL");
  if (state.status !== "success") return <section className="events-view" data-testid="events-view">
    <h2>Centre d’événements</h2><div role="status"><strong>{state.status === "loading" ? "Chargement des événements…" : "Événements indisponibles"}</strong></div>
    <p>L’état actuel est inconnu. Aucune source absente n’est remplacée par un flux vide.</p>
    {state.status === "error" && <details><summary>Détail de lecture</summary><code>{state.code}</code></details>}
  </section>;
  const snapshot = state.snapshot;
  const rows = snapshot.events.filter(e => (sourceFilter === "ALL" || e.source_id === sourceFilter) && (severityFilter === "ALL" || e.severity === severityFilter));
  return <section className="events-view" data-testid="events-view">
    <div className="events-heading"><h2>Centre d’événements</h2><span className="direction-card-badge">{snapshot.freshness_classification === "STALE" ? "Capture périmée" : "Capture récente"}</span></div>
    <p>Historique en lecture seule. Une alerte critique enregistrée ne signifie pas qu’un incident est encore actif.</p>
    {snapshot.freshness_classification === "STALE" && <p className="direction-warning" role="status">Capture périmée : événements historiques, état actuel inconnu.</p>}
    <div className="events-sources" data-testid="events-sources">{snapshot.sources.map(s => <article className="events-source" key={s.source_id}>
      <h3>{sources[s.source_id]}</h3><strong>{statuses[s.status]}</strong>
      {s.status === "PRESENT" ? <><p>{s.published_count} publiés / {s.events_observed} observés dans cette capture</p>
        {s.truncated && <p className="direction-warning">Couverture partielle · 100 événements maximum.</p>}
        {s.events_observed === 0 && <p>Aucun événement dans cette capture. Cela ne certifie pas l’absence d’incident.</p>}
        <p>{s.source_id === "ppl_lifecycles" ? "Ouvertures et états terminaux projetés ; journal PPL complet hors périmètre." : "Journal capturé ; activité actuelle du producteur inconnue."}</p>
        <p>Fraîcheur source : {s.freshness_classification === "UNKNOWN" ? "inconnue" : s.freshness_classification === "STALE" ? "périmée" : "récente"}</p>
        {s.undated_count !== 0 && <p>{s.undated_count} événements à date inconnue</p>}
        {s.excluded_records !== 0 && <p>{s.excluded_records} corrections exclues</p>}
      </> : <p>Population et fraîcheur indisponibles.</p>}
      <details><summary>Provenance de la source</summary><dl>
        <dt>Format</dt><dd>{s.format}</dd><dt>Empreinte de capture</dt><dd>{s.source_sha256 ?? "Indisponible"}</dd>
        <dt>Projection source générée à</dt><dd>{s.source_generated_at_utc ?? "Indisponible"}</dd>
        <dt>Epoch PAPER</dt><dd>{s.paper_epoch_id ?? "Indisponible"}</dd>
      </dl></details>
    </article>)}</div>
    <div className="events-filters">
      <label>Source<select aria-label="Source" value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}><option value="ALL">Toutes les sources</option>{SOURCE_IDS.map(id => <option key={id} value={id}>{sources[id]}</option>)}</select></label>
      <label>Sévérité<select aria-label="Sévérité" value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}><option value="ALL">Toutes les sévérités</option>{Object.entries(severities).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
    </div>
    <p>{rows.length} événements affichés sur {snapshot.events.length} publiés. Regroupés par source ; dates inconnues à la fin de chaque source.</p>
    {rows.length === 0 && <p data-testid="events-empty">{snapshot.events.length === 0 ? "Aucun événement publié ; consulter la disponibilité de chaque source ci-dessus." : "Aucun événement ne correspond aux filtres."}</p>}
    <div className="events-list">{rows.map(e => <article className={`event-row event-${e.severity.toLowerCase()}`} key={e.event_id} data-testid="event-row">
      <div className="events-heading"><h3>{kinds[e.kind]}</h3><span>{e.severity === "CRITICAL" ? "! " : e.severity === "WARNING" ? "⚠ " : "ℹ "}{severities[e.severity]}</span></div>
      <p>{sources[e.source_id]}{e.symbol ? ` · ${e.symbol}` : ""}</p>
      <p>{e.occurred_at_utc ? <time dateTime={e.occurred_at_utc}>{e.occurred_at_utc}</time> : "Date inconnue · aucun fuseau déduit"}</p>
      <details><summary>Voir l’identité de l’événement</summary><dl><dt>Identifiant</dt><dd>{e.event_id}</dd><dt>Record de capture</dt><dd>{e.source_record}</dd><dt>Séquence PPL</dt><dd>{e.sequence ?? "Indisponible"}</dd></dl></details>
    </article>)}</div>
    <details className="events-provenance"><summary>Provenance de la présentation</summary><dl><dt>Générée à</dt><dd>{snapshot.generated_at_utc}</dd><dt>Âge de capture</dt><dd>{snapshot.snapshot_age_s}s</dd><dt>Endpoint</dt><dd>/api/operator/v1/events</dd><dt>Autorité</dt><dd>{snapshot.authority}</dd></dl><p>La fraîcheur de présentation ne prouve pas l’activité des moteurs.</p></details>
  </section>;
};
