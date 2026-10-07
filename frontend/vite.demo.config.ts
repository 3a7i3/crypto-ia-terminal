import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const fixtures: Record<string, string> = {
  snapshot: "A_minimal_canonical", market: "L_scanner", "market-microstructure": "M_microstructure",
  "ppl-comparison": "H_ppl_comparison", "research-lab": "N_research_publication",
  "research-strategies": "O_research_strategies", "financial-reconciliation": "P_financial_clarity",
  "burn-in": "J_burn_in", "runtime-service": "K_runtime_service",
};
export default defineConfig({
  plugins: [react(), {
    name: "isolated-synthetic-preview",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url ?? "/", "http://localhost").pathname;
        if (pathname.startsWith("/api/")) {
          // Fail closed: every API request terminates locally; no proxy or runtime fallback.
          response.setHeader("Content-Type", "application/json");
          response.setHeader("Cache-Control", "no-store");
          const scenario = request.headers.cookie?.match(/(?:^|; )ux-demo-scenario=([^;]+)/)?.[1];
          const key = pathname.replace("/api/operator/v1/", "");
          if (request.method !== "GET") { response.statusCode = 405; response.end('{}'); return; }
          try {
            if (scenario === "missing" || !fixtures[key]) throw new Error("missing");
            const fixture = JSON.parse(readFileSync(resolve(".cross-stack-fixtures", `${fixtures[key]}.json`), "utf8"));
            if (scenario === "stale" && "freshness_classification" in fixture.body) {
              fixture.body.freshness_classification = "STALE";
              fixture.body.snapshot_age_s = 86400;
            }
            response.statusCode = fixture.http_status;
            response.end(JSON.stringify(fixture.body));
          } catch {
            response.statusCode = 503;
            response.end(JSON.stringify({ error_code: "DEMO_SOURCE_INDISPONIBLE", error_message: "Source synthétique absente dans cet aperçu fictif." }));
          }
          return;
        }
        if (request.method === "GET" && request.headers.accept?.includes("text/html")) request.url = "/demo.html";
        next();
      });
    },
  }],
  server: { host: "0.0.0.0", port: 3002 },
  build: { outDir: "dist-demo", rollupOptions: { input: "demo.html" } },
});
