import { defineConfig } from "vitest/config";

// VR_PORT: each checkout or agent picks its own port (docs/WORKFLOWS.md section 0).
const port = Number(process.env.VR_PORT ?? 5187);

// VR_E2E=1 also builds the runtime e2e harness page (src/app/e2e/), for Playwright. Normal builds leave it out.
const e2e = process.env.VR_E2E === "1";

export default defineConfig({
  build: e2e
    ? { rolldownOptions: { input: { main: "index.html", e2e: "src/app/e2e/index.html" } } }
    : {},
  server: {
    port,
    host: "127.0.0.1",
    strictPort: true,
    // The repo's schema/ and vector folders live one level up and are imported directly.
    fs: { allow: [".."] },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    // CPU-heavy analytic checks take 3-6 s on the GitHub runner, near Vitest's 5 s default.
    testTimeout: 30_000,
  },
});
