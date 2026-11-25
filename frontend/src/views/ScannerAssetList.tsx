/** Scanner S3: compact list of the assets published by scanner-universe/1.1.0,
 *  with search, 4/4 · 3/4 · 2/4 filters and a detail per exact instrument.
 *  Reads the publication already validated for the dashboard; no request, no
 *  price, no score, no Radar admissibility. Rows exist only while the universe
 *  is verified: an unavailable publication leaves no former row on screen. */
import { useEffect, useState, type MouseEvent } from "react";
import { MARKET_LABEL, MARKET_SHORT, ASSET_CLASS_LABEL, type UniverseAsset, type UniverseMarket } from "../lib/scannerUniverseClient";
import { COVERAGES, PAGE_SIZE, chipCounts, filterAssets, normalizeQuery, type AssetMatch, type Coverage } from "../lib/scannerAssetSearch";

const ORDER: UniverseMarket[] = ["KRAKEN_SPOT", "KRAKEN_PERPETUAL", "MEXC_SPOT", "MEXC_PERPETUAL"];
const plural = (n: number, one: string, many = one + "s") => n > 1 ? many : one;
const joinFr = (xs: string[]) => xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} et ${xs[xs.length - 1]}`;

export type AssetListState = "LOADING" | "UNAVAILABLE" | "NOT_PUBLISHED" | "EMPTY" | "READY";
export interface AssetSearch { q: string; cov: Coverage | null; set: (q: string, cov: Coverage | null) => void }

/** Search kept in component state when no URL owner is given (tests, isolated render). */
export function useLocalAssetSearch(): AssetSearch {
  const [s, setS] = useState<{ q: string; cov: Coverage | null }>({ q: "", cov: null });
  return { ...s, set: (q, cov) => setS({ q: normalizeQuery(q), cov }) };
}

/** Full market names with presence or absence, in card order: what the compact KR·S … MX·P line shows. */
const presence = (a: UniverseAsset) => ORDER.map(k => `${MARKET_LABEL[k]} ${a.markets[k] ? "présent" : "absent"}`).join(", ");
const rowLabel = (a: UniverseAsset, via: string | null) =>
  `${a.base}, ${a.asset_class === "CRYPTO" ? "" : ASSET_CLASS_LABEL[a.asset_class] + ", "}${a.market_count} marchés sur 4 : ${presence(a)}, ${plural(a.quotes.length, "devise")} ${joinFr(a.quotes)}${via ? `, trouvé via ${via}` : ""}, ouvrir les instruments`;

const Row = ({ m, onOpen }: { m: AssetMatch; onOpen: (e: MouseEvent<HTMLButtonElement>, base: string) => void }) => {
  const a = m.asset;
  return <li><button type="button" className="su-asset-row" aria-label={rowLabel(a, m.via)} onClick={e => onOpen(e, a.base)}>
    <span className="su-row-main"><strong>{a.base}</strong><span className="market-count-badge">{a.market_count}/4</span>
      {a.asset_class !== "CRYPTO" && <span className="su-class">{ASSET_CLASS_LABEL[a.asset_class]}</span>}
      {m.via && <span className="su-via">via {m.via}</span>}</span>
    <span className="su-row-meta" aria-hidden="true">
      <span className="su-mkts">{ORDER.map(k => <span key={k} className={a.markets[k] ? undefined : "su-off"} title={`${MARKET_LABEL[k]} ${a.markets[k] ? "présent" : "absent"}`}>{MARKET_SHORT[k]}</span>)}</span>
      <span className="su-quotes">{a.quotes.join(" · ")}</span></span>
  </button></li>;
};

const MESSAGE: Record<Exclude<AssetListState, "READY">, string> = {
  LOADING: "Liste en chargement.",
  UNAVAILABLE: "Liste indisponible : aucun actif n’est présenté comme courant.",
  NOT_PUBLISHED: "Non publié par scanner-universe/1.0.0 : la liste par actif n’existe pas dans ce schéma. Les paires strictes restent dans leur section.",
  EMPTY: "Aucun actif publié sur au moins un Spot et un Perpétuel.",
};

export function ScannerAssetList({ state, assets, search, onOpen }: {
  state: AssetListState; assets: UniverseAsset[]; search: AssetSearch;
  onOpen: (e: MouseEvent<HTMLButtonElement>, base: string) => void;
}) {
  const ready = state === "READY";
  const { q, cov } = search;
  const [limit, setLimit] = useState(PAGE_SIZE);
  useEffect(() => setLimit(PAGE_SIZE), [q, cov]);
  const counts = ready ? chipCounts(assets) : null;
  const { crypto, others } = ready ? filterAssets(assets, q, cov) : { crypto: [], others: [] };
  const total = crypto.length + others.length;
  const shownCrypto = crypto.slice(0, limit);
  const shownOthers = others.slice(0, Math.max(0, limit - crypto.length));
  const rest = total - shownCrypto.length - shownOthers.length;
  const chip = (c: Coverage | null) => {
    const n = counts ? (c === null ? counts.all : counts[c]) : null;
    const name = c === null ? "Tous" : `${c}/4`;
    const label = c === null ? `Tous, ${n ?? "compte indisponible"}${n !== null ? ` ${plural(n, "ligne publiée", "lignes publiées")}` : ""}`
      : `${c} marchés sur 4, ${n ?? "compte indisponible"}${n !== null ? ` ${plural(n, "crypto-actif")}` : ""}`;
    return <button key={name} type="button" className="su-chip-filter" aria-pressed={cov === c} disabled={!ready} aria-label={label}
      onClick={() => search.set(q, c)}>{name} <span className="su-chip-count">{n ?? "—"}</span></button>;
  };

  return <section className="su-assets" aria-label="Actifs publiés" data-list-state={state}>
    <div className="su-block-head"><h3>Actifs publiés</h3><span>présence dans les catalogues</span></div>
    <input type="search" className="su-search" aria-label="Actif ou symbole" placeholder="Actif ou symbole (BTC, XBT…)"
      value={q} disabled={!ready} autoComplete="off" autoCapitalize="characters" spellCheck={false}
      onChange={e => search.set(e.currentTarget.value, cov)} />
    <div className="su-filters" role="group" aria-label="Filtrer par couverture">{[null, ...COVERAGES].map(chip)}</div>
    {!ready ? <p className="su-list-msg" role="status" data-testid="asset-list-message">{MESSAGE[state]}</p> : <>
      <p className="su-results" aria-live="polite" data-testid="asset-results">
        {total} {plural(total, "résultat")} · {counts!.all} {plural(counts!.all, "ligne publiée", "lignes publiées")}</p>
      {total === 0 ? <p className="su-list-msg" role="status" data-testid="asset-list-message">
        {q ? `Aucun actif publié ne correspond à « ${q} »${cov !== null ? ` avec le filtre ${cov}/4` : ""}.` : `Aucun crypto-actif publié sur ${cov} marchés.`}</p> : <>
        {shownCrypto.length > 0 && <ul className="su-asset-list" aria-label="Crypto-actifs">{shownCrypto.map(m => <Row key={m.asset.base} m={m} onOpen={onOpen} />)}</ul>}
        {shownOthers.length > 0 && <>
          <p className="su-group-head" id="su-uncounted">Devises et stablecoins · non comptés dans la couverture</p>
          <ul className="su-asset-list" aria-labelledby="su-uncounted">{shownOthers.map(m => <Row key={m.asset.base} m={m} onOpen={onOpen} />)}</ul></>}
        {rest > 0 && <button type="button" className="su-more" onClick={() => setLimit(l => l + PAGE_SIZE)}>
          Afficher {Math.min(PAGE_SIZE, rest)} de plus ({rest} {plural(rest, "restant")})</button>}
      </>}
    </>}
  </section>;
}
