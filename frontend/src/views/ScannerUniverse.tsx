/** Scanner V1: the common MEXC × Kraken universe (Spot × Perpetual) as published
 *  by the server. Every listed pair carries its four market proofs; an empty
 *  verified universe and an unavailable one are shown apart. Nothing is computed here. */
import { useEffect, useRef, useState } from "react";
import {
  fetchScannerUniverse, universeView, UniverseError, MARKET_LABEL, MARKET_SHORT, UNIVERSE_MARKETS,
  type ScannerUniverse as Universe, type UniverseView, type UniversePair, type UniverseMarket,
} from "../lib/scannerUniverseClient";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import "./scanner-universe.css";

const utc = (ms: number | null | undefined) => ms == null ? "Non disponible" : new Date(ms).toISOString().replace("T", " ").slice(0, 19) + " UTC";
const REASON: Record<string, string> = {
  ABSENT: "absente du catalogue", NOT_TRADABLE: "non négociable", NOT_PERPETUAL: "contrat à échéance",
  AMBIGUOUS_MAPPING: "correspondance ambiguë", AMBIGUOUS_CONTRACT: "contrat ambigu", DUPLICATE_KEY: "deux instruments pour la même paire",
  DARK_POOL_PAIR: "carnet dark pool", STALE: "relevé périmé", COLLECTED_IN_FUTURE: "horodatage incohérent",
  READ_TOO_OLD: "dernière lecture trop ancienne", UNVERIFIABLE: "non vérifiable",
};
export const reasonLabel = (reason: string | null) => {
  if (!reason) return "valide";
  const [head, tail] = reason.split(":");
  if (head === "INCOMPLETE") return `catalogue incomplet (${tail})`;
  if (head === "UNAVAILABLE") return `catalogue inaccessible (${tail})`;
  if (head.startsWith("SOURCE_")) return "source non vérifiée";
  return REASON[head] ?? reason;
};

/** Polls the publication and turns it into what the Scanner may show as current. */
export function useScannerUniverse(pollMs = 60_000): UniverseView {
  const [doc, setDoc] = useState<Universe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [now, setNow] = useState(Date.now);
  const received = useRef(0);
  useEffect(() => {
    const poll = setInterval(() => setRefresh(n => n + 1), pollMs);
    const tick = setInterval(() => setNow(Date.now()), 1_000);
    return () => { clearInterval(poll); clearInterval(tick); };
  }, [pollMs]);
  useEffect(() => {
    const controller = new AbortController();
    fetchScannerUniverse(controller.signal).then(d => {
      if (controller.signal.aborted) return;
      received.current = Date.now(); setDoc(d); setError(null); setNow(received.current);
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof UniverseError ? e.code : "TRANSPORT_ERROR"); });
    return () => controller.abort();
  }, [refresh]);
  return universeView(doc, error, received.current, now);
}

const Proof = ({ market, pair }: { market: UniverseMarket; pair: UniversePair }) => {
  const p = pair.proofs[market];
  return <div className="universe-proof"><dt>{MARKET_LABEL[market]}</dt><dd>
    <strong>{p.native_symbol}</strong> · {p.native_base}/{p.native_quote}<br />
    {p.contract_type === "SPOT" ? "Spot" : p.contract_type === "LINEAR_PERPETUAL" ? "Perpétuel linéaire" : "Perpétuel inverse"}
    {p.settlement_asset ? ` · règlement ${p.settlement_asset}` : ""}<br />
    <small>{p.status}</small><br /><small>Relevé {utc(p.collected_ms)}</small></dd></div>;
};

export function ScannerUniverse({ view }: { view: UniverseView }) {
  const [active, setActive] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const close = () => { setActive(null); trigger.current?.focus(); };
  const doc = view.state === "LOADING" ? null : view.doc;
  const detail = view.state === "VERIFIED" ? view.pairs.find(p => p.key === active) : undefined;
  const setup = view.state === "UNAVAILABLE" && !view.doc ? marketSourceSetup(view.code) : null;
  const blocked = new Map(view.state === "UNAVAILABLE" ? view.blocking.filter(b => b.market).map(b => [b.market!, b.reason]) : []);

  return <section className="scanner-universe" aria-label="Univers commun du Scanner" data-state={view.state}>
    <header><h2>Univers commun</h2>
      <p>MEXC Spot ∩ MEXC Perpétuel ∩ Kraken Spot ∩ Kraken Perpétuel · même base, même devise de cotation.</p></header>
    {doc && <ul className="universe-sources" aria-label="État des quatre catalogues">{doc.sources.map(s => {
      const reason = blocked.get(s.market) ?? (s.current ? null : s.reason ?? "UNVERIFIABLE");
      const ok = s.current && !reason;
      return <li key={s.market} className={ok ? "ok" : "ko"}>
        <strong>{ok ? "✓" : "✗"} {MARKET_LABEL[s.market]}</strong>
        <span>{ok ? `${s.admissible} négociables` : reasonLabel(reason)}</span>
        <small>{utc(s.collected_ms)}</small></li>;
    })}</ul>}
    {view.state === "LOADING" && <p role="status">Chargement de l’univers commun…</p>}
    {view.state === "UNAVAILABLE" && (setup
      ? <p role="alert" className="universe-banner ko"><strong>Univers indisponible</strong> · source non configurée sur ce serveur ({view.code}). Aucune liste courante.</p>
      : <p role="alert" className="universe-banner ko"><strong>Univers indisponible</strong> · {view.blocking.map(b => (b.market ? MARKET_LABEL[b.market] + " : " : "") + reasonLabel(b.reason)).join(" · ")}. Aucune paire n’est présentée comme courante.</p>)}
    {view.state === "UNAVAILABLE" && view.doc?.reference && <p className="universe-reference">Dernière liste vérifiée, <strong>non courante</strong>, calculée le {utc(view.doc.reference.computed_ms)} : {view.doc.reference.keys.length ? view.doc.reference.keys.join(", ") : "univers vide"}.</p>}
    {view.state === "VERIFIED_EMPTY" && <p role="status" className="universe-banner empty"><strong>Univers vide vérifié</strong> · les quatre catalogues sont complets et frais ; aucune paire n’est négociable sur les quatre marchés avec la même devise de cotation.</p>}
    {view.state === "VERIFIED" && <>
      <p role="status" className="universe-banner ok"><strong>{view.pairs.length} paire{view.pairs.length > 1 ? "s" : ""} vérifiée{view.pairs.length > 1 ? "s" : ""}</strong> · quatre preuves de marché chacune · calcul {utc(view.doc.computed_ms)}</p>
      <ul className="universe-pairs" aria-label="Paires vérifiées sur quatre marchés">{view.pairs.map(p =>
        <li key={p.key}><button type="button" onClick={e => { trigger.current = e.currentTarget; setActive(p.key); }} aria-label={`${p.key} · vérifiée sur ${UNIVERSE_MARKETS.map(m => MARKET_LABEL[m]).join(", ")}`}>
          <strong>{p.key}</strong>
          <span className="universe-badges" aria-hidden="true">{UNIVERSE_MARKETS.map(m => <span key={m}>✓ {MARKET_SHORT[m]}</span>)}</span>
        </button></li>)}</ul>
    </>}
    {doc && doc.exclusions.length > 0 && <details className="universe-exclusions">
      <summary>{doc.exclusions.length}{doc.exclusions_truncated ? "+" : ""} paire{doc.exclusions.length > 1 ? "s" : ""} présente{doc.exclusions.length > 1 ? "s" : ""} sur trois marchés au moins, exclue{doc.exclusions.length > 1 ? "s" : ""}</summary>
      <ul>{doc.exclusions.map(e => <li key={e.key}><strong>{e.key}</strong> · {UNIVERSE_MARKETS.filter(m => e.reasons[m] !== null).map(m => `${MARKET_LABEL[m]} : ${reasonLabel(e.reasons[m])}`).join(" · ")}</li>)}</ul>
    </details>}
    {detail && <dialog className="universe-detail" aria-label={`Preuves ${detail.key}`} ref={node => { if (node && !node.open) node.showModal?.(); }}
      open={typeof HTMLDialogElement.prototype.showModal !== "function" || undefined} onClose={close}
      onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); e.currentTarget.close?.(); close(); } }}>
      <form method="dialog"><button type="button" onClick={e => { e.currentTarget.closest("dialog")?.close?.(); close(); }}>Fermer</button></form>
      <h3>{detail.key} · quatre preuves</h3>
      <dl>{UNIVERSE_MARKETS.map(m => <Proof key={m} market={m} pair={detail} />)}</dl>
      <p><small>Empreinte de l’univers {view.state === "VERIFIED" ? view.doc.universe_sha256.slice(0, 16) : ""}… · observation uniquement, aucune autorisation de trading.</small></p>
    </dialog>}
  </section>;
}
