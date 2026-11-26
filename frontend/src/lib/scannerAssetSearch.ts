/** Scanner S3: search and coverage filter over the assets of one verified
 *  scanner-universe/1.1.0 publication. Pure functions; nothing is fetched and
 *  nothing is ranked. The canonical base comes from the publication; a native
 *  symbol matches only if the publication lists it. No alias table here.
 *  `market_count` describes catalogue presence only: no Radar admissibility,
 *  eligibility or priority is derived from it. */
import type { UniverseAsset, UniverseMarket } from "./scannerUniverseClient";

export const QUERY_MAX = 32;
export const PAGE_SIZE = 50;
export type Coverage = 4 | 3 | 2;
export const COVERAGES: Coverage[] = [4, 3, 2];
/** Same order as the source cards. */
const ORDER: UniverseMarket[] = ["KRAKEN_SPOT", "KRAKEN_PERPETUAL", "MEXC_SPOT", "MEXC_PERPETUAL"];

/** URL or input value -> bounded search: trimmed, upper case, at most 32
 *  characters among A-Z 0-9 . _ - / : (any other character is removed). */
export function normalizeQuery(raw: string | null | undefined): string {
  return (raw ?? "").toUpperCase().replace(/[^A-Z0-9._\-/:]/g, "").slice(0, QUERY_MAX);
}
/** URL value -> coverage filter; anything but 4, 3 or 2 means "Tous" (null). */
export function parseCoverage(raw: string | null | undefined): Coverage | null {
  return raw === "4" ? 4 : raw === "3" ? 3 : raw === "2" ? 2 : null;
}

export type AssetMatch = { asset: UniverseAsset; via: string | null };
/** Base prefix first (no "via"); otherwise the first published native symbol
 *  containing the query, in card order. Exact characters only, no fuzzy match. */
export function matchAsset(asset: UniverseAsset, q: string): AssetMatch | null {
  if (!q || asset.base.startsWith(q)) return { asset, via: null };
  for (const m of ORDER) for (const r of asset.markets[m] ?? []) if (r.native_symbol.toUpperCase().includes(q)) return { asset, via: r.native_symbol };
  return null;
}

/** Chip counts, from the whole verified publication (search does not change them).
 *  "Tous" counts every published row, stablecoins and currencies included; the
 *  coverage chips count crypto-assets only, like the coverage tiles. */
export function chipCounts(assets: UniverseAsset[]): { all: number } & Record<Coverage, number> {
  const crypto = assets.filter(a => a.asset_class === "CRYPTO");
  return { all: assets.length, 4: crypto.filter(a => a.market_count === 4).length, 3: crypto.filter(a => a.market_count === 3).length, 2: crypto.filter(a => a.market_count === 2).length };
}

/** Rows to show, in publication order: crypto-assets first, then (under "Tous"
 *  only) the currencies and stablecoins as a final, uncounted group. */
export function filterAssets(assets: UniverseAsset[], q: string, cov: Coverage | null): { crypto: AssetMatch[]; others: AssetMatch[] } {
  const hits = assets.map(a => matchAsset(a, q)).filter((m): m is AssetMatch => m !== null);
  const crypto = hits.filter(m => m.asset.asset_class === "CRYPTO" && (cov === null || m.asset.market_count === cov));
  const others = cov === null ? hits.filter(m => m.asset.asset_class !== "CRYPTO") : [];
  return { crypto, others };
}

/** Writes q and cov into a copy of the current query string, keeping every other parameter (product…). */
export function withAssetSearch(params: URLSearchParams, q: string, cov: Coverage | null): URLSearchParams {
  const next = new URLSearchParams(params);
  const nq = normalizeQuery(q);
  if (nq) next.set("q", nq); else next.delete("q");
  if (cov !== null) next.set("cov", String(cov)); else next.delete("cov");
  return next;
}
