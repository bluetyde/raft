import { defineConfig } from "vitest/config";

// VR_PORT: each checkout or agent picks its own port (docs/WORKFLOWS.md section 0).
const port = Number(process.env.VR_PORT ?? 5187);

export default defineConfig({
  server: {
    port,
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
