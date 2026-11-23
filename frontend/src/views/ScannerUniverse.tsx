/** Scanner V1: the common MEXC × Kraken universe (Spot × Perpetual) as published
 *  by the server. Every listed pair carries its four market proofs; an empty
 *  verified universe and an unavailable one are shown apart. Nothing is computed here. */
import { useEffect, useRef, useState } from "react";
import {
  fetchScannerUniverse, universeView, UniverseError, MARKET_LABEL, MARKET_SHORT, UNIVERSE_MARKETS,
  type ScannerUniverse as Universe, type UniverseView, type UniversePair, type UniverseMarket, type UniverseAsset,
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

const AssetDetail = ({ asset }: { asset: UniverseAsset }) => <dl>{UNIVERSE_MARKETS.map(m => {
  const rows = asset.markets[m];
  return <div className="universe-proof" key={m}><dt>{MARKET_LABEL[m]}</dt><dd>{rows
    ? rows.map(r => <span key={r.native_symbol} className="asset-listing"><strong>{r.native_symbol}</strong> · {r.quote}{r.contract_type === "INVERSE_PERPETUAL" ? " · inverse" : ""}</span>)
    : <em>non négocié</em>}</dd></div>;
})}</dl>;

export function ScannerUniverse({ view }: { view: UniverseView }) {
  const [active, setActive] = useState<string | null>(null);
  const [activeAsset, setActiveAsset] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const close = () => { setActive(null); setActiveAsset(null); trigger.current?.focus(); };
  const doc = view.state === "LOADING" ? null : view.doc;
  const detail = view.state === "VERIFIED" ? view.pairs.find(p => p.key === active) : undefined;
  const setup = view.state === "UNAVAILABLE" && !view.doc ? marketSourceSetup(view.code) : null;
  const byAsset = doc?.schema_version === "scanner-universe/1.1.0";
  const assets = view.state === "VERIFIED" || view.state === "VERIFIED_EMPTY" ? view.assets : [];
  const tier = (n: number) => assets.filter(a => a.market_count === n);
  const asset = assets.find(a => a.base === activeAsset);
  const blocked = new Map(view.state === "UNAVAILABLE" ? view.blocking.filter(b => b.market).map(b => [b.market!, b.reason]) : []);

  return <section className="scanner-universe" aria-label="Univers commun du Scanner" data-state={view.state}>
    <header><h2>{byAsset ? "Actifs MEXC × Kraken" : "Univers commun"}</h2>
      <p>{byAsset ? "Actifs négociés sur au moins un Spot et un Perpétuel · chaque marché dans sa propre devise, jamais confondues (USD ≠ USDT)."
        : "MEXC Spot ∩ MEXC Perpétuel ∩ Kraken Spot ∩ Kraken Perpétuel · même base, même devise de cotation."}</p></header>
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
    {byAsset && (view.state === "VERIFIED" || view.state === "VERIFIED_EMPTY") && <>
      <p role="status" className="universe-banner ok"><strong>{tier(4).length} actif{tier(4).length > 1 ? "s" : ""} sur les 4 marchés</strong> · {tier(3).length} sur 3 · {tier(2).length} sur 2 · calcul {utc(view.doc.computed_ms)}</p>
      <p className="universe-strict">Paires strictes (même devise sur les 4 marchés) : {view.state === "VERIFIED" ? view.pairs.length : 0}.</p>
      {tier(4).length > 0 && <details className="universe-exclusions"><summary>Voir les {tier(4).length} actifs sur les 4 marchés</summary><ul className="universe-pairs universe-assets" aria-label="Actifs sur les quatre marchés">{tier(4).map(a =>
        <li key={a.base}><button type="button" onClick={e => { trigger.current = e.currentTarget; setActiveAsset(a.base); }} aria-label={`${a.base} · 4 marchés · devises ${a.quotes.join(", ")}`}>
          <strong>{a.base}</strong><span className="market-count-badge">4/4</span></button></li>)}</ul></details>}
      {tier(3).length + tier(2).length > 0 && <details className="universe-exclusions">
        <summary>{tier(3).length + tier(2).length} actifs sur 3 ou 2 marchés</summary>
        <ul>{[...tier(3), ...tier(2)].map(a => <li key={a.base}><button type="button" className="asset-link" onClick={e => { trigger.current = e.currentTarget; setActiveAsset(a.base); }}><strong>{a.base}</strong></button> · {a.market_count}/4 · {UNIVERSE_MARKETS.filter(m => a.markets[m]).map(m => MARKET_SHORT[m]).join(" ")}</li>)}</ul>
      </details>}
    </>}
    {!byAsset && view.state === "VERIFIED_EMPTY" && <p role="status" className="universe-banner empty"><strong>Univers vide vérifié</strong> · les quatre catalogues sont complets et frais ; aucune paire n’est négociable sur les quatre marchés avec la même devise de cotation.</p>}
    {view.state === "VERIFIED" && <>
      <p role="status" className="universe-banner ok"><strong>{view.pairs.length} paire{view.pairs.length > 1 ? "s" : ""} vérifiée{view.pairs.length > 1 ? "s" : ""}</strong> · quatre preuves de marché chacune · calcul {utc(view.doc.computed_ms)}</p>
      <ul className="universe-pairs" aria-label="Paires vérifiées sur quatre marchés">{view.pairs.map(p =>
        <li key={p.key}><button type="button" onClick={e => { trigger.current = e.currentTarget; setActive(p.key); }} aria-label={`${p.key} · vérifiée sur ${UNIVERSE_MARKETS.map(m => MARKET_LABEL[m]).join(", ")}`}>
          <strong>{p.key}</strong>
          <span className="universe-badges" aria-hidden="true">{UNIVERSE_MARKETS.map(m => <span key={m}>✓ {MARKET_SHORT[m]}</span>)}</span>
        </button></li>)}</ul>
    </>}
    {!byAsset && doc && doc.exclusions.length > 0 && <details className="universe-exclusions">
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
    {asset && <dialog className="universe-detail" aria-label={`Instruments ${asset.base}`} ref={node => { if (node && !node.open) node.showModal?.(); }}
      open={typeof HTMLDialogElement.prototype.showModal !== "function" || undefined} onClose={close}
      onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); e.currentTarget.close?.(); close(); } }}>
      <form method="dialog"><button type="button" onClick={e => { e.currentTarget.closest("dialog")?.close?.(); close(); }}>Fermer</button></form>
      <h3>{asset.base} · {asset.market_count}/4 marchés</h3>
      <AssetDetail asset={asset} />
      <p><small>Devises listées telles que publiées : {asset.quotes.join(", ")}. Aucune devise n’est assimilée à une autre · observation uniquement, aucune autorisation de trading.</small></p>
    </dialog>}
  </section>;
}
