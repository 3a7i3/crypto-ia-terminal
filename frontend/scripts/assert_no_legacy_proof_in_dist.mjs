// M1-C5 (EO-026, D3): the production build must not contain the CI-only
// CryptoRadar historique proof page nor the withdrawn scanner component.
// Run after `npm run build`; exits non-zero with the offending evidence.
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(process.argv[2] || path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "dist"));
const MARKERS = [
  "legacy-proof",            // proof page path, banner test id, data-proof attribute
  "market-scanner-coverage", // MarketScanner-only test id
  "market-opportunity-row",  // MarketScanner-only test id
  "Preuve de compatibilité · CryptoRadar historique",
];
async function walk(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...await walk(full)); else out.push(full);
  }
  return out;
}
const files = await walk(root);
const problems = [];
const html = files.filter((f) => f.endsWith(".html")).map((f) => path.relative(root, f));
if (html.length !== 1 || html[0] !== "index.html") problems.push("unexpected HTML entries: " + html.join(", "));
if (!files.some((f) => /assets[\\/]index-[^\\/]+\.js$/.test(f))) problems.push("no application bundle under assets/ (wrong directory?)");
for (const file of files) {
  // Markup and code only: the shared stylesheets keep the historical class
  // names (styling is not a mounted component and reads no source).
  if (!/\.(html|js|json|webmanifest)$/.test(file)) continue;
  const text = await readFile(file, "utf8");
  for (const marker of MARKERS) if (text.includes(marker)) problems.push(`${path.relative(root, file)} contains ${JSON.stringify(marker)}`);
}
if (problems.length) {
  console.error("LEGACY_PROOF_IN_PRODUCTION_BUILD=FAIL\n" + problems.join("\n"));
  process.exit(1);
}
console.log(`LEGACY_PROOF_ABSENT_FROM_PRODUCTION_BUILD=PASS files=${files.length} root=${root}`);
