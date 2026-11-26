import { usePassiveSnapshot } from "../lib/usePassiveSnapshot";
import type { StorageState } from "../lib/storage";

const categories = ["raw", "candles", "generations", "root"] as const;
const errors = ["STORAGE_INVENTORY_UNAVAILABLE"];
type Category = typeof categories[number];
type Row = { files: number; bytes: number; modified_at: string | null };
type Inventory = {
  version: 1;
  agent_reports?: { observed_at: string; runs: Pick<Row, "files" | "bytes">; rehearsals: Pick<Row, "files" | "bytes"> } | null;
  observed_at: string;
  scanner: Record<Category, Row> | null;
  disk: { total_bytes: number; used_bytes: number; available_bytes: number };
};

const uint = (x: unknown): x is number => Number.isSafeInteger(x) && Number(x) >= 0;
const stamp = (x: unknown): x is string => typeof x === "string" && x.endsWith("Z") && Number.isFinite(Date.parse(x));

function valid(value: unknown): value is Inventory {
  const doc = value as Inventory | null;
  if (!doc || doc.version !== 1 || !stamp(doc.observed_at)) return false;
  const d = doc.disk;
  if (!d || !uint(d.total_bytes) || !d.total_bytes || !uint(d.used_bytes) ||
      !uint(d.available_bytes) || d.used_bytes + d.available_bytes > d.total_bytes) return false;
  const reports = doc.agent_reports;
  if (reports != null && (!stamp(reports.observed_at) ||
      ![reports.runs, reports.rehearsals].every(row => row && uint(row.files) && uint(row.bytes)))) return false;
  if (doc.scanner === null) return true;
  const scanner = doc.scanner;
  return !!scanner && categories.every(key => {
    const row = scanner[key];
    return !!row && uint(row.files) && uint(row.bytes) &&
      (row.files ? stamp(row.modified_at) : row.bytes === 0 && row.modified_at === null);
  }) && uint(categories.reduce((sum, key) => sum + scanner[key].bytes, 0));
}

const size = (bytes: number) => new Intl.NumberFormat("fr-FR", {
  maximumSignificantDigits: 3,
}).format(bytes >= 1e9 ? bytes / 1e9 : bytes >= 1e6 ? bytes / 1e6 : bytes >= 1e3 ? bytes / 1e3 : bytes)
  + (bytes >= 1e9 ? " Go" : bytes >= 1e6 ? " Mo" : bytes >= 1e3 ? " ko" : " octets");

const labels = { raw: "Données brutes", candles: "Bougies", generations: "Générations", root: "Fichiers à la racine" };

const localDate = (value: string) => new Date(value).toLocaleString("fr-FR", {
  dateStyle: "short", timeStyle: "short",
});
const exactSize = (bytes: number) => `${bytes.toLocaleString("fr-FR")} octets`;

function ageLabel(stamp: string) {
  const minutes = Math.floor((Date.now() - Date.parse(stamp)) / 60_000);
  if (minutes < 0) return "Heure du relevé à vérifier";
  if (minutes === 0) return "Relevé il y a moins d’une minute";
  if (minutes < 60) return `Relevé il y a ${minutes} min`;
  return `Relevé il y a ${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

export function StorageInventory({ packets }: { packets: StorageState }) {
  const state = usePassiveSnapshot("/api/operator/v1/storage-inventory", valid,
    errors, "STORAGE_INVENTORY");
  const snapshot = state.status === "success" ? state.snapshot : null;
  const scanner = snapshot?.scanner ?? null;
  const disk = snapshot?.disk;
  const dp = packets.status === "success" && packets.snapshot.source_status === "PRESENT"
    ? packets.snapshot.total_bytes : null;
  const reports = snapshot?.agent_reports;
  const rows = [
    { label: "Scanner MEXC Spot", bytes: scanner ? categories.reduce((sum, key) => sum + scanner[key].bytes, 0) : null, color: "#168574" },
    { label: "DecisionPackets historiques", bytes: dp, color: "#7765b6" },
    { label: "Rapports du cartographe", bytes: reports ? reports.runs.bytes + reports.rehearsals.bytes : null, color: "#bd6628" },
  ];
  const total = rows.reduce((sum, row) => sum + (row.bytes ?? 0), 0);
  let angle = 0;
  const stops = rows.filter(row => row.bytes).map(row => {
    const start = angle;
    angle += row.bytes! / total * 360;
    return `${row.color} ${start}deg ${angle}deg`;
  });

  return <article className="direction-card direction-card-governed">
    <h3>Stockage CAT</h3>
    <section aria-label="Disque VPS">
      <strong>Disque VPS</strong>
      {disk ? <><p>{size(disk.available_bytes)} disponibles sur {size(disk.total_bytes)}</p>
        <meter aria-label="Espace utilisé sur le disque du VPS" max={disk.total_bytes} value={disk.used_bytes} />
        {snapshot && <p><strong>{ageLabel(snapshot.observed_at)}</strong>
          {Date.now() - Date.parse(snapshot.observed_at) > 180_000 && <span> · Relevé ancien</span>}
          <br /><time dateTime={snapshot.observed_at}>{localDate(snapshot.observed_at)}</time></p>}</>
        : <p>Jauge indisponible</p>}
    </section>
    <section aria-label="Volume logique mesuré">
      <strong>Volume logique mesuré</strong>
      {total > 0 && <div aria-hidden="true" style={{ width: 128, aspectRatio: "1", marginBlock: 12,
        background: `conic-gradient(${stops.join(",")})`, borderRadius: "50%",
        maskImage: "radial-gradient(transparent 54%, black 55%)" }} />}
      <p>{rows.some(row => row.bytes !== null) ? exactSize(total) : "Indisponible"}</p>
      <ul style={{ listStyle: "none", paddingInlineStart: 0 }}>{rows.map(row => <li key={row.label}><span aria-hidden="true" style={{ color: row.color }}>● </span>
        {row.label} · {row.bytes === null ? "Indisponible" : exactSize(row.bytes)}</li>)}</ul>
      <p>Périmètre : Scanner, DecisionPackets et rapports du cartographe. Historique BBO et PAPER hors mesure.</p>
      {reports && <details><summary>Rapports du cartographe</summary>
        <p>Relevé du <time dateTime={reports.observed_at}>{localDate(reports.observed_at)}</time></p>
        <dl>
          <dt>Exécutions · résultats et preuves d’invocation</dt>
          <dd>{reports.runs.files} fichiers · {exactSize(reports.runs.bytes)}</dd>
          <dt>Répétitions · essais avant branchement</dt>
          <dd>{reports.rehearsals.files} fichiers · {exactSize(reports.rehearsals.bytes)}</dd>
        </dl>
      </details>}
      {scanner && <details><summary>Catégories du scanner</summary>
        <dl className="direction-fact-grid">{categories.map(key => <div key={key}>
          <dt>{labels[key]}</dt><dd>{scanner[key].files} fichiers · {size(scanner[key].bytes)}</dd>
          <dd>{scanner[key].modified_at ? <time dateTime={scanner[key].modified_at}>
            {localDate(scanner[key].modified_at)}
          </time> : "Aucune modification observée"}</dd>
        </div>)}</dl>
      </details>}
    </section>
  </article>;
}
