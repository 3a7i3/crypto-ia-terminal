import { useEffect, useState } from "react";

export type PassiveSnapshotState<T> = { status: "loading" } | { status: "success"; snapshot: T } | { status: "error"; code: string };

/** Serialized GET + bounded response/JSON time; replaces prior truth on failure. */
export function usePassiveSnapshot<T>(endpoint: string, validate: (x: unknown) => x is T, known: readonly string[], prefix: string, intervalMs = 20_000): PassiveSnapshotState<T> {
  const [state, setState] = useState<PassiveSnapshotState<T>>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let requestTimer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController;
    async function load() {
      controller = new AbortController();
      let next: PassiveSnapshotState<T>;
      try {
        const request = async () => {
          const response = await fetch(endpoint, { method: "GET", signal: controller.signal });
          const body: unknown = await response.json();
          return { response, body };
        };
        const timeout = new Promise<never>((_, reject) => {
          requestTimer = setTimeout(() => { controller.abort(); reject(new Error("READ_TIMEOUT")); }, 10_000);
        });
        const { response, body } = await Promise.race([request(), timeout]);
        if (!response.ok) {
          const code = typeof body === "object" && body !== null && "error_code" in body && typeof body.error_code === "string" && known.includes(body.error_code) ? body.error_code : `${prefix}_SOURCE_ERROR`;
          next = { status: "error", code };
        } else next = validate(body) ? { status: "success", snapshot: body } : { status: "error", code: `${prefix}_CONTRACT_ERROR` };
      } catch { next = { status: "error", code: `${prefix}_TRANSPORT_ERROR` }; }
      finally { clearTimeout(requestTimer); }
      if (alive) { setState(next); timer = setTimeout(load, intervalMs); }
    }
    load();
    return () => { alive = false; controller.abort(); clearTimeout(requestTimer); if (timer !== undefined) clearTimeout(timer); };
  }, [endpoint, validate, known, prefix, intervalMs]);
  return state;
}
