/** Scanner scientifique (S2): mobile dashboard of the MEXC × Kraken universe
 *  (Spot × Perpetual) as published by the server. First screen: global status,
 *  the four catalogue sources with their age, and the coverage counts as
 *  published (assets on 4/3/2 markets kept apart from strict same-quote pairs).
 *  Native instruments and proofs stay one tap away. Nothing is computed here
 *  beyond formatting: an unavailable value is shown as such, never as zero, and
 *  catalogue freshness is never presented as a live price. */
import { useEffect, useRef, useState, type MouseEvent } from "react";
import {
  fetchScannerUniverse, universeView, sourceFreshness, UniverseError, MARKET_LABEL, MARKET_SHORT, UNIVERSE_MARKETS,
  type ScannerUniverse as Universe, type UniverseView, type UniversePair, type UniverseMarket, type UniverseAsset, type UniverseSource, ASSET_CLASS_LABEL,
} from "../lib/scannerUniverseClient";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import { ScannerAssetList, useLocalAssetSearch, type AssetListState, type AssetSearch } from "./ScannerAssetList";
import "./scanner-universe.css";

const utc = (ms: number | null | undefined) => ms == null ? "Non disponible" : new Date(ms).toISOString().replace("T", " ").slice(0, 19) + " UTC";
const minute = (ms: number) => new Date(ms).toISOString().replace("T", " ").slice(0, 16) + " UTC";
const iso = (ms: number) => new Date(ms).toISOString();
/** Elapsed time, rounded down to its unit. Formatting only. */
export const ageLabel = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 172_800) return `${Math.floor(s / 3600)} h`;
  return `${Math.floor(s / 86_400)} j`;
};
const REASON: Record<string, string> = {
  ABSENT: "absente du catalogue", NOT_TRADABLE: "non négociable", NOT_PERPETUAL: "contrat à échéance",
  AMBIGUOUS_MAPPING: "correspondance ambiguë", AMBIGUOUS_CONTRACT: "contrat ambigu", DUPLICATE_KEY: "deux instruments pour la même paire",
  DARK_POOL_PAIR: "carnet dark pool", STALE: "relevé périmé", COLLECTED_IN_FUTURE: "horodatage incohérent",
  READ_TOO_OLD: "dernière lecture trop ancienne", UNVERIFIABLE: "non vérifiable",
  INVALID_UNIVERSE_CONTRACT: "publication invalide (contrat scanner-universe non respecté)", INVALID_JSON: "réponse illisible",
  RESPONSE_LIMIT: "réponse trop volumineuse", TIMEOUT: "délai de lecture dépassé", TRANSPORT_ERROR: "lecture impossible (réseau)",
};
export const reasonLabel = (reason: string | null) => {
  if (!reason) return "valide";
  const [head, tail] = reason.split(":");
  if (head === "INCOMPLETE") return `catalogue incomplet (${tail})`;
  if (head === "UNAVAILABLE") return `catalogue inaccessible (${tail})`;
  if (head.startsWith("SOURCE_")) return "source non vérifiée";
  if (/^HTTP_\d{3}$/.test(head)) return `erreur du serveur (${head})`;
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

/** Short card names, still unambiguous (venue + market type); full names stay in aria-label and details. */
export const MARKET_CARD: Record<UniverseMarket, string> = { KRAKEN_SPOT: "Kraken Spot", KRAKEN_PERPETUAL: "Kraken Perp.", MEXC_SPOT: "MEXC Spot", MEXC_PERPETUAL: "MEXC Perp." };
/** Display order asked for the operator: Kraken first, Spot before Perpetual. */
export const SOURCE_ORDER: UniverseMarket[] = ["KRAKEN_SPOT", "KRAKEN_PERPETUAL", "MEXC_SPOT", "MEXC_PERPETUAL"];

type Tone = "ok" | "empty" | "warn" | "ko" | "wait";
type SourceCard = { market: UniverseMarket; tone: Tone; label: string; why: string | null; source: UniverseSource | null; ageMs: number | null };

/** One card per catalogue, read from the publication and the client's own age check. */
function sourceCards(view: UniverseView): SourceCard[] {
  const doc = view.state === "LOADING" ? null : view.doc;
  if (!doc) return SOURCE_ORDER.map(market => ({ market, tone: "wait", label: "Inconnue", source: null, ageMs: null,
    why: view.state === "LOADING" ? "publication en cours de lecture" : "publication non reçue ou illisible" }));
  const serverNow = view.state !== "LOADING" && view.serverNow !== undefined ? view.serverNow : doc.served_ms ?? doc.computed_ms;
  const fresh = sourceFreshness(doc, serverNow);
  const blocked = new Map(view.state === "UNAVAILABLE" ? view.blocking.filter(b => b.market).map(b => [b.market!, b.reason]) : []);
  // A failed refresh or a too old read leaves every value unconfirmed, whatever it said.
  const unconfirmed = view.state === "UNAVAILABLE" && view.blocking.some(b => b.market === null);
  return SOURCE_ORDER.map(market => {
    const source = doc.sources.find(s => s.market === market) ?? null;
    const { ageMs = null, stale = true } = fresh.get(market) ?? {};
    const base = { market, source, ageMs };
    if (!source) return { ...base, tone: "ko", label: "Absente", why: "source absente de la publication" };
    const reason = blocked.get(market) ?? (source.current ? null : source.reason ?? "UNVERIFIABLE");
    if (!reason && source.collected_ms === null) return { ...base, tone: "ko", label: "Indisponible", why: "relevé sans horodatage" };
    if (reason === "STALE" || (!reason && stale))
      return { ...base, tone: "warn", label: "Périmée", why: `limite ${ageLabel(doc.freshness_max_age_ms)} dépassée` };
    if (reason) return { ...base, tone: "ko", label: source.catalogue_state === "INCOMPLETE" ? "Incomplète" : "Indisponible", why: reasonLabel(reason).replace(/^catalogue /, "") };
    if (unconfirmed) return { ...base, tone: "wait", label: "Non confirmée", why: "dernière publication reçue, plus confirmée" };
    return { ...base, tone: "ok", label: "Disponible", why: null };
  });
}

function globalStatus(view: UniverseView, byAsset: boolean): { tone: Tone; label: string } {
  if (view.state === "LOADING") return { tone: "wait", label: "Chargement" };
  if (view.state === "VERIFIED") return { tone: "ok", label: "Vérifié" };
  if (view.state === "VERIFIED_EMPTY") return { tone: byAsset ? "ok" : "empty", label: "Vérifié · strict vide" };
  if (view.code === "SOURCE_STALE") return { tone: "warn", label: "Source périmée" };
  if (view.code === "READ_TOO_OLD") return { tone: "warn", label: "Publication trop ancienne" };
  if (view.code === "INVALID_UNIVERSE_CONTRACT") return { tone: "ko", label: "Publication invalide" };
  return { tone: "ko", label: "Indisponible" };
}

const Proof = ({ market, pair }: { market: UniverseMarket; pair: UniversePair }) => {
  const p = pair.proofs[market];
  return <div className="universe-proof"><dt>{MARKET_LABEL[market]}</dt><dd>
    <strong>{p.native_symbol}</strong> · {p.native_base}/{p.native_quote}<br />
    {p.contract_type === "SPOT" ? "Spot" : p.contract_type === "LINEAR_PERPETUAL" ? "Perpétuel linéaire" : "Perpétuel inverse"}
    {p.settlement_asset ? ` · règlement ${p.settlement_asset}` : ""}<br />
    <small>{p.status}</small><br /><small>Relevé {utc(p.collected_ms)}</small></dd></div>;
};

const CONTRACT: Record<string, string> = { SPOT: "Spot", LINEAR_PERPETUAL: "Perpétuel linéaire", INVERSE_PERPETUAL: "Perpétuel inverse" };
/** S3: every published native instrument of every market, one line each, never truncated. */
const AssetDetail = ({ asset }: { asset: UniverseAsset }) => <dl className="su-instruments">{SOURCE_ORDER.map(m => {
  const rows = asset.markets[m];
  return <div className="universe-proof" key={m} data-market={m}><dt>{MARKET_LABEL[m]}{rows ? ` · ${rows.length} instrument${rows.length > 1 ? "s" : ""}` : ""}</dt><dd>{rows
    ? <ul className="su-instrument-rows">{rows.map(r => <li key={r.native_symbol}>
        <strong>{r.native_symbol}</strong> · {asset.base} / {r.quote} · {CONTRACT[r.contract_type] ?? r.contract_type} · règlement {r.settlement_asset
          ?? (r.contract_type === "SPOT" ? "sans objet (Spot)" : "non publié")}</li>)}</ul>
    : <em>Aucun instrument publié pour ce marché</em>}</dd></div>;
})}</dl>;

/** A count as published, or the reason it cannot be shown. Never a zero by default. */
type Count = { value: number } | { missing: string };
const CountValue = ({ count }: { count: Count }) => "value" in count
  ? <strong className="su-count">{count.value}</strong>
  : <span className="su-count missing" title={count.missing}><span aria-hidden="true">—</span><span className="su-sr">{count.missing}</span></span>;

export function ScannerUniverse({ view, search }: { view: UniverseView; search?: AssetSearch }) {
  const localSearch = useLocalAssetSearch();
  const assetSearch = search ?? localSearch;
  const [active, setActive] = useState<string | null>(null);
  const [activeAsset, setActiveAsset] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const close = () => { setActive(null); setActiveAsset(null); trigger.current?.focus(); };
  const open = (setter: (k: string) => void, key: string) => (e: MouseEvent<HTMLButtonElement>) => { trigger.current = e.currentTarget; setter(key); };
  const doc = view.state === "LOADING" ? null : view.doc;
  const verified = view.state === "VERIFIED" || view.state === "VERIFIED_EMPTY";
  const detail = view.state === "VERIFIED" ? view.pairs.find(p => p.key === active) : undefined;
  const setup = view.state === "UNAVAILABLE" && !view.doc ? marketSourceSetup(view.code) : null;
  const byAsset = doc?.schema_version === "scanner-universe/1.1.0";
  const assets = verified ? view.assets : [];
  const crypto = assets.filter(a => a.asset_class === "CRYPTO");
  const others = assets.filter(a => a.asset_class !== "CRYPTO");
  const tier = (n: number) => crypto.filter(a => a.market_count === n);
  const asset = assets.find(a => a.base === activeAsset);
  // A detail whose asset left the publication (or a publication that became unavailable) closes.
  useEffect(() => { if (activeAsset !== null && !asset) setActiveAsset(null); }, [activeAsset, asset]);
  const listState: AssetListState = view.state === "LOADING" ? "LOADING" : !verified ? "UNAVAILABLE" : !byAsset ? "NOT_PUBLISHED" : assets.length ? "READY" : "EMPTY";
  const status = globalStatus(view, byAsset);
  const cards = sourceCards(view);
  const serverNow = view.state !== "LOADING" && doc ? view.serverNow ?? doc.served_ms ?? doc.computed_ms : null;
  const strictCount = view.state === "VERIFIED" ? view.pairs.length : view.state === "VERIFIED_EMPTY" ? 0 : null;

  const missing = view.state === "LOADING" ? "En chargement" : "Indisponible";
  const tierCount = (n: number): Count => !verified ? { missing } : byAsset ? { value: tier(n).length } : { missing: "Non publié" };
  const strict: Count = strictCount === null ? { missing } : { value: strictCount };
  const reasons = view.state === "UNAVAILABLE" ? view.blocking.map(b => (b.market ? MARKET_LABEL[b.market] + " : " : "") + reasonLabel(b.reason)).join(" · ") : "";

  return <section className="scanner-universe" aria-label="Scanner scientifique" data-state={view.state}
    data-code={view.state === "UNAVAILABLE" ? view.code : undefined}>
    {/* A — En-tête : statut, dernier relevé vérifié, âge de publication, nature */}
    <header className="su-head">
      <div className="su-title"><h2>Scanner scientifique</h2>
        <span className="su-pill" data-tone={status.tone} aria-live="polite">{status.label}</span></div>
      <p className="su-meta">
        <span className="su-checked">{verified ? <>Relevé vérifié <time dateTime={iso(view.doc.computed_ms)} title={utc(view.doc.computed_ms)}>{minute(view.doc.computed_ms)}</time>
          {serverNow !== null && <> · publié il y a {ageLabel(serverNow - view.doc.computed_ms)}</>}</>
          : view.state === "LOADING" ? "Relevé vérifié : lecture en cours"
          : doc?.reference ? <>Dernier relevé vérifié <time dateTime={iso(doc.reference.computed_ms)} title={utc(doc.reference.computed_ms)}>{minute(doc.reference.computed_ms)}</time> · <strong>non courant</strong></>
          : doc && doc.status !== "UNVERIFIABLE" ? <>Dernier relevé vérifié <time dateTime={iso(doc.computed_ms)} title={utc(doc.computed_ms)}>{minute(doc.computed_ms)}</time> · <strong>plus courant</strong></>
          : "Relevé vérifié : aucun relevé courant"}</span>
        <span className="su-nature"><span className="su-tag">Catalogues</span> pas de cotation LIVE</span>
      </p>
    </header>

    {/* B — Quatre sources, cartes compactes 2 × 2 */}
    <div className="su-block-head" aria-hidden="true"><span>Sources</span><span>âge du relevé</span></div>
    <ul className="su-sources" aria-label="État des quatre sources">{cards.map(c =>
      <li key={c.market} data-tone={c.tone} aria-label={`${MARKET_LABEL[c.market]} : ${c.label}`}>
        <span className="su-source-line"><strong className="su-source-name">{MARKET_CARD[c.market]}</strong>
          {c.source?.collected_ms != null
            ? <time className="su-age" dateTime={iso(c.source.collected_ms)} title={`Relevé ${utc(c.source.collected_ms)}`}>{c.ageMs !== null ? ageLabel(c.ageMs) : "?"}</time>
            : <span className="su-age" title="Relevé non disponible">—</span>}</span>
        <span className="su-chip" data-tone={c.tone}><span className="su-dot" aria-hidden="true" />{c.label}</span>
        {c.why && (c.tone === "ko" || c.tone === "warn") && <span className="su-why">{c.why}</span>}
      </li>)}</ul>

    {/* C — Couverture : actifs multi-marchés et paires strictes, quatre indicateurs */}
    <section className="su-coverage" aria-label="Couverture de l’univers">
      <div className="su-block-head"><h3>Couverture</h3><span>actifs multi-marchés ≠ paires strictes</span></div>
      <dl className="su-tiles">
        {[4, 3, 2].map(n => <div key={n} className="su-tile" data-testid={`coverage-tier-${n}`}><dt>{n} marchés</dt><dd><CountValue count={tierCount(n)} /></dd></div>)}
        <div className="su-tile su-strict" data-testid="coverage-strict"><dt>Paires strictes</dt><dd><CountValue count={strict} /></dd></div>
      </dl>
      <p className="su-note">
        {!verified ? `— : ${missing.toLowerCase()}, aucun compte n’est présenté comme courant.`
          : !byAsset ? `— : non publié, le schéma ${doc!.schema_version} ne regroupe pas par actif.`
          : `${tier(4).length + tier(3).length + tier(2).length} crypto-actif${tier(4).length + tier(3).length + tier(2).length > 1 ? "s" : ""} au total${others.length > 0 ? ` · ${others.length} devise${others.length > 1 ? "s" : ""} et stablecoin${others.length > 1 ? "s" : ""} non compté${others.length > 1 ? "s" : ""}` : ""}.`}
        {" "}Paire stricte : même base et même devise de cotation sur les 4 marchés.</p>
    </section>

    {/* Pourquoi : indisponible, strict vide ou liste vérifiée */}
    {view.state === "LOADING" && <p role="status" className="universe-banner wait">Chargement de l’univers commun…</p>}
    {view.state === "UNAVAILABLE" && (setup
      ? <p role="alert" className="universe-banner ko"><strong>Univers indisponible</strong> · source non configurée sur ce serveur ({view.code}). Aucune liste courante.</p>
      : <p role="alert" className={`universe-banner ${status.tone}`}><strong>Univers indisponible</strong> · {reasons}. Aucune paire n’est présentée comme courante.</p>)}
    {view.state === "UNAVAILABLE" && view.doc?.reference && <p className="universe-reference">Dernière liste vérifiée, <strong>non courante</strong>, calculée le {utc(view.doc.reference.computed_ms)} : {view.doc.reference.keys.length ? view.doc.reference.keys.join(", ") : "univers vide"}.</p>}
    {view.state === "VERIFIED_EMPTY" && (byAsset
      ? <p role="status" className="universe-banner empty"><strong>Aucune paire stricte</strong> · catalogues complets et frais, mais aucune paire n’a la même devise de cotation sur les quatre marchés. Les actifs multi-marchés sont comptés à part.</p>
      : <p role="status" className="universe-banner empty"><strong>Univers vide vérifié</strong> · les quatre catalogues sont complets et frais ; aucune paire n’est négociable sur les quatre marchés avec la même devise de cotation.</p>)}
    {view.state === "VERIFIED" && <p role="status" className="universe-banner ok"><strong>{view.pairs.length} paire{view.pairs.length > 1 ? "s" : ""} vérifiée{view.pairs.length > 1 ? "s" : ""}</strong> · même devise de cotation sur les quatre marchés, quatre preuves chacune.</p>}

    {/* S3 — Liste des actifs publiés : recherche, filtres, détail par instrument */}
    <ScannerAssetList state={listState} assets={assets} search={assetSearch} onOpen={(e, base) => { trigger.current = e.currentTarget; setActiveAsset(base); }} />

    {/* D — Détails, au toucher */}
    <div className="su-details" aria-label="Détails">
      {view.state === "VERIFIED" && <details className="universe-exclusions">
        <summary>Paires strictes ({view.pairs.length}) · preuves natives</summary>
        <ul className="universe-pairs" aria-label="Paires vérifiées sur quatre marchés">{view.pairs.map(p =>
          <li key={p.key}><button type="button" onClick={open(setActive, p.key)} aria-label={`${p.key} · vérifiée sur ${UNIVERSE_MARKETS.map(m => MARKET_LABEL[m]).join(", ")}`}>
            <strong>{p.key}</strong>
            <span className="universe-badges" aria-hidden="true">{UNIVERSE_MARKETS.map(m => <span key={m}>✓ {MARKET_SHORT[m]}</span>)}</span>
          </button></li>)}</ul></details>}
      {!byAsset && doc && doc.exclusions.length > 0 && <details className="universe-exclusions">
        <summary>{doc.exclusions.length}{doc.exclusions_truncated ? "+" : ""} paire{doc.exclusions.length > 1 ? "s" : ""} présente{doc.exclusions.length > 1 ? "s" : ""} sur trois marchés au moins, exclue{doc.exclusions.length > 1 ? "s" : ""}</summary>
        <ul>{doc.exclusions.map(e => <li key={e.key}><strong>{e.key}</strong> · {SOURCE_ORDER.filter(m => e.reasons[m] !== null && e.reasons[m] !== undefined).map(m => `${MARKET_LABEL[m]} : ${reasonLabel(e.reasons[m])}`).join(" · ")}</li>)}</ul>
      </details>}
      {doc && <details className="universe-exclusions su-publication">
        <summary>Détail technique des sources et de la publication</summary>
        <dl className="su-source-detail">{SOURCE_ORDER.map(m => { const s = doc.sources.find(x => x.market === m); const c = cards.find(x => x.market === m)!;
          return <div key={m}><dt>{MARKET_LABEL[m]}</dt><dd>{s ? <>
            {c.label}{c.why ? ` · ${c.why}` : ""} · catalogue {s.catalogue_state}{s.reason ? ` (${s.reason})` : ""}<br />
            {s.instruments} instruments · {s.admissible} admissibles<br />
            Relevé {utc(s.collected_ms)}{c.ageMs !== null ? ` · âge ${ageLabel(c.ageMs)}` : ""}</> : "Absente de la publication"}</dd></div>; })}
          <div><dt>Publication</dt><dd>
            {doc.schema_version} · statut publié {doc.status}<br />
            Calcul {utc(doc.computed_ms)}{doc.served_ms !== undefined ? <> · service {utc(doc.served_ms)}</> : null}<br />
            Limite de fraîcheur {ageLabel(doc.freshness_max_age_ms)} · cadence {ageLabel(doc.cadence_ms)}<br />
            Empreinte <code className="su-sha">{doc.universe_sha256}</code></dd></div>
        </dl>
      </details>}
    </div>

    {detail && <dialog className="universe-detail" aria-label={`Preuves ${detail.key}`} ref={node => { if (node && !node.open) node.showModal?.(); }}
      open={typeof HTMLDialogElement.prototype.showModal !== "function" || undefined} onClose={close}
      onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); e.currentTarget.close?.(); close(); } }}>
      <form method="dialog"><button type="button" onClick={e => { e.currentTarget.closest("dialog")?.close?.(); close(); }}>Fermer</button></form>
      <h3>{detail.key} · quatre preuves</h3>
      <dl>{SOURCE_ORDER.map(m => <Proof key={m} market={m} pair={detail} />)}</dl>
      <p><small>Empreinte de l’univers {view.state === "VERIFIED" ? view.doc.universe_sha256.slice(0, 16) : ""}… · observation uniquement, aucune autorisation de trading.</small></p>
    </dialog>}
    {asset && <dialog className="universe-detail" aria-label={`Instruments ${asset.base}`} ref={node => { if (node && !node.open) node.showModal?.(); }}
      open={typeof HTMLDialogElement.prototype.showModal !== "function" || undefined} onClose={close}
      onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); e.currentTarget.close?.(); close(); } }}>
      <form method="dialog"><button type="button" onClick={e => { e.currentTarget.closest("dialog")?.close?.(); close(); }}>Fermer</button></form>
      <h3>{asset.base} · {ASSET_CLASS_LABEL[asset.asset_class]} · {asset.market_count}/4 marchés</h3>
      <AssetDetail asset={asset} />
      <p><small>Devises listées telles que publiées : {asset.quotes.join(", ")}. Aucune devise n’est assimilée à une autre · observation uniquement, aucune autorisation de trading.</small></p>
    </dialog>}
  </section>;
}
