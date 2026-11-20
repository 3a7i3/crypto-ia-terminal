// Rejeu historique pour le panneau Footprint (mode Démo historique).
//
// Le fichier est un artefact statique livré avec la release, jamais un flux en
// direct. Il ne change aucune autorité : PAPER, PPL et FIN n'en dépendent pas.
// Un fichier absent ou invalide reste visible comme tel ; aucune donnée n'est
// fabriquée pour le remplacer.
import type { FootprintTrade } from "./footprintEngine";

export const FOOTPRINT_REPLAY_URL = "/observations/footprint/mexc-btc_usdt-perp-replay-v1.json";
export const FOOTPRINT_REPLAY_SCHEMA = "cat.footprint.replay.v1";
export const FOOTPRINT_REPLAY_MAX_TRADES = 500_000;

export interface FootprintReplayGap { from_utc: string; to_utc: string }
export interface FootprintReplayProvenance {
  venue: "MEXC";
  market_type: "perpetual";
  symbol: "BTC_USDT";
  /** Endpoint, collecteur ou archive d'origine. */
  source: string;
  collected_at_utc: string;
  coverage_from_utc: string;
  coverage_to_utc: string;
  /** Unité de `qty` telle que publiée par la source. */
  qty_unit: "contracts" | "base";
  side_semantics: "aggressor";
  gaps: FootprintReplayGap[];
  notes?: string;
}
export interface FootprintReplay {
  schema: typeof FOOTPRINT_REPLAY_SCHEMA;
  provenance: FootprintReplayProvenance;
  tick_size: number;
  trades: FootprintTrade[];
}

export type FootprintReplayState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "absent"; detail: string }
  | { status: "invalid"; reason: string }
  | { status: "error"; message: string }
  | { status: "ready"; replay: FootprintReplay; sha256: string | null; bytes: number };

const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const isIso = (v: unknown): v is string => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(v) && Number.isFinite(Date.parse(v));

export class FootprintReplayError extends Error {}

/** Valide la structure du rejeu. Les transactions elles-mêmes sont validées par le moteur, qui compte les rejets. */
export function parseFootprintReplay(input: unknown): FootprintReplay {
  const fail = (reason: string): never => { throw new FootprintReplayError(reason); };
  if (!isObject(input)) fail("document non objet");
  const doc = input as Record<string, unknown>;
  if (doc.schema !== FOOTPRINT_REPLAY_SCHEMA) fail(`schéma attendu ${FOOTPRINT_REPLAY_SCHEMA}`);
  const p = doc.provenance;
  if (!isObject(p)) fail("provenance absente");
  const prov = p as Record<string, unknown>;
  if (prov.venue !== "MEXC" || prov.market_type !== "perpetual" || prov.symbol !== "BTC_USDT") {
    fail("le rejeu doit porter sur BTC_USDT perpétuel MEXC");
  }
  if (typeof prov.source !== "string" || prov.source.trim() === "") fail("source de provenance absente");
  for (const key of ["collected_at_utc", "coverage_from_utc", "coverage_to_utc"] as const) {
    if (!isIso(prov[key])) fail(`${key} doit être une date UTC ISO 8601`);
  }
  const from = Date.parse(prov.coverage_from_utc as string);
  const to = Date.parse(prov.coverage_to_utc as string);
  if (!(from < to)) fail("fenêtre de couverture vide ou inversée");
  if (prov.qty_unit !== "contracts" && prov.qty_unit !== "base") fail("qty_unit doit valoir contracts ou base");
  if (prov.side_semantics !== "aggressor") fail("side_semantics doit valoir aggressor");
  if (!Array.isArray(prov.gaps)) fail("gaps doit être une liste (vide si aucune lacune connue)");
  for (const g of prov.gaps as unknown[]) {
    if (!isObject(g) || !isIso(g.from_utc) || !isIso(g.to_utc) || !(Date.parse(g.from_utc) < Date.parse(g.to_utc))) fail("lacune de couverture invalide");
  }
  if (prov.notes !== undefined && typeof prov.notes !== "string") fail("notes doit être un texte");
  const tick = doc.tick_size;
  if (typeof tick !== "number" || !Number.isFinite(tick) || tick <= 0) fail("tick_size doit être un nombre fini > 0");
  if (!Array.isArray(doc.trades) || doc.trades.length === 0) fail("aucune transaction");
  if ((doc.trades as unknown[]).length > FOOTPRINT_REPLAY_MAX_TRADES) fail(`plus de ${FOOTPRINT_REPLAY_MAX_TRADES} transactions`);
  for (const t of doc.trades as unknown[]) {
    // Une transaction hors fenêtre déclarée rendrait la couverture affichée fausse.
    if (isObject(t) && typeof t.ts === "number" && (t.ts < from || t.ts > to)) fail("transaction hors de la fenêtre de couverture déclarée");
  }
  return doc as unknown as FootprintReplay;
}

async function sha256Hex(text: string): Promise<string | null> {
  try {
    const subtle = globalThis.crypto?.subtle;
    if (!subtle) return null;
    const digest = await subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  } catch {
    return null;
  }
}

/** Charge le rejeu. Une réponse HTML (repli SPA du serveur) signifie que le fichier n'est pas livré. */
export async function loadFootprintReplay(fetchImpl: typeof fetch = fetch, url = FOOTPRINT_REPLAY_URL): Promise<FootprintReplayState> {
  let response: Response;
  try {
    response = await fetchImpl(url, { cache: "no-store", headers: { accept: "application/json" } });
  } catch (error) {
    return { status: "error", message: error instanceof Error ? error.message : String(error) };
  }
  const type = response.headers?.get?.("content-type") ?? "";
  if (response.status === 404 || (response.ok && !type.includes("json"))) {
    return { status: "absent", detail: `${url} non livré avec cette release` };
  }
  if (!response.ok) return { status: "error", message: `HTTP ${response.status}` };
  const text = await response.text();
  let parsed: unknown;
  try { parsed = JSON.parse(text); } catch { return { status: "invalid", reason: "JSON illisible" }; }
  try {
    const replay = parseFootprintReplay(parsed);
    return { status: "ready", replay, sha256: await sha256Hex(text), bytes: new TextEncoder().encode(text).length };
  } catch (error) {
    if (error instanceof FootprintReplayError) return { status: "invalid", reason: error.message };
    throw error;
  }
}
