import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// O-02W-D2: dev proxy targets the O-02W-D1 read-only loopback operator API
// only. Default 127.0.0.1:8090; optionally overridden via the non-secret
// Vite env var VITE_OPERATOR_API_TARGET. No CORS is added to FastAPI — the
// proxy exists purely so the dev server can reach the loopback API.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const target = env.VITE_OPERATOR_API_TARGET || "http://127.0.0.1:8090";

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
        },
        "/healthz": {
          target,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
