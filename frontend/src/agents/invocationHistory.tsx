// ── Mini terminal d'un agent d'observation (lecture seule) ─────────────────
//
// Une bulle par rapport publié, heure de production en bas (heure du navigateur).
// Source : GET /agent-invocations/<agent>/history (20 plus récents) ; cartographe par défaut,
// Data Provenance Auditor depuis le 2026-11-23 (même bloc).
// L'interface ne recalcule rien : elle valide, formate et affiche les verdicts serveur ;
// une entrée non valide reste visible comme telle. Une panne de lecture n'est pas une
// liste vide. Le gyrophare reprend le voyant du contrat partagé (vert/rouge/gris).
import React, { useEffect, useState } from "react";
import type { ActivityLight } from "./agentRegistry";
import { CARTOGRAPHER_INVOCATION_URL, INVOCATION_CONTRACT, parseUtc } from "./invocationEvidence";

export const CARTOGRAPHER_HISTORY_URL = `${CARTOGRAPHER_INVOCATION_URL}/history`;
export const HISTORY_POLL_MS = 30_000;

export interface HistoryItem {
  verdict: string;
  reason: string | null;
  invocation_id?: string;
  ended_utc?: string;
  started_utc?: string;
  state?: string;
  result_status?: string | null;
  analysed_sha?: string;
  content_sha256?: string | null;
  summary?: {
    seen: { sources: number; imports: number; calls: number };
    found: string[];
    not_concluded: { path: string | null; line: number | null; reason: string | null }[];
    write_templates: number;
    limits: number;
    errors: string[];
    /** Chaîne de provenance (Data Provenance Auditor seulement) : maillons et niveaux de preuve. */
    chain?: { links: number; levels: Record<string, number>; hops?: { hop: string; level: string }[]; inferred: number; runtime_required: number };
    /** Observateur de données runtime : un contrôle par ligne, verdict du serveur affiché tel quel. */
    checks?: { code: string; verdict: string; observed: string | number | boolean | null; note: string | null }[];
    verdict_counts?: Record<string, number> | null;
    domain?: string | null;
  };
}
export type HistoryState =
  | { status: "LOADING" }
  | { status: "UNREACHABLE"; reason: string }
  | { status: "OK"; connection: string; connection_reason: string | null; total: number | null; items: HistoryItem[] };

export function parseHistory(raw: unknown): HistoryState {
  const bad = (reason: string): HistoryState => ({ status: "UNREACHABLE", reason });
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return bad("réponse non objet");
  const r = raw as Record<string, unknown>;
  if (r.contract !== INVOCATION_CONTRACT || r.read_only !== true) return bad("contrat inconnu");
  if (typeof r.connection !== "string" || !Array.isArray(r.items)) return bad("historique invalide");
  const items: HistoryItem[] = [];
  for (const it of r.items) {
    if (typeof it !== "object" || it === null || typeof (it as HistoryItem).verdict !== "string") return bad("entrée invalide");
    const h = it as HistoryItem;
    if (h.verdict === "VALID" && (parseUtc(h.ended_utc) === null || typeof h.summary !== "object")) return bad("entrée valide incomplète");
    items.push(h);
  }
  return {
    status: "OK",
    connection: r.connection,
    connection_reason: typeof r.connection_reason === "string" ? r.connection_reason : null,
    total: typeof r.total === "number" ? r.total : null,
    items,
  };
}

export function useInvocationHistory(enabled: boolean, pollMs = HISTORY_POLL_MS, url = CARTOGRAPHER_HISTORY_URL): HistoryState {
  const [state, setState] = useState<HistoryState>({ status: "LOADING" });
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let ctrl: AbortController | null = null;
    const tick = async () => {
      ctrl = new AbortController();
      const guard = setTimeout(() => ctrl?.abort(), 10_000);
      try {
        const res = await fetch(url, { cache: "no-store", signal: ctrl.signal });
        const next = res.ok ? parseHistory(await res.json()) : { status: "UNREACHABLE" as const, reason: `HTTP ${res.status}` };
        if (alive) setState(next);
      } catch {
        if (alive) setState({ status: "UNREACHABLE", reason: "coupure API" });
      } finally {
        clearTimeout(guard);
        if (alive) timer = setTimeout(() => void tick(), pollMs);
      }
    };
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
      ctrl?.abort();
    };
  }, [enabled, pollMs, url]);
  return state;
}

const fmtTime = (utc: string) =>
  new Date(parseUtc(utc) as number).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const fmtDay = (utc: string) => new Date(parseUtc(utc) as number).toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
const durS = (a?: string, b?: string) => {
  const x = parseUtc(a), y = parseUtc(b);
  return x !== null && y !== null ? `${((y - x) / 1000).toLocaleString("fr-FR")} s` : null;
};

const Bubble: React.FC<{ item: HistoryItem; previous?: HistoryItem }> = ({ item, previous }) => {
  if (item.verdict !== "VALID" || !item.summary || !item.ended_utc) {
    return (
      <div className="miniterm-msg miniterm-msg-bad" data-testid="miniterm-bubble" data-verdict={item.verdict}>
        <div className="miniterm-title">Preuve {item.verdict}</div>
        {item.reason ?? "motif non fourni"}
      </div>
    );
  }
  const s = item.summary;
  const same = previous?.content_sha256 && previous.content_sha256 === item.content_sha256;
  const d = durS(item.started_utc, item.ended_utc);
  return (
    <div className="miniterm-msg" data-testid="miniterm-bubble" data-verdict="VALID">
      <div className="miniterm-title">
        Rapport · <span className={`miniterm-status-${item.result_status ?? "none"}`}>{item.result_status ?? "sans résultat"}</span> · {item.state}
      </div>
      {same ? (
        <div>Identique au précédent (révision analysée {item.analysed_sha?.slice(0, 8)} inchangée).</div>
      ) : s.checks ? (
        <ul data-testid="miniterm-checks">
          <li>
            <b>Contrôles</b> : {(["OK", "WARN", "ALERT", "UNKNOWN"] as const)
              .map((v) => `${s.verdict_counts?.[v] ?? "?"} ${v}`)
              .join(" · ")}
          </li>
          {s.checks
            .filter((k) => k.verdict !== "OK")
            .map((k) => (
              <li key={k.code} className={`miniterm-check miniterm-check-${k.verdict}`}>
                <b>{k.verdict}</b> {k.code}
                {k.observed !== null ? ` = ${String(k.observed)}` : ""}
                {k.note ? ` · ${k.note}` : ""}
              </li>
            ))}
          <li><b>Non conclu</b> : {s.not_concluded.length ? s.not_concluded.map((u) => u.reason ?? "?").join(" ; ") : "rien"}</li>
        </ul>
      ) : s.chain ? (
        <ul>
          <li><b>Vu</b> : {s.seen.sources} sources consultées, chaîne de {s.chain.links} maillons</li>
          {s.chain.hops?.length ? (
            <li data-testid="miniterm-chain">
              <b>Chaîne</b> : {s.chain.hops.map((h) => `${h.hop} ${h.level}`).join(" → ")}
            </li>
          ) : null}
          <li><b>Trouvé</b> : {s.found.length ? s.found.join(", ") : "aucun constat"}</li>
          <li>
            <b>Non conclu</b> : {s.not_concluded.length ? s.not_concluded.map((u) => u.reason ?? "?").join(" ; ") : "rien"}
            {s.chain.runtime_required ? ` · ${s.chain.runtime_required} mesure${s.chain.runtime_required > 1 ? "s" : ""} runtime requise${s.chain.runtime_required > 1 ? "s" : ""}` : ""}
          </li>
          <li><b>Statuts</b> : {s.limits} limites, {s.errors.length} erreur{s.errors.length > 1 ? "s" : ""}</li>
        </ul>
      ) : (
        <ul>
          <li><b>Vu</b> : {s.seen.sources} sources, {s.seen.imports} imports, {s.seen.calls} appels</li>
          <li><b>Trouvé</b> : {s.found.length ? s.found.join(", ") : "aucun constat"}</li>
          <li>
            <b>Non conclu</b> : {s.not_concluded.length ? s.not_concluded.map((u) => `${u.path ?? "?"}${u.line ? ` L${u.line}` : ""} (${u.reason ?? "?"})`).join(" ; ") : "rien"}
          </li>
          <li><b>Statuts</b> : {s.write_templates} gabarits d'écriture, {s.limits} limites, {s.errors.length} erreur{s.errors.length > 1 ? "s" : ""}</li>
        </ul>
      )}
      <div className="miniterm-meta">empreinte {item.content_sha256?.slice(0, 8)}…</div>
      <div className="miniterm-ft" data-testid="miniterm-time">{fmtTime(item.ended_utc)}{d ? ` · ${d}` : ""}</div>
    </div>
  );
};

const GIRO_CLASS: Record<ActivityLight, string> = { GREEN: "green", RED: "red", GRAY: "gray" } as Record<ActivityLight, string>;

export const CartographerMiniTerminal: React.FC<{ title?: string; light: ActivityLight; lightReason: string; history: HistoryState; controls?: React.ReactNode; info?: React.ReactNode; footer?: React.ReactNode }> = ({
  title = "Repository Cartographer",
  light,
  lightReason,
  history,
  controls,
  info,
  footer,
}) => {
  const chrono = history.status === "OK" ? [...history.items].reverse() : [];
  let lastDay = "";
  return (
    <section className="miniterm" data-testid="miniterm" aria-label={`Mini terminal du ${title}`}>
      <header className="miniterm-hd">
        <img
          className={`miniterm-giro miniterm-giro-${GIRO_CLASS[light]}`}
          src={`${import.meta.env.BASE_URL}agents/giro-${GIRO_CLASS[light]}.png`}
          width={36}
          height={36}
          data-testid="miniterm-giro"
          data-light={light}
          alt={`État : ${lightReason}`}
          title={lightReason}
        />
        <h3>{title}</h3>
      </header>
      {info ? <div className="miniterm-info" data-testid="miniterm-info">{info}</div> : null}
      {controls}
      <div className="miniterm-term" data-testid="miniterm-term">
        {history.status === "LOADING" ? <div className="miniterm-day">Lecture en cours…</div> : null}
        {history.status === "UNREACHABLE" ? (
          <div className="miniterm-msg miniterm-msg-bad" data-testid="miniterm-unreachable">Historique illisible · {history.reason}</div>
        ) : null}
        {history.status === "OK" && history.connection !== "AVAILABLE" ? (
          <div className="miniterm-day">{history.connection === "ABSENT" ? "Aucun rapport pour l'instant" : `Historique ${history.connection} · ${history.connection_reason ?? ""}`}</div>
        ) : null}
        {chrono.map((it, i) => {
          const day = it.ended_utc ? fmtDay(it.ended_utc) : "";
          const sep = day && day !== lastDay ? <div className="miniterm-day">{day}</div> : null;
          if (day) lastDay = day;
          return (
            <React.Fragment key={it.invocation_id ?? `x${i}`}>
              {sep}
              <Bubble item={it} previous={chrono[i - 1]} />
            </React.Fragment>
          );
        })}
      </div>
      {history.status === "OK" && history.total !== null && history.total > history.items.length ? (
        <p className="miniterm-foot">{history.items.length} plus récents affichés sur {history.total}.</p>
      ) : null}
      {footer ? <div className="miniterm-footer" data-testid="miniterm-footer">{footer}</div> : null}
    </section>
  );
};
