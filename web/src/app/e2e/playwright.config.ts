/**
 * Playwright config for the runtime end-to-end check (TODO Next #8). From web/:
 *   npx playwright test -c src/app/e2e/playwright.config.ts
 * It builds the app with the e2e harness page (VR_E2E=1) and serves the production build.
 * VR_CHROMIUM: an optional Chromium executable (for machines without Playwright's own browser build).
 */

import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const port = Number(process.env.VR_E2E_PORT ?? 5189);

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  // Outside the repo, so failed-run traces never show up in git status.
  outputDir: join(tmpdir(), "virtual-reactor-e2e"),
  timeout: 90_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${port}`,
    browserName: "chromium",
    launchOptions: process.env.VR_CHROMIUM ? { executablePath: process.env.VR_CHROMIUM } : {},
  },
  webServer: {
    command: `npx vite build && npx vite preview --port ${port} --strictPort`,
    cwd: "../../..",
    env: { VR_E2E: "1" },
    url: `http://localhost:${port}/src/app/e2e/index.html`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
