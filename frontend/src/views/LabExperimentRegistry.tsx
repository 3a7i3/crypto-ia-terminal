import { usePassiveSnapshot } from "../lib/usePassiveSnapshot";

type Card = { experiment_id: string; execution_host: string; published_at: string; result_sha256: string; summary: { observations: number } };
type Registry = { experiments: Card[] };
const errors = ["LAB_REGISTRY_UNAVAILABLE"];
function valid(value: unknown): value is Registry {
  const data = value as Registry | null;
  return Array.isArray(data?.experiments) && data.experiments.every(card =>
    typeof card?.experiment_id === "string" && typeof card.execution_host === "string" &&
    typeof card.result_sha256 === "string" && Number.isFinite(Date.parse(card.published_at)) &&
    Number.isSafeInteger(card.summary?.observations));
}
export function LabExperimentRegistry() {
  const state = usePassiveSnapshot("/api/operator/v1/lab-experiments", valid, errors, "LAB_REGISTRY");
  return <section className="research-panel" aria-label="Expériences">
    <h2>Expériences</h2>
    {state.status === "loading" && <p>Chargement des fiches…</p>}
    {state.status === "error" && <p>Registre indisponible.</p>}
    {state.status === "success" && (state.snapshot.experiments.length === 0
      ? <p>Aucune fiche publiée.</p>
      : state.snapshot.experiments.map(card => <article className="research-attribution-card" key={card.experiment_id}>
        <h3>Test de publication</h3>
        <p><strong>Synthétique</strong> · <strong>Terminé</strong></p>
        <p>VM d’origine : {card.execution_host}</p>
        <p>Publié le <time dateTime={card.published_at}>{new Date(card.published_at).toLocaleString("fr-FR")}</time></p>
        <p>{card.summary.observations} observations synthétiques</p>
        <details><summary>Provenance</summary>
          <p style={{ overflowWrap: "anywhere" }}>{card.experiment_id}</p>
          <p style={{ overflowWrap: "anywhere" }}>SHA-256 du résultat : {card.result_sha256}</p>
        </details>
      </article>))}
  </section>;
}
