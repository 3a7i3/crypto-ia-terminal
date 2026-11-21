// Capture figée lue par le panneau Footprint (vue unique BTC_USDT).
//
// Le fichier est un artefact statique livré avec la release, jamais un flux en
// direct. Il est vérifié à l'octet près par son empreinte SHA-256 attendue. Il ne change aucune autorité : PAPER, PPL et FIN n'en dépendent pas.
// Un fichier absent ou invalide reste visible comme tel ; aucune donnée n'est
// fabriquée pour le remplacer.
import type { FootprintTrade } from "./footprintEngine";

export const FOOTPRINT_REPLAY_URL = "/observations/footprint/mexc-btc_usdt-perp-replay-v1.json";
export const FOOTPRINT_REPLAY_SCHEMA = "cat.footprint.replay.v1";
export const FOOTPRINT_REPLAY_MAX_TRADES = 500_000;
/** Empreinte du fichier MEXC livré : tout autre contenu est refusé. */
export const FOOTPRINT_REPLAY_SHA256 = "a41c608814c02a10e5a9369b11806196b770ad578db0d5037368413c4cce391f";

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
  | { status: "ready"; replay: FootprintReplay; sha256: string; bytes: number };

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

// SHA-256 en JavaScript pur : WebCrypto n'existe pas hors contexte sécurisé (HTTP
// non local). L'empreinte doit pouvoir être vérifiée partout où le fichier est lu.
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);
export function sha256HexSync(data: Uint8Array): string {
  const len = data.length; const padded = new Uint8Array(((len + 9 + 63) >> 6) << 6);
  padded.set(data); padded[len] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, Math.floor(len / 0x20000000)); view.setUint32(padded.length - 4, (len << 3) >>> 0);
  const h = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
  const w = new Uint32Array(64);
  const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n));
  for (let off = 0; off < padded.length; off += 64) {
    for (let i = 0; i < 16; i += 1) w[i] = view.getUint32(off + i * 4);
    for (let i = 16; i < 64; i += 1) {
      const a = w[i - 15]; const b = w[i - 2];
      w[i] = (w[i - 16] + (rotr(a, 7) ^ rotr(a, 18) ^ (a >>> 3)) + w[i - 7] + (rotr(b, 17) ^ rotr(b, 19) ^ (b >>> 10))) >>> 0;
    }
    let [a, b, c, d, e, f, g, hh] = h;
    for (let i = 0; i < 64; i += 1) {
      const t1 = (hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) >>> 0;
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
      hh = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
  return [...h].map((x) => x.toString(16).padStart(8, "0")).join("");
}

/**
 * Charge la capture figée. Une réponse HTML (repli SPA du serveur) signifie que le
 * fichier n'est pas livré. L'empreinte est calculée sur les octets reçus, avant
 * toute interprétation ; `expectedSha256 = null` ne sert qu'aux fixtures de test.
 */
export async function loadFootprintReplay(
  fetchImpl: typeof fetch = fetch, url = FOOTPRINT_REPLAY_URL, expectedSha256: string | null = FOOTPRINT_REPLAY_SHA256,
): Promise<FootprintReplayState> {
  let response: Response;
  let bytes: Uint8Array;
  try {
    response = await fetchImpl(url, { cache: "no-store", headers: { accept: "application/json" } });
    const type = response.headers?.get?.("content-type") ?? "";
    if (response.status === 404 || (response.ok && !type.includes("json"))) {
      return { status: "absent", detail: `${url} non livré avec cette release` };
    }
    if (!response.ok) return { status: "error", message: `HTTP ${response.status}` };
    bytes = new Uint8Array(await response.arrayBuffer());
  } catch (error) {
    return { status: "error", message: error instanceof Error ? error.message : String(error) };
  }
  const sha256 = sha256HexSync(bytes);
  if (expectedSha256 !== null && sha256 !== expectedSha256) {
    return { status: "invalid", reason: `empreinte SHA-256 ${sha256.slice(0, 12)}… différente de l'empreinte attendue ${expectedSha256.slice(0, 12)}…` };
  }
  let parsed: unknown;
  try { parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); } catch { return { status: "invalid", reason: "JSON illisible" }; }
  try {
    return { status: "ready", replay: parseFootprintReplay(parsed), sha256, bytes: bytes.length };
  } catch (error) {
    if (error instanceof FootprintReplayError) return { status: "invalid", reason: error.message };
    throw error;
  }
}
