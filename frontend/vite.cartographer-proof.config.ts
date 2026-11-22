// Harnais synthétique de la preuve d'invocation. Aucune donnée réelle : scénarios figés,
// choisis par le cookie `cart-scenario`. Aucun proxy, aucune lecture du VPS.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const NOW = new Date();
const iso = (d: Date) => d.toISOString().replace(/\.\d{3}Z$/, "Z");
const minutesAgo = (m: number) => iso(new Date(NOW.getTime() - m * 60_000));

const base = {
  connection: "AVAILABLE",
  connection_reason: "dernière preuve valide",
  activity: "TERMINE",
  activity_reason: "dernière invocation COMPLETED",
  last_activity_utc: minutesAgo(6),
  last_result: "PARTIAL",
  last_state: "COMPLETED",
  invocation_id: "9f1c2e7a4b6d8e0f1a2b3c4d5e6f7a8b",
  observed_at_utc: minutesAgo(1),
  agent_id: "repository-cartographer",
  runner_id: "obs-repo-cartographer-ro-01",
  mission_id: "02e0f78f43d1062ee0efed015ad9fe37329dbe480062f02c53e32c82e19fdece",
  read_only: true,
  lock: { present: false },
};

const scenarios: Record<string, { status: number; body?: unknown }> = {
  partial: { status: 200, body: base },
  running: {
    status: 200,
    body: { ...base, activity: "EN_COURS", activity_reason: "bail valide", last_activity_utc: minutesAgo(2), lock: { present: true, reason: "bail valide" } },
  },
  failed: {
    status: 200,
    body: { ...base, last_state: "TIMEOUT", last_result: null, activity_reason: "dernière invocation TIMEOUT" },
  },
  invalid: {
    status: 200,
    body: { ...base, connection: "INVALID", connection_reason: "INVALID: empreinte du contenu altérée", activity: "INDETERMINE", last_activity_utc: null, last_result: null },
  },
  stale: {
    status: 200,
    body: { ...base, activity: "EN_COURS", observed_at_utc: minutesAgo(40), lock: { present: true, reason: "bail valide" } },
  },
  outage: { status: 503 },
};

export default defineConfig({
  root: "test-harness/cartographer-proof",
  plugins: [react(), {
    name: "cartographer-proof-synthetic",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url ?? "/", "http://localhost").pathname;
        if (!pathname.startsWith("/api/")) return next();
        response.setHeader("Content-Type", "application/json");
        response.setHeader("Cache-Control", "no-store");
        const name = request.headers.cookie?.match(/(?:^|; )cart-scenario=([^;]+)/)?.[1] ?? "partial";
        const s = scenarios[name] ?? scenarios.partial;
        response.statusCode = s.status;
        response.end(s.body === undefined ? "{}" : JSON.stringify(s.body));
      });
    },
  }],
  server: { port: 5179, strictPort: true, fs: { allow: [".."] } },
});
