// Harnais synthétique de la preuve d'invocation. Aucune donnée réelle : scénarios figés,
// choisis par le cookie `cart-scenario`. Aucun proxy, aucune lecture du VPS.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Chaque réponse est calculée à la requête : la date d'observation serveur est « maintenant ».
const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");

function scenario(name: string): { status: number; body?: unknown } {
  const now = Date.now();
  const ago = (m: number) => iso(now - m * 60_000);
  const ttl = iso(now + 90_000);
  const base = {
    contract: "cat.observation.invocation.v1",
    agent_id: "repository-cartographer",
    runner_id: "obs-repo-cartographer-ro-01",
    mission_id: "02e0f78f43d1062ee0efed015ad9fe37329dbe480062f02c53e32c82e19fdece",
    server_observed_at_utc: iso(now),
    connection: "AVAILABLE",
    connection_reason: "dernière preuve valide",
    activity: "TERMINE",
    activity_reason: "dernière invocation COMPLETED (aucun processus ne détient le verrou)",
    life_observed: false,
    lease_until_utc: null,
    last_activity_utc: ago(6),
    last_mission_age_s: 360,
    mission_overdue: false,
    last_result: "PARTIAL",
    last_state: "COMPLETED",
    invocation_id: "9f1c2e7a4b6d8e0f1a2b3c4d5e6f7a8b",
    display: { light: "RED", label: "Inactif · fin normale", reason: "dernière invocation COMPLETED", valid_until_utc: ttl },
    read_only: true,
  };
  const running = {
    ...base,
    activity: "EN_COURS",
    activity_reason: "verrou noyau tenu, bail valide",
    life_observed: true,
    lease_until_utc: iso(now + 240_000),
    last_activity_utc: ago(1),
    display: { light: "GREEN", label: "Actif", reason: "exécution en cours attestée", valid_until_utc: ttl },
  };
  switch (name) {
    case "running":
      return { status: 200, body: running };
    case "failed":
      return { status: 200, body: { ...base, last_state: "TIMEOUT", last_result: null, activity_reason: "dernière invocation TIMEOUT",
        display: { light: "RED", label: "Inactif · échec", reason: "dernière invocation TIMEOUT", valid_until_utc: ttl } } };
    case "overdue":
      return { status: 200, body: { ...base, last_activity_utc: ago(40 * 60), last_mission_age_s: 40 * 3600, mission_overdue: true,
        display: { ...base.display, label: "Inactif · fin normale · aucune mission depuis plus de 36 h" } } };
    case "invalid-running":
      // Verrou tenu mais preuve INVALID : le serveur annonce gris ; l'interface ne verdit jamais.
      return { status: 200, body: { ...running, connection: "INVALID", connection_reason: "INVALID: empreinte du contenu altérée",
        last_result: null, last_state: null,
        display: { light: "GRAY", label: "Non attesté", reason: "exécution signalée mais preuve INVALID", valid_until_utc: null } } };
    case "hostile-green":
      // Réponse incohérente (vert annoncé sans observation de vie) : filtrée en gris.
      return { status: 200, body: { ...running, life_observed: false } };
    case "expired":
      // Vert annoncé avec une échéance déjà passée : gris immédiat.
      return { status: 200, body: { ...running, display: { ...running.display, valid_until_utc: iso(now) } } };
    case "outage":
      return { status: 503 };
    default:
      return { status: 200, body: base };
  }
}

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
        // « hang » : le serveur ne répond jamais (requête bloquée, contrôle d'échéance).
        if (name === "hang") return;
        const s = scenario(name);
        response.statusCode = s.status;
        response.end(s.body === undefined ? "{}" : JSON.stringify(s.body));
      });
    },
  }],
  server: { port: 5179, strictPort: true, fs: { allow: [".."] } },
});
