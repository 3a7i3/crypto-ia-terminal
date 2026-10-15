import { useCallback, useEffect, useRef, useState } from "react";
import { collectGithubObservation, type GithubObservation } from "./githubRoadmapReader";
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
      .finally(() => { busy.current = false; if (!ctl.signal.aborted) setLoading(false); });
  }, []);

  const apply = useCallback(() => {
    setCandidate(c => {
      if (!c || !c.observation.complete) return c;
      setStorageWarning(!saveSnapshot(c.observation));
      setActive(c.observation);
      return null;
    });
  }, []);
  const discard = useCallback(() => setCandidate(null), []);
  return { active, candidate, loading, storageWarning, refresh, apply, discard };
}
