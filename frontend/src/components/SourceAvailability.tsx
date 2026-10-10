import React from "react";

/** Metadata from a successfully validated response in this mounted session.
 * Never carries previous metrics forward or invents runtime evidence. */
export interface LastSourceEvidence {
  generatedAt: string;
  identity: string;
  sourceUpdatedAt?: string;
}

const causes: Record<string, string> = {
  RESEARCH_LAB_SNAPSHOT_MISSING: "La publication du Laboratoire est introuvable au chemin configuré pour l’API.",
  BURN_IN_STATUS_MISSING: "La publication Burn-in est introuvable au chemin configuré pour l’API.",
  RESEARCH_LAB_INVALID_PATH: "Le chemin Research ne désigne pas un fichier régulier autorisé.",
  RESEARCH_LAB_UNREADABLE: "L’API ne peut pas lire la publication du Laboratoire.",
  BURN_IN_STATUS_UNREADABLE: "L’API ne peut pas lire la publication Burn-in.",
  BURN_IN_STATUS_INVALID_PATH: "Le chemin Burn-in ne désigne pas un fichier régulier autorisé.",
  RESEARCH_LAB_INVALID_SCHEMA: "La publication du Laboratoire est incompatible avec le contrat attendu.",
  BURN_IN_STATUS_INVALID_SCHEMA: "La publication Burn-in est incompatible avec le contrat attendu.",
  RESEARCH_LAB_MALFORMED_JSON: "La publication du Laboratoire est illisible ou mal formée.",
  BURN_IN_STATUS_MALFORMED_JSON: "La publication Burn-in est mal formée.",
};

export const SourceAvailability: React.FC<{
  source: "research" | "burn-in";
  code: string;
  httpStatus?: number;
  message?: string;
  lastEvidence?: LastSourceEvidence;
}> = ({ source, code, httpStatus, message, lastEvidence }) => (
  <section className="source-availability" role="status" data-testid="source-availability">
    <h2>{source === "research" ? "Laboratoire indisponible" : "Burn-in indisponible"}</h2>
    <p>{causes[code] ?? "La lecture a échoué : transport ou contrat à vérifier."}</p>
    <p>Les données actuelles restent inconnues (UNKNOWN), jamais assimilées à zéro.
      {source === "burn-in" && " L’absence de publication ne prouve ni la fin du burn-in ni l’absence de positions."}</p>
    <h3>Dernière preuve lue dans cette session</h3>
    {lastEvidence ? <p>Publication : {lastEvidence.generatedAt} · {lastEvidence.identity}
      {lastEvidence.sourceUpdatedAt && ` · Source PPL : ${lastEvidence.sourceUpdatedAt}`}
      <br />Preuve antérieure uniquement : aucune valeur passée n’est affichée comme actuelle.</p>
      : <p>Aucune preuve validée lue dans cette session. Dernière preuve runtime : inconnue.</p>}
    <h3>Action nécessaire</h3>
    <p>{source === "research"
      ? "Faire vérifier le chemin API et l’existence d’une sélection Research admise et de ses résultats immuables. Leur publication passive peut être préparée sans lancer Replay ou Diagnostic."
      : "Faire vérifier le chemin API, l’identité d’epoch et le producteur passif PPL/configuration figée. Aucun redémarrage Advisor ni changement d’epoch n’est requis par cet écran."}</p>
    <p>Aucune source de substitution, activation ou réparation automatique.</p>
    <details><summary>Diagnostics techniques</summary>
      <p>GET /api/operator/v1/{source === "research" ? "research-lab" : "burn-in"}</p>
      <p>{httpStatus && `HTTP ${httpStatus} · `}{code}</p>
      {message && <p>{message}</p>}
    </details>
  </section>
);
