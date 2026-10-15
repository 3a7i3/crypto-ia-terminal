// GITHUB-ROADMAP-SYNC-01 — pure reconciliation, differences and snapshot storage.
//
// A mission is linked to GitHub only through the `issue` / `pr` numbers written in the
// editorial register. GitHub states are shown beside the register's own tracks
// (integration, deployment, certification) and never overwrite them: a merged pull
// request is not a deployment and a closed issue is not a certification.
import type { WorkItem } from "./machineWorkboardRegister";
import { GITHUB_REPO, OBSERVATION_SCHEMA, type CiStatus, type GithubObservation, type IssueObs } from "./githubRoadmapReader";

export type PullState = "draft" | "open" | "merged" | "closed_unmerged";
export interface IssueFact { number: number; found: boolean; state?: "open" | "closed"; stateReason?: string | null; title?: string; labels?: string[]; milestone?: string | null; isPullRequest?: boolean }
export interface PullFact { number: number; found: boolean; state?: PullState; base?: string; headSha?: string; mergeCommitSha?: string | null; ci?: { status: CiStatus; headSha: string; failing: string[]; pending: string[] } | null }
export interface MissionFacts { missionId: string; issue: IssueFact; pr: PullFact | null; flags: string[] }
export interface Reconciliation {
  missions: MissionFacts[];
  /** Open GitHub objects that no mission cites: shown, never auto-added to the register. */
  unmappedOpen: { number: number; title: string; isPullRequest: boolean }[];
  unmappedTotal: number;
}

export const referencedPulls = (items: readonly WorkItem[]): number[] => [...new Set(items.flatMap(i => (i.pr ? [i.pr] : [])))];

const pullState = (p: { state: "open" | "closed"; draft: boolean; merged: boolean }): PullState =>
  p.merged ? "merged" : p.state === "closed" ? "closed_unmerged" : p.draft ? "draft" : "open";

export function reconcile(items: readonly WorkItem[], obs: GithubObservation): Reconciliation {
  const issues = new Map(obs.issues.map(i => [i.number, i]));
  const pulls = new Map(obs.pulls.map(p => [p.number, p]));
  const cited = new Set<number>();
  const missions = items.map((item): MissionFacts => {
    cited.add(item.issue);
    const raw = issues.get(item.issue);
    const issue: IssueFact = raw
      ? { number: raw.number, found: true, state: raw.state, stateReason: raw.stateReason, title: raw.title, labels: raw.labels, milestone: raw.milestone, isPullRequest: raw.isPullRequest }
      : { number: item.issue, found: false };
    let pr: PullFact | null = null;
    if (item.pr) {
      cited.add(item.pr);
      const p = pulls.get(item.pr);
      const checks = p ? obs.checks[p.headSha] : undefined;
      pr = p
        ? { number: p.number, found: true, state: pullState(p), base: p.base, headSha: p.headSha, mergeCommitSha: p.mergeCommitSha,
            // CI is read only from the check runs of this exact head; a missing read stays UNKNOWN.
            ci: checks && checks.headSha === p.headSha ? { status: checks.status, headSha: checks.headSha, failing: checks.failing, pending: checks.pending } : { status: "UNKNOWN", headSha: p.headSha, failing: [], pending: [] } }
        : { number: item.pr, found: false };
    }
    return { missionId: item.id, issue, pr, flags: flagsFor(item, issue, pr) };
  });
  const unmapped: IssueObs[] = obs.issues.filter(i => !cited.has(i.number));
  return {
    missions,
    unmappedOpen: unmapped.filter(i => i.state === "open").map(i => ({ number: i.number, title: i.title, isPullRequest: i.isPullRequest })),
    unmappedTotal: unmapped.length,
  };
}

/** Informational gaps only ("à vérifier"). They never edit a register field. */
function flagsFor(item: WorkItem, issue: IssueFact, pr: PullFact | null): string[] {
  const flags: string[] = [];
  if (!issue.found) flags.push(`Issue #${item.issue} absente du relevé.`);
  else if (issue.state === "closed" && item.status !== "done") flags.push(`Issue #${item.issue} fermée alors que le registre ne donne pas la mission terminée (une issue fermée n'est pas une preuve).`);
  if (pr) {
    if (!pr.found) flags.push(`PR #${pr.number} introuvable dans le relevé.`);
    else if (pr.state === "closed_unmerged") flags.push(`PR #${pr.number} fermée sans fusion.`);
    else if (pr.state === "draft" || pr.state === "open") {
      if (item.status === "done") flags.push(`Registre « terminé » mais PR #${pr.number} non fusionnée.`);
      if (item.integration === "MERGED_SOURCE") flags.push(`Intégration source déclarée au registre, PR #${pr.number} non fusionnée.`);
    } else if (pr.state === "merged" && item.integration !== "MERGED_SOURCE") {
      flags.push(`PR #${pr.number} fusionnée ; l'intégration source n'est pas confirmée au registre (rien n'est modifié automatiquement).`);
    }
  }
  return flags;
}

// ── Differences ────────────────────────────────────────────────────────────────
export interface DiffEntry { missionId: string; field: string; before: string; after: string }
export interface SyncDiff {
  first: boolean;
  entries: DiffEntry[];
  unmappedBefore: number | null; unmappedAfter: number;
  /** Flags present in the candidate (they describe the register vs GitHub, not a change). */
  flaggedMissions: number;
}
const same = (v: unknown): string => (v === undefined || v === null ? "—" : Array.isArray(v) ? (v.length ? v.join(", ") : "—") : String(v));
/** Compare on full values; only the display shortens a SHA. */
const show = (v: string): string => (/^[0-9a-f]{40}$/.test(v) ? v.slice(0, 7) : v);

function fields(m: MissionFacts): Record<string, unknown> {
  return {
    "issue.trouvée": m.issue.found, "issue.état": m.issue.state, "issue.raison": m.issue.stateReason, "issue.titre": m.issue.title,
    "issue.labels": m.issue.labels, "issue.jalon": m.issue.milestone,
    "pr.trouvée": m.pr?.found, "pr.état": m.pr?.state, "pr.base": m.pr?.base, "pr.head": m.pr?.headSha, "pr.fusion": m.pr?.mergeCommitSha,
    "ci.état": m.pr?.ci?.status, "ci.échecs": m.pr?.ci?.failing, "ci.en attente": m.pr?.ci?.pending,
  };
}

export function diffObservations(items: readonly WorkItem[], previous: GithubObservation | null, next: GithubObservation): SyncDiff {
  const after = reconcile(items, next);
  const flaggedMissions = after.missions.filter(m => m.flags.length).length;
  if (!previous) return { first: true, entries: [], unmappedBefore: null, unmappedAfter: after.unmappedTotal, flaggedMissions };
  const before = reconcile(items, previous);
  const byId = new Map(before.missions.map(m => [m.missionId, m]));
  const entries: DiffEntry[] = [];
  for (const m of after.missions) {
    const old = byId.get(m.missionId);
    if (!old) continue;
    const a = fields(old), b = fields(m);
    for (const key of Object.keys(b)) if (same(a[key]) !== same(b[key])) entries.push({ missionId: m.missionId, field: key, before: show(same(a[key])), after: show(same(b[key])) });
  }
  return { first: false, entries, unmappedBefore: before.unmappedTotal, unmappedAfter: after.unmappedTotal, flaggedMissions };
}

// ── Last successful snapshot (per-browser convenience, never authority) ────────
export const SNAPSHOT_STORAGE_KEY = "workboard.github-snapshot.v1";

const obj = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const strs = (x: unknown): x is string[] => Array.isArray(x) && x.every(v => typeof v === "string");
const ints = (x: unknown): x is number[] => Array.isArray(x) && x.every(v => Number.isSafeInteger(v) && v > 0);
const shaOk = (x: unknown) => typeof x === "string" && /^[0-9a-f]{40}$/.test(x);
const CI = new Set(["SUCCESS", "FAILURE", "PENDING", "NONE", "UNKNOWN"]);

export function validateObservation(x: unknown): x is GithubObservation {
  if (!obj(x) || x.schema !== OBSERVATION_SCHEMA || x.repo !== GITHUB_REPO || x.source !== "api.github.com/unauthenticated-read-only") return false;
  if (typeof x.observedAt !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(x.observedAt) || !Number.isFinite(Date.parse(x.observedAt))) return false;
  if (typeof x.complete !== "boolean" || !Number.isSafeInteger(x.requestCount) || !Array.isArray(x.errors) || !strs(x.labels) || !strs(x.milestones) || !ints(x.missingPulls)) return false;
  if (x.rateLimit !== null && !(obj(x.rateLimit) && Number.isFinite(x.rateLimit.limit) && Number.isFinite(x.rateLimit.remaining))) return false;
  if (!Array.isArray(x.issues) || !x.issues.every(i => obj(i) && Number.isSafeInteger(i.number) && (i.state === "open" || i.state === "closed") && typeof i.title === "string" && typeof i.isPullRequest === "boolean" && strs(i.labels) && (i.milestone === null || typeof i.milestone === "string") && (i.stateReason === null || typeof i.stateReason === "string"))) return false;
  if (!Array.isArray(x.pulls) || !x.pulls.every(p => obj(p) && Number.isSafeInteger(p.number) && (p.state === "open" || p.state === "closed") && typeof p.draft === "boolean" && typeof p.merged === "boolean" && shaOk(p.headSha) && typeof p.base === "string" && (p.mergeCommitSha === null || shaOk(p.mergeCommitSha)))) return false;
  return obj(x.checks) && Object.entries(x.checks).every(([sha, c]) => shaOk(sha) && obj(c) && c.headSha === sha && typeof c.status === "string" && CI.has(c.status) && strs(c.failing) && strs(c.pending));
}

export function loadSnapshot(storage: Pick<Storage, "getItem"> | null = safeStorage()): GithubObservation | null {
  try {
    const raw = storage?.getItem(SNAPSHOT_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return validateObservation(parsed) && parsed.complete ? parsed : null;
  } catch { return null; }
}
/** Only complete observations are ever stored. Returns false when the browser refuses. */
export function saveSnapshot(obs: GithubObservation, storage: Pick<Storage, "setItem"> | null = safeStorage()): boolean {
  if (!obs.complete) return false;
  try { storage?.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify(obs)); return !!storage; } catch { return false; }
}
function safeStorage(): Storage | null { try { return window.localStorage; } catch { return null; } }
