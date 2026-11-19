import { defineConfig, mergeConfig } from "vite";
import base from "./vite.config";

// M1-C5 (EO-026, D3): separate build of the CI-only CryptoRadar historique
// compatibility proof page. Output goes to dist-legacy-proof/, never to the
// production dist/; the production build (vite.config.ts) keeps index.html as
// its only entry. Same dev proxy and plugins as the application.
export default defineConfig((env) => mergeConfig(
  typeof base === "function" ? base(env) : base,
  {
    build: {
      outDir: "dist-legacy-proof",
      emptyOutDir: true,
      rollupOptions: { input: { "market-scanner": "legacy-proof/market-scanner.html" } },
    },
  },
));
