/** Programmateur d'affichage (Moniteur de marché) : règle seulement le rythme de
 *  lecture de l'écran (GET). Il ne commande aucun collecteur ni service : le
 *  collecteur continue sur le serveur à son propre rythme. Le choix est mémorisé
 *  dans ce navigateur seulement (préférence d'affichage), avec repli sans stockage. */
import { useEffect, useRef, useState } from "react";

export const CADENCES = [
  { id: "live", label: "Live", ms: 5_000 },
  { id: "1m", label: "1m", ms: 60_000 },
  { id: "5m", label: "5m", ms: 300_000 },
  { id: "off", label: "Off", ms: null },
] as const;
export type CadenceId = typeof CADENCES[number]["id"];
export type Signal = "green" | "orange" | "red";
/** A read slower than this, still waiting, counts as a weak connection. */
export const SLOW_READ_MS = 3_000;
const KEY = "cat.marketMonitor.cadence";

function stored(): CadenceId {
  try { const v = window.localStorage.getItem(KEY); return CADENCES.some(c => c.id === v) ? v as CadenceId : "live"; } catch { return "live"; }
}

/** Voyant : vert = dernière lecture réussie et à l'heure pour le rythme choisi ;
 *  orange = lecture en attente au-delà de 3 s, ou dernière réussite en retard ;
 *  rouge = Off, erreur de lecture ou source non active (décidé par l'appelant). */
export function signalOf(o: { cadence: CadenceId; pendingSince: number | null; lastOk: number | null; error: boolean; sourceActive: boolean; now: number }): { signal: Signal; label: string } {
  if (o.cadence === "off") return { signal: "red", label: "Inactif · lecture arrêtée (Off)" };
  if (o.error) return { signal: "red", label: "Erreur de lecture" };
  if (o.lastOk !== null && !o.sourceActive) return { signal: "red", label: "Source inactive" };
  const ms = CADENCES.find(c => c.id === o.cadence)!.ms!;
  if (o.pendingSince !== null && o.now - o.pendingSince > SLOW_READ_MS) return { signal: "orange", label: "Connexion faible · en attente des résultats" };
  if (o.lastOk === null) return { signal: "orange", label: "En attente des premiers résultats" };
  if (o.now - o.lastOk > ms + 2 * SLOW_READ_MS) return { signal: "orange", label: "Résultats en retard" };
  return { signal: "green", label: "Connecté" };
}

/** Returns the current cadence, a setter, and a tick that changes at each due read.
 *  Reads pause while the page is hidden and resume (with an immediate read) when shown. */
export function useRefreshSchedule() {
  const [cadence, setCadenceState] = useState<CadenceId>(stored);
  const [tick, setTick] = useState(0);
  const [visible, setVisible] = useState(() => typeof document === "undefined" || document.visibilityState !== "hidden");
  const previous = useRef<{ cadence: CadenceId; visible: boolean } | null>(null);
  const setCadence = (id: CadenceId) => {
    setCadenceState(id);
    try { window.localStorage.setItem(KEY, id); } catch { /* préférence non mémorisée */ }
  };
  useEffect(() => {
    const onVisibility = () => setVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);
  useEffect(() => {
    const ms = CADENCES.find(c => c.id === cadence)!.ms;
    // Reprise ou nouveau rythme : lecture immédiate. Un même état remonté (StrictMode) ne relit pas.
    const changed = previous.current !== null && (previous.current.cadence !== cadence || previous.current.visible !== visible);
    previous.current = { cadence, visible };
    if (ms === null || !visible) return;
    if (changed) setTick(t => t + 1);
    const id = setInterval(() => setTick(t => t + 1), ms);
    return () => clearInterval(id);
  }, [cadence, visible]);
  return { cadence, setCadence, tick, readNow: () => setTick(t => t + 1) };
}
