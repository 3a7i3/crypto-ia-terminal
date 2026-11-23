// ── Programmateur d'un agent d'observation (cartographe, Data Provenance Auditor) ──
// SEULE écriture de l'interface (exception gouvernée, opérateur, 2026-11-22 07:23Z).
// Le bouton dépose une DEMANDE de rythme (liste fermée) ; un applicateur root sur le serveur
// l'applique au timer et publie l'état appliqué. L'interface n'affiche comme « appliqué » que
// ce que le serveur publie ; une demande non encore appliquée est montrée « en attente ».
import React, { useCallback, useEffect, useRef, useState } from "react";
import { CARTOGRAPHER_INVOCATION_URL, parseUtc } from "./invocationEvidence";

export const CARTOGRAPHER_SCHEDULE_URL = `${CARTOGRAPHER_INVOCATION_URL}/schedule`;
export const SCHEDULE_POLL_MS = 15_000;
const TEST_ON = import.meta.env.VITE_CARTOGRAPHER_SCHEDULE_TEST === "1";
export const MENU: { value: string; label: string }[] = [
  ...(TEST_ON ? [{ value: "1min", label: "1 min (test)" }] : []),
  { value: "10min", label: "10 min" },
  { value: "1h", label: "1 h" },
  { value: "off", label: "Off" },
];
export const RHYTHM_LABEL: Record<string, string> = { "1min": "1 min", "10min": "10 min", "1h": "1 h", off: "arrêt complet" };

export interface ScheduleState {
  requested: string | null;
  applied: string | null;
  next_utc: string | null;
  connection: string;
}

export function useAgentSchedule(enabled: boolean, pollMs = SCHEDULE_POLL_MS, url = CARTOGRAPHER_SCHEDULE_URL) {
  const [state, setState] = useState<ScheduleState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const kick = useRef<() => void>(() => undefined);

  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (timer) clearTimeout(timer);
      try {
        const r = await fetch(url, { cache: "no-store" });
        const b = r.ok ? await r.json() : null;
        if (alive && b && typeof b === "object") {
          setState({
            requested: typeof b.requested === "string" ? b.requested : null,
            applied: typeof b.applied === "string" ? b.applied : null,
            next_utc: parseUtc(b.next_utc) !== null ? b.next_utc : null,
            connection: typeof b.connection === "string" ? b.connection : "UNREADABLE",
          });
        } else if (alive) setState(null);
      } catch {
        if (alive) setState(null);
      } finally {
        if (alive) timer = setTimeout(() => void tick(), pollMs);
      }
    };
    kick.current = () => void tick();
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [enabled, pollMs, url]);

  const request = useCallback(async (rhythm: string) => {
    setSending(true);
    setError(null);
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json", "x-cat-operator": "schedule" },
        body: JSON.stringify({ rhythm }),
      });
      if (r.status !== 202) setError(`demande refusée (HTTP ${r.status})`);
    } catch {
      setError("demande non transmise (coupure)");
    } finally {
      setSending(false);
      kick.current();
      // L'applicateur agit en quelques secondes : relire peu après.
      setTimeout(() => kick.current(), 3_000);
    }
  }, [url]);

  return { schedule: state, error, sending, request };
}

const fmt = (utc: string) =>
  new Date(parseUtc(utc) as number).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const ScheduleControl: React.FC<{
  schedule: ScheduleState | null;
  error: string | null;
  sending: boolean;
  onPick: (v: string) => void;
}> = ({ schedule, error, sending, onPick }) => {
  const [open, setOpen] = useState(false);
  const applied = schedule?.applied ?? null;
  const pending = schedule?.requested && schedule.requested !== applied ? schedule.requested : null;
  return (
    <div className="miniterm-rythme">
      <span data-testid="schedule-label">
        Rythme : <b>{applied ? RHYTHM_LABEL[applied] ?? applied : "non publié"}</b>
        {applied && applied !== "off" && schedule?.next_utc ? <> · prochain <b>{fmt(schedule.next_utc)}</b></> : null}
        {pending ? <span className="miniterm-pending"> · demande {RHYTHM_LABEL[pending] ?? pending} en attente</span> : null}
        {error ? <span className="miniterm-pending"> · {error}</span> : null}
      </span>
      <div className="miniterm-dd">
        <button
          type="button"
          className="miniterm-clock"
          data-testid="schedule-clock"
          aria-haspopup="menu"
          aria-expanded={open}
          disabled={sending}
          onClick={() => setOpen((o) => !o)}
        >
          ⏰ ▾
        </button>
        {open ? (
          <div className="miniterm-menu" role="menu">
            {MENU.map((m) => (
              <button
                key={m.value}
                type="button"
                role="menuitem"
                data-testid={`schedule-${m.value}`}
                className={applied === m.value ? "is-current" : undefined}
                onClick={() => {
                  setOpen(false);
                  onPick(m.value);
                }}
              >
                {m.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
};
