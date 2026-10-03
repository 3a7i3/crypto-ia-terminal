import React from "react";
import { useStorage, type StorageState } from "../lib/storage";

const statuses = { PRESENT: "Capture disponible", NOT_CONFIGURED: "Source non configurée", MISSING: "Répertoire absent", READ_ERROR: "Lecture impossible", INVALID_PATH: "Chemin ou fichier non régulier", OUTPUT_LIMIT: "Limite de lecture dépassée", SOURCE_CHANGED: "Source modifiée pendant la capture", INVALID_METADATA: "Métadonnées invalides" };
export const StorageCard: React.FC<{ state: StorageState }> = ({ state }) => {
  if (state.status !== "success") return <article className="direction-card direction-card-governed" data-testid="storage-view">
    <h3>Stockage · DecisionPackets</h3><strong>{state.status === "loading" ? "Chargement du stockage…" : "Stockage indisponible"}</strong>
    <p>Volume et population inconnus.</p>{state.status === "error" && <details><summary>Détail de lecture</summary><code>{state.code}</code></details>}
  </article>;
  const s = state.snapshot, available = s.source_status === "PRESENT";
  return <article className="direction-card direction-card-governed" data-testid="storage-view">
    <div className="direction-card-heading"><h3>Stockage · DecisionPackets</h3><span className="direction-card-badge">{s.freshness_classification === "STALE" ? "Capture périmée" : "Capture récente"}</span></div>
    <strong>{statuses[s.source_status]}</strong>
    {s.freshness_classification === "STALE" && <p className="direction-warning">Observation historique : volume actuel inconnu.</p>}
    <dl className="direction-fact-grid">
      <div><dt>Fichiers à la capture</dt><dd>{available ? s.matched_file_count : "Indisponible"}</dd></div>
      <div><dt>Volume exact en octets</dt><dd>{available ? s.total_bytes : "Indisponible"}</dd></div>
      <div><dt>Dernière modification filesystem</dt><dd>{s.latest_file_modified_at_utc ?? "Indisponible"}</dd></div>
    </dl>
    {available && s.matched_file_count === 0 && <p>Aucun fichier correspondant dans cette capture. Cela ne prouve pas l’absence de décisions machine.</p>}
    <p>Métadonnées des fichiers uniquement. Aucun journal ouvert ; ce volume ne mesure ni le nombre de packets, ni l’espace disque libre, ni la santé Advisor.</p>
    <details className="direction-provenance"><summary>Provenance du stockage</summary><dl className="direction-fact-grid">
      <div><dt>Capture à</dt><dd>{s.observed_at_utc}</dd></div><div><dt>Âge de la capture</dt><dd>{s.snapshot_age_s}s</dd></div>
      <div><dt>Portée</dt><dd>Enfants directs · {s.pattern}</dd></div><div><dt>Entrées observées</dt><dd>{s.entries_observed ?? "Indisponible"}</dd></div>
      <div><dt>Empreinte des métadonnées</dt><dd>{s.inventory_sha256 ?? "Indisponible"}</dd></div>
      <div><dt>Autorité</dt><dd>{s.authority}</dd></div><div><dt>Endpoint</dt><dd>/api/operator/v1/storage</dd></div>
    </dl><p>La fraîcheur de capture ne prouve pas l’activité du producteur. L’empreinte ne porte pas sur le contenu des journaux.</p></details>
  </article>;
};
export const StorageView: React.FC = () => <StorageCard state={useStorage()} />;
