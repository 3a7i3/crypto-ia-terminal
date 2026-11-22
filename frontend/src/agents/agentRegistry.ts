// ── Registre des identités d'agents (métadonnées source) ───────────────────
//
// Ce module sépare strictement deux choses :
//   1. le registre versionné (qui est recensé, d'où vient son profil, quel est
//      son statut de revue A0) — `agentIdentityRegistry.v1.json` ;
//   2. les preuves d'activité runtime, qui n'existent pas encore côté serveur.
//
// Le voyant d'activité est GRIS par défaut. Il ne devient VERT ou ROUGE que si
// un runner relié et vérifié fournit une preuve serveur datée, fraîche et
// cohérente. Une erreur d'API, une preuve absente, périmée ou incohérente,
// un serveur inaccessible ou une source non branchée donnent GRIS + motif.
// Aucune fonction de ce module ne lance, n'arrête ni n'autorise un agent.

import registryJson from "./agentIdentityRegistry.v1.json";

export type FamilyId =
  | "OBSERVATION"
  | "RECHERCHE"
  | "EVALUATION"
  | "RISQUE_GOUVERNANCE"
  | "EXECUTION_PAPER"
  | "MAINTENANCE";

export const FAMILY_ORDER: readonly FamilyId[] = [
  "OBSERVATION",
  "RECHERCHE",
  "EVALUATION",
  "RISQUE_GOUVERNANCE",
  "EXECUTION_PAPER",
  "MAINTENANCE",
];

export type ValidationStatus =
  | "MIGRATION_CANDIDATE"
  | "REVIEW_REQUIRED"
  | "BLOCKED_LEGACY_RECONCILIATION";

/** NOT_WIRED : aucun runner relié. VERIFIED : runner relié et vérifié. BLOCKED : héritage. */
export type WiringStatus = "NOT_WIRED" | "VERIFIED" | "BLOCKED";

export interface AgentFamily {
  id: FamilyId;
  label: string;
  summary: string;
}

export interface AgentIdentity {
  id: string;
  display_name: string;
  family: FamilyId | null;
  mission: string;
  source_path: string;
  source_blob_sha1: string;
  validation_status: ValidationStatus;
  validation_note: string;
  wiring_status: WiringStatus;
  runner_id: string | null;
  legacy_blocked: boolean;
}

export interface AgentRegistry {
  schema: "cat.agent_identity_registry.v1";
  registry_version: number;
  authority: "SOURCE_METADATA_ONLY";
  boundary: string;
  source_basis: Record<string, string>;
  families: AgentFamily[];
  agents: AgentIdentity[];
}

const VALIDATION: readonly ValidationStatus[] = [
  "MIGRATION_CANDIDATE",
  "REVIEW_REQUIRED",
  "BLOCKED_LEGACY_RECONCILIATION",
];
const WIRING: readonly WiringStatus[] = ["NOT_WIRED", "VERIFIED", "BLOCKED"];
const ID_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SHA1_RE = /^[0-9a-f]{40}$/;
const PROFILE_PATH_RE = /^\.github\/(?:agents\/)?[A-Za-z0-9-]+\.agent\.md$/;

/** Vérifie le registre et lève une erreur explicite au premier écart. */
export function validateRegistry(input: unknown): AgentRegistry {
  const r = input as AgentRegistry;
  const fail = (msg: string): never => {
    throw new Error(`Registre agents invalide : ${msg}`);
  };
  if (!r || r.schema !== "cat.agent_identity_registry.v1") fail("schéma inattendu");
  if (r.authority !== "SOURCE_METADATA_ONLY") fail("autorité inattendue");
  const famIds = r.families.map((f) => f.id);
  if (famIds.length !== FAMILY_ORDER.length || FAMILY_ORDER.some((id, i) => famIds[i] !== id))
    fail("familles attendues dans l'ordre fixe");
  const seen = new Set<string>();
  const seenPaths = new Set<string>();
  for (const a of r.agents) {
    if (!ID_RE.test(a.id)) fail(`identifiant ${a.id}`);
    if (seen.has(a.id)) fail(`identifiant dupliqué ${a.id}`);
    seen.add(a.id);
    if (!PROFILE_PATH_RE.test(a.source_path)) fail(`chemin source ${a.source_path}`);
    if (seenPaths.has(a.source_path)) fail(`source dupliquée ${a.source_path}`);
    seenPaths.add(a.source_path);
    if (!SHA1_RE.test(a.source_blob_sha1)) fail(`empreinte source ${a.id}`);
    if (!VALIDATION.includes(a.validation_status)) fail(`validation ${a.id}`);
    if (!WIRING.includes(a.wiring_status)) fail(`branchement ${a.id}`);
    if (!a.mission.trim() || !a.display_name.trim()) fail(`mission ou nom vide ${a.id}`);
    if (a.legacy_blocked) {
      if (a.family !== null) fail(`héritage ${a.id} rattaché à une famille`);
      if (a.validation_status !== "BLOCKED_LEGACY_RECONCILIATION" || a.wiring_status !== "BLOCKED")
        fail(`héritage ${a.id} non bloqué`);
    } else {
      if (a.family === null || !FAMILY_ORDER.includes(a.family)) fail(`famille ${a.id}`);
      if (a.validation_status === "BLOCKED_LEGACY_RECONCILIATION") fail(`statut héritage hors héritage ${a.id}`);
    }
    if (a.wiring_status === "VERIFIED" && !a.runner_id) fail(`runner manquant ${a.id}`);
    if (a.wiring_status !== "VERIFIED" && a.runner_id !== null) fail(`runner non vérifié déclaré ${a.id}`);
    if (a.family === "EXECUTION_PAPER") fail(`profil PAPER non qualifié ${a.id}`);
  }
  return r;
}

export const AGENT_REGISTRY: AgentRegistry = validateRegistry(registryJson);

export const GITHUB_SOURCE_BASE = "https://github.com/3a7i3/crypto-ia-terminal/blob/main/";

export function agentsOfFamily(reg: AgentRegistry, family: FamilyId): AgentIdentity[] {
  return reg.agents.filter((a) => !a.legacy_blocked && a.family === family);
}

export function legacyAgents(reg: AgentRegistry): AgentIdentity[] {
  return reg.agents.filter((a) => a.legacy_blocked);
}

export const VALIDATION_LABEL: Record<ValidationStatus, string> = {
  MIGRATION_CANDIDATE: "Candidat à migrer",
  REVIEW_REQUIRED: "Revue requise",
  BLOCKED_LEGACY_RECONCILIATION: "Bloqué · héritage",
};

export const WIRING_LABEL: Record<WiringStatus, string> = {
  NOT_WIRED: "Aucun runner relié",
  VERIFIED: "Runner relié et vérifié",
  BLOCKED: "Bloqué",
};

// ── Preuves runtime (séparées du registre) ────────────────────────────────

/** Une preuve d'activité publiée par le serveur pour un runner identifié. */
export interface ActivityEvidence {
  agent_id: string;
  runner_id: string;
  /** Date à laquelle le serveur a produit cette preuve. */
  observed_at_utc: string;
  /** Dernière activité attestée du runner. */
  last_activity_at_utc: string | null;
  /** Référence de la preuve côté serveur (journal, heartbeat, digest). */
  server_proof_ref: string;
  /** État d'exécution attesté. Seul EN_COURS peut produire un voyant vert. */
  execution_state?: "EN_COURS" | "TERMINE" | "INDETERMINE";
  /** Issue d'une invocation terminée : fin normale ou échec. Sert au libellé rouge. */
  outcome?: "FIN_NORMALE" | "ECHEC" | null;
}

export type EvidenceSource =
  | { status: "NOT_CONNECTED" }
  | { status: "LOADING" }
  | { status: "UNREACHABLE" }
  | { status: "API_ERROR"; code: string }
  | { status: "OK"; records: ActivityEvidence[] };

/** Aucune source de preuve runtime n'existe à ce jour : état honnête par défaut. */
export const RUNTIME_EVIDENCE_SOURCE: EvidenceSource = { status: "NOT_CONNECTED" };

export type ActivityLight = "GREEN" | "RED" | "GRAY";

export interface ActivityVerdict {
  light: ActivityLight;
  label: string;
  reason: string;
  last_proof_at_utc: string | null;
}

/** Âge maximal d'une preuve serveur pour être considérée comme actuelle. */
export const MAX_PROOF_AGE_S = 15 * 60;
/** Fenêtre d'activité récente (conservée pour compatibilité : elle ne produit plus de vert). */
export const RECENT_ACTIVITY_WINDOW_S = 60 * 60;
/** Tolérance d'horloge pour une date légèrement future. */
export const CLOCK_SKEW_S = 60;

const ISO_UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;

function parseUtc(v: unknown): number | null {
  if (typeof v !== "string" || !ISO_UTC_RE.test(v)) return null;
  const t = Date.parse(v);
  return Number.isFinite(t) ? t : null;
}

const gray = (reason: string, last: string | null = null): ActivityVerdict => ({
  light: "GRAY",
  label: "Non attesté",
  reason,
  last_proof_at_utc: last,
});

/**
 * Classe l'activité d'un profil. Fonction pure : VERT et ROUGE exigent un
 * runner vérifié et une preuve serveur unique, cohérente et fraîche.
 */
export function classifyActivity(
  agent: AgentIdentity,
  source: EvidenceSource,
  nowMs: number,
): ActivityVerdict {
  if (agent.legacy_blocked) return gray("Héritage bloqué : aucun statut opérationnel.");
  if (agent.wiring_status !== "VERIFIED" || !agent.runner_id)
    return gray("Préproduction : aucun runner relié et vérifié.");
  switch (source.status) {
    case "NOT_CONNECTED":
      return gray("Aucune source de preuve serveur n'est branchée.");
    case "LOADING":
      return gray("Lecture de la preuve serveur en cours.");
    case "UNREACHABLE":
      return gray("Serveur de preuves inaccessible.");
    case "API_ERROR":
      return gray(`Erreur de l'API de preuves (${source.code}).`);
    case "OK":
      break;
    default:
      return gray("Source de preuve inconnue.");
  }
  const records = source.records.filter((r) => r && r.agent_id === agent.id);
  if (records.length === 0) return gray("Aucune preuve serveur pour ce profil.");
  if (records.length > 1) return gray("Preuves multiples contradictoires pour ce profil.");
  const ev = records[0];
  if (ev.runner_id !== agent.runner_id)
    return gray("Preuve incohérente : runner différent du runner vérifié.");
  if (typeof ev.server_proof_ref !== "string" || !ev.server_proof_ref.trim())
    return gray("Preuve incohérente : référence serveur absente.");
  const observed = parseUtc(ev.observed_at_utc);
  if (observed === null) return gray("Preuve incohérente : date d'observation invalide.");
  if (observed > nowMs + CLOCK_SKEW_S * 1000)
    return gray("Preuve incohérente : date d'observation dans le futur.", ev.observed_at_utc);
  if (nowMs - observed > MAX_PROOF_AGE_S * 1000)
    return gray("Preuve périmée : l'état actuel n'est pas attesté.", ev.observed_at_utc);
  if (ev.execution_state === undefined)
    return gray("Preuve incomplète : état d'exécution non attesté.", ev.observed_at_utc);
  if (ev.execution_state === "INDETERMINE")
    return gray("Activité indéterminée : bail expiré ou preuve absente.", ev.observed_at_utc);
  const activity = ev.last_activity_at_utc === null ? null : parseUtc(ev.last_activity_at_utc);
  if (ev.last_activity_at_utc !== null && activity === null)
    return gray("Preuve incohérente : date d'activité invalide.", ev.observed_at_utc);
  if (activity !== null && activity > observed + CLOCK_SKEW_S * 1000)
    return gray("Preuve incohérente : activité postérieure à l'observation.", ev.observed_at_utc);
  if (ev.execution_state === "EN_COURS") {
    // Vert uniquement : exécution en cours attestée, preuve fraîche (contrôlée plus haut).
    return {
      light: "GREEN",
      label: "Actif",
      reason: "Exécution en cours attestée par un bail valide.",
      last_proof_at_utc: ev.observed_at_utc,
    };
  }
  // TERMINE : inactivité attestée. Jamais vert, même si la fin est récente.
  if (ev.outcome === "ECHEC")
    return {
      light: "RED",
      label: "Inactif · échec",
      reason: "Dernière invocation terminée en échec.",
      last_proof_at_utc: ev.observed_at_utc,
    };
  if (ev.outcome === "FIN_NORMALE")
    return {
      light: "RED",
      label: "Inactif · fin normale",
      reason: "Dernière invocation terminée normalement ; aucune exécution en cours attestée.",
      last_proof_at_utc: ev.observed_at_utc,
    };
  return gray("Issue de la dernière invocation non attestée.", ev.observed_at_utc);
}
