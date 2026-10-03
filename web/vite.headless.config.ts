import { defineConfig } from "vite";

// Bundles the headless runner (src/headless/cli.ts) into one Node 24 ES module: dist-headless/raft-headless.mjs.
// Used by `npm run build:headless`; the browser build (vite.config.ts) never includes it.
export default defineConfig({
  build: {
    ssr: "src/headless/cli.ts",
    outDir: "dist-headless",
    emptyOutDir: true,
    target: "node24",
    minify: false,
    rolldownOptions: { output: { format: "esm", entryFileNames: "raft-headless.mjs" } },
  },
});
