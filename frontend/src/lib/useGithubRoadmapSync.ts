import { useCallback, useEffect, useRef, useState } from "react";
import { collectGithubObservation, OBSERVATION_SCHEMA, GITHUB_REPO, type GithubObservation } from "./githubRoadmapReader";
import { diffObservations, loadSnapshot, referencedPulls, saveSnapshot, type SyncDiff } from "./githubRoadmapReconcile";
import { WORK_ITEMS } from "./machineWorkboardRegister";

export interface Candidate { observation: GithubObservation; diff: SyncDiff }
export interface GithubSyncState {
  /** Last successful, applied snapshot. Never cleared by a failed refresh. */
  active: GithubObservation | null;
  candidate: Candidate | null;
  loading: boolean;
  storageWarning: boolean;
  refresh: () => void;
  apply: () => void;
  discard: () => void;
}

export function useGithubRoadmapSync(): GithubSyncState {
  const [active, setActive] = useState<GithubObservation | null>(() => loadSnapshot());
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [loading, setLoading] = useState(false);
  const [storageWarning, setStorageWarning] = useState(false);
  const busy = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  useEffect(() => () => controller.current?.abort(), []);

  const refresh = useCallback(() => {
    if (busy.current) return;
    busy.current = true;
    setLoading(true);
    setCandidate(null);
    const ctl = new AbortController();
    controller.current = ctl;
    collectGithubObservation({ fetchImpl: (input, init) => fetch(input, init), referencedPulls: referencedPulls(WORK_ITEMS), signal: ctl.signal })
      .then(observation => {
        if (ctl.signal.aborted) return;
        setCandidate({ observation, diff: diffObservations(WORK_ITEMS, activeRef.current, observation) });
      })
      .catch(e => {
        if (ctl.signal.aborted) return;
        // An unexpected failure is shown as an incomplete, non-applicable observation; the active snapshot is untouched.
        const failed: GithubObservation = {
          schema: OBSERVATION_SCHEMA, repo: GITHUB_REPO, observedAt: new Date().toISOString().slice(0, 19) + "Z",
          source: "api.github.com/unauthenticated-read-only", requestCount: 0, rateLimit: null, complete: false,
          errors: [{ code: "INVALID_RESPONSE", scope: "sync", message: e instanceof Error ? e.message.slice(0, 160) : "Erreur inattendue." }],
          issues: [], pulls: [], labels: [], milestones: [], missingPulls: [], checks: {},
        };
        setCandidate({ observation: failed, diff: { first: true, entries: [], unmappedBefore: null, unmappedAfter: 0, flaggedMissions: 0 } });
      })
      .finally(() => { busy.current = false; if (!ctl.signal.aborted) setLoading(false); });
  }, []);

  const candidateRef = useRef<Candidate | null>(null);
  candidateRef.current = candidate;
  const apply = useCallback(() => {
    const c = candidateRef.current;
    if (!c || !c.observation.complete) return;
    candidateRef.current = null; // a second click before re-render cannot apply it twice
    setStorageWarning(!saveSnapshot(c.observation));
    setActive(c.observation);
    setCandidate(null);
  }, []);
  const discard = useCallback(() => setCandidate(null), []);
  return { active, candidate, loading, storageWarning, refresh, apply, discard };
}
