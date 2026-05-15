// Polling hook — refetch toutes les `ms` millisecondes
import { useState, useEffect } from "react";

export interface PollState<T> {
  data: T | null;
  loading: boolean;
  error: boolean;
}

export function usePolling<T>(url: string, ms = 20_000): PollState<T> {
  const [data, setData]       = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => {
      fetch(url)
        .then(r => {
          if (!r.ok) throw new Error(r.statusText);
          return r.json() as Promise<T>;
        })
        .then(j => { if (alive) { setData(j); setLoading(false); setError(false); } })
        .catch(() => { if (alive) { setLoading(false); setError(true); } });
    };
    load();
    const id = setInterval(load, ms);
    return () => { alive = false; clearInterval(id); };
  }, [url, ms]);

  return { data, loading, error };
}
