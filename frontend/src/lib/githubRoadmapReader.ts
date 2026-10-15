// GITHUB-ROADMAP-SYNC-01 — read-only, unauthenticated GitHub reader.
//
// Only GET requests to api.github.com for one fixed repository. No credential is
// ever attached. Issue/PR bodies and comments are never requested: only titles,
// states, labels, milestones, head SHAs and check runs, which are GitHub content
// to display as text, never instructions. Anything that fails is recorded in
// `errors` and marks the observation incomplete; nothing is silently dropped.

export const GITHUB_REPO = "3a7i3/crypto-ia-terminal";
export const OBSERVATION_SCHEMA = "github-roadmap-observation/1";
const API = "https://api.github.com";

export type SyncErrorCode =
  | "NETWORK" | "RATE_LIMITED" | "RATE_LIMIT_INSUFFICIENT" | "HTTP_ERROR" | "INVALID_RESPONSE"
  | "TRUNCATED" | "BUDGET_EXCEEDED" | "NOT_FOUND" | "NOT_FETCHED" | "CHECKS_MISMATCH" | "ABORTED";
export interface SyncError { code: SyncErrorCode; scope: string; message: string; status?: number }

export interface IssueObs {
  number: number; title: string; state: "open" | "closed"; stateReason: string | null; isPullRequest: boolean;
  labels: string[]; milestone: string | null; updatedAt: string;
}
export interface PullObs {
  number: number; title: string; state: "open" | "closed"; draft: boolean; merged: boolean; base: string;
  headSha: string; mergeCommitSha: string | null; mergedAt: string | null; updatedAt: string;
}
export type CiStatus = "SUCCESS" | "FAILURE" | "PENDING" | "NONE" | "UNKNOWN";
export interface ChecksObs {
  headSha: string; status: CiStatus; total: number; failing: string[]; pending: string[];
}
export interface RateLimitObs { limit: number; remaining: number; resetAt: string | null }
export interface GithubObservation {
  schema: typeof OBSERVATION_SCHEMA; repo: string; observedAt: string; source: "api.github.com/unauthenticated-read-only";
  requestCount: number; rateLimit: RateLimitObs | null; complete: boolean; errors: SyncError[];
  issues: IssueObs[]; pulls: PullObs[]; labels: string[]; milestones: string[];
  /** Register-cited pull requests that GitHub answered 404 for (a finding, not an error). */
  missingPulls: number[];
  /** Keyed by the exact head SHA of a pull request. */
  checks: Record<string, ChecksObs>;
}

export interface ReaderOptions {
  fetchImpl: typeof fetch;
  now?: () => Date;
  /** Pull requests the register refers to; open PRs are always read as well. */
  referencedPulls: readonly number[];
  maxRequests?: number;
  maxPagesPerList?: number;
  signal?: AbortSignal;
}
/** Anonymous quota is 60/h per IP; stay under it and refuse to start below this reserve. */
export const DEFAULT_MAX_REQUESTS = 55;
const MIN_QUOTA_TO_START = 12;
const FAILING = new Set(["failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"]);
const OK = new Set(["success", "neutral", "skipped"]);

const isObj = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const isInt = (x: unknown): x is number => typeof x === "number" && Number.isSafeInteger(x) && x > 0;
const isSha = (x: unknown): x is string => typeof x === "string" && /^[0-9a-f]{40}$/.test(x);
const text = (x: unknown, max = 300): string | null => (typeof x === "string" ? x.slice(0, max) : null);
const iso = (x: unknown): string | null => (typeof x === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(x) ? x : null);
const nextLink = (header: string | null): string | null => {
  const m = header?.split(",").map(part => part.match(/<([^>]+)>\s*;\s*rel="next"/)).find(Boolean);
  return m ? m[1] : null;
};

class Stop extends Error {}

export async function collectGithubObservation(opts: ReaderOptions): Promise<GithubObservation> {
  const now = opts.now ?? (() => new Date());
  const maxRequests = opts.maxRequests ?? DEFAULT_MAX_REQUESTS;
  const maxPages = opts.maxPagesPerList ?? 10;
  const errors: SyncError[] = [];
  const obs: GithubObservation = {
    schema: OBSERVATION_SCHEMA, repo: GITHUB_REPO, observedAt: now().toISOString().slice(0, 19) + "Z",
    source: "api.github.com/unauthenticated-read-only", requestCount: 0, rateLimit: null, complete: false, errors,
    issues: [], pulls: [], labels: [], milestones: [], missingPulls: [], checks: {},
  };
  let halted = false;
  const fail = (e: SyncError) => { errors.push(e); };

  const readRate = (res: Response) => {
    const limit = Number(res.headers.get("x-ratelimit-limit")), remaining = Number(res.headers.get("x-ratelimit-remaining"));
    const reset = Number(res.headers.get("x-ratelimit-reset"));
    if (res.headers.get("x-ratelimit-limit") !== null && Number.isFinite(limit) && Number.isFinite(remaining)) {
      obs.rateLimit = { limit, remaining, resetAt: Number.isFinite(reset) && reset > 0 ? new Date(reset * 1000).toISOString().slice(0, 19) + "Z" : null };
    }
  };

  /** One GET. Returns parsed JSON + Link header, or null after recording the error. */
  async function get(url: string, scope: string, counted = true, allow404 = false): Promise<{ json: unknown; link: string | null } | null> {
    if (halted) { fail({ code: "NOT_FETCHED", scope, message: "Requête non envoyée : relevé interrompu." }); return null; }
    if (opts.signal?.aborted) { halted = true; fail({ code: "ABORTED", scope, message: "Relevé annulé." }); return null; }
    if (counted && obs.requestCount >= maxRequests) {
      halted = true; fail({ code: "BUDGET_EXCEEDED", scope, message: `Budget de ${maxRequests} requêtes atteint.` }); return null;
    }
    if (counted) obs.requestCount += 1;
    let res: Response;
    try {
      res = await opts.fetchImpl(url, {
        method: "GET", headers: { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
        cache: "no-cache", credentials: "omit", signal: opts.signal,
      });
    } catch (e) {
      halted = true;
      fail({ code: opts.signal?.aborted ? "ABORTED" : "NETWORK", scope, message: e instanceof Error ? e.message.slice(0, 160) : "Erreur réseau." });
      return null;
    }
    readRate(res);
    if (res.status === 403 || res.status === 429) {
      const exhausted = res.headers.get("x-ratelimit-remaining") === "0" || res.headers.get("retry-after") !== null;
      halted = true;
      fail({ code: exhausted ? "RATE_LIMITED" : "HTTP_ERROR", scope, status: res.status,
        message: exhausted ? `Quota GitHub épuisé${obs.rateLimit?.resetAt ? ` jusqu'à ${obs.rateLimit.resetAt}` : ""}.` : `GitHub a refusé la requête (${res.status}).` });
      return null;
    }
    if (res.status === 404) { if (!allow404) fail({ code: "NOT_FOUND", scope, status: 404, message: "Objet introuvable sur GitHub." }); return null; }
    if (!res.ok) { fail({ code: "HTTP_ERROR", scope, status: res.status, message: `Réponse HTTP ${res.status}.` }); return null; }
    try {
      return { json: await res.json(), link: res.headers.get("link") };
    } catch {
      if (opts.signal?.aborted) { halted = true; fail({ code: "ABORTED", scope, message: "Relevé annulé." }); return null; }
      fail({ code: "INVALID_RESPONSE", scope, message: "Réponse non JSON." });
      return null;
    }
  }

  /** Follow `rel="next"` up to maxPages; a remaining next page is a TRUNCATED error. */
  async function paged(path: string, scope: string, pick: (json: unknown) => unknown[] | null): Promise<unknown[]> {
    const out: unknown[] = [];
    let url: string | null = `${API}${path}`;
    for (let page = 1; url; page += 1) {
      if (page > maxPages) { fail({ code: "TRUNCATED", scope, message: `Plus de ${maxPages} pages : liste tronquée.` }); break; }
      const r = await get(url, `${scope}#${page}`);
      if (!r) { if (halted) throw new Stop(); break; }
      const items = pick(r.json);
      if (!items) { fail({ code: "INVALID_RESPONSE", scope: `${scope}#${page}`, message: "Forme de réponse inattendue." }); break; }
      out.push(...items);
      const next = nextLink(r.link);
      url = next && next.startsWith(`${API}/`) ? next : null;
    }
    return out;
  }
  const arr = (j: unknown) => (Array.isArray(j) ? j : null);
  const repo = `/repos/${GITHUB_REPO}`;

  const parseIssue = (x: unknown): IssueObs | null => {
    if (!isObj(x) || !isInt(x.number) || (x.state !== "open" && x.state !== "closed")) return null;
    const labels = Array.isArray(x.labels) ? x.labels.map(l => (isObj(l) ? text(l.name, 80) : typeof l === "string" ? l.slice(0, 80) : null)).filter((l): l is string => !!l) : [];
    return {
      number: x.number, title: text(x.title) ?? "", state: x.state, stateReason: text(x.state_reason, 40), isPullRequest: isObj(x.pull_request),
      labels, milestone: isObj(x.milestone) ? text(x.milestone.title, 120) : null, updatedAt: iso(x.updated_at) ?? "",
    };
  };
  const parsePull = (x: unknown): PullObs | null => {
    if (!isObj(x) || !isInt(x.number) || (x.state !== "open" && x.state !== "closed") || !isObj(x.head) || !isSha(x.head.sha) || !isObj(x.base)) return null;
    return {
      number: x.number, title: text(x.title) ?? "", state: x.state, draft: x.draft === true, merged: typeof x.merged_at === "string" && x.merged_at.length > 0,
      base: text(x.base.ref, 100) ?? "", headSha: x.head.sha, mergeCommitSha: isSha(x.merge_commit_sha) && typeof x.merged_at === "string" ? (x.merge_commit_sha as string) : null,
      mergedAt: typeof x.merged_at === "string" ? x.merged_at : null, updatedAt: iso(x.updated_at) ?? "",
    };
  };

  async function checksFor(sha: string): Promise<ChecksObs | null> {
    const scope = `checks:${sha.slice(0, 7)}`;
    let total = 0;
    const errorsBefore = errors.length;
    const runs = await paged(`${repo}/commits/${sha}/check-runs?per_page=100`, scope, j => {
      if (!isObj(j) || !Array.isArray(j.check_runs) || !Number.isSafeInteger(j.total_count)) return null;
      total = j.total_count as number;
      return j.check_runs;
    });
    if (errors.length > errorsBefore) return null; // a failed read is UNKNOWN, never "no checks"
    const failing: string[] = [], pending: string[] = [];
    let ok = 0;
    for (const run of runs) {
      if (!isObj(run) || run.head_sha !== sha) { fail({ code: "CHECKS_MISMATCH", scope, message: "Un contrôle ne porte pas le HEAD demandé : ignoré." }); return null; }
      const name = text(run.name, 100) ?? "(sans nom)";
      if (run.status !== "completed") pending.push(name);
      else if (typeof run.conclusion === "string" && FAILING.has(run.conclusion)) failing.push(name);
      else if (typeof run.conclusion === "string" && OK.has(run.conclusion)) ok += 1;
      else { fail({ code: "INVALID_RESPONSE", scope, message: `Conclusion inconnue pour « ${name} ».` }); return null; }
    }
    if (runs.length !== total) { fail({ code: "TRUNCATED", scope, message: "Contrôles incomplets pour ce HEAD." }); return null; }
    const status: CiStatus = failing.length ? "FAILURE" : pending.length ? "PENDING" : ok > 0 ? "SUCCESS" : "NONE";
    return { headSha: sha, status, total, failing, pending };
  }

  try {
    // Pre-flight: /rate_limit is not counted by GitHub, so it can refuse before any quota is spent.
    const rl = await get(`${API}/rate_limit`, "rate_limit", false);
    if (!rl) throw new Stop();
    const core = isObj(rl.json) && isObj(rl.json.resources) && isObj(rl.json.resources.core) ? rl.json.resources.core : null;
    if (core && Number.isFinite(core.remaining) && Number.isFinite(core.limit)) {
      const reset = Number(core.reset);
      obs.rateLimit = { limit: core.limit as number, remaining: core.remaining as number, resetAt: Number.isFinite(reset) && reset > 0 ? new Date(reset * 1000).toISOString().slice(0, 19) + "Z" : null };
      if ((core.remaining as number) < MIN_QUOTA_TO_START) {
        fail({ code: "RATE_LIMIT_INSUFFICIENT", scope: "rate_limit", message: `Quota restant (${core.remaining}) insuffisant pour un relevé complet${obs.rateLimit.resetAt ? ` ; réinitialisation à ${obs.rateLimit.resetAt}` : ""}.` });
        throw new Stop();
      }
    }

    obs.labels = (await paged(`${repo}/labels?per_page=100`, "labels", arr)).map(l => (isObj(l) ? text(l.name, 80) : null)).filter((l): l is string => !!l);
    obs.milestones = (await paged(`${repo}/milestones?state=all&per_page=100`, "milestones", arr)).map(m => (isObj(m) ? text(m.title, 120) : null)).filter((m): m is string => !!m);
    for (const raw of await paged(`${repo}/issues?state=all&per_page=100&sort=created&direction=asc`, "issues", arr)) {
      const issue = parseIssue(raw);
      if (issue) obs.issues.push(issue); else fail({ code: "INVALID_RESPONSE", scope: "issues", message: "Une entrée d'issue est invalide : ignorée." });
    }
    for (const raw of await paged(`${repo}/pulls?state=open&per_page=100`, "pulls:open", arr)) {
      const pull = parsePull(raw);
      if (pull) obs.pulls.push(pull); else fail({ code: "INVALID_RESPONSE", scope: "pulls:open", message: "Une PR est invalide : ignorée." });
    }
    const have = new Set(obs.pulls.map(p => p.number));
    const missing = [...new Set(opts.referencedPulls)].filter(n => !have.has(n));
    // Know the remaining cost before spending it: one GET per missing PR, one or more check-run reads per PR.
    const needed = missing.length * 2 + have.size;
    const affordable = Math.min(obs.rateLimit?.remaining ?? Infinity, maxRequests - obs.requestCount);
    if (affordable < needed) {
      fail({ code: obs.rateLimit && obs.rateLimit.remaining < maxRequests - obs.requestCount ? "RATE_LIMIT_INSUFFICIENT" : "BUDGET_EXCEEDED", scope: "details", message: `Il reste ${affordable} requêtes pour ${needed} détails nécessaires.` });
      throw new Stop();
    }
    for (const n of missing) {
      const before = errors.length;
      const r = await get(`${API}${repo}/pulls/${n}`, `pull:${n}`, true, true);
      if (!r) {
        if (halted) throw new Stop();
        // A 404 on a PR the register cites is a finding to show, not a failed sync.
        if (errors.length === before) obs.missingPulls.push(n);
        continue;
      }
      const pull = parsePull(r.json);
      if (pull && pull.number === n) obs.pulls.push(pull);
      else fail({ code: "INVALID_RESPONSE", scope: `pull:${n}`, message: "Réponse de PR invalide." });
    }
    for (const sha of [...new Set(obs.pulls.map(p => p.headSha))]) {
      const checks = await checksFor(sha);
      if (checks) obs.checks[sha] = checks;
    }
  } catch (e) {
    if (!(e instanceof Stop)) throw e;
  }
  obs.complete = errors.length === 0;
  return obs;
}
