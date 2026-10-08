/**
 * Not a check: writes the pictures used in README.md. Skipped unless VR_SCREENSHOTS names a folder. From web/:
 *   VR_SCREENSHOTS=../docs/images npx playwright test -c src/app/e2e/playwright.config.ts screenshots
 * It starts the OpenMC-built TRIGA core 242 on its low-power ascension scenario, withdraws the rods to about the critical
 * position and a little beyond, and lets the power rise by a few decades before the pictures.
 */

import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const dir = process.env.VR_SCREENSHOTS;
test.skip(!dir, "set VR_SCREENSHOTS=<folder> to write the README pictures");

const inst = (page: Page, name: string) => page.locator(`[data-inst="${name}"]`);

async function ready(page: Page, library: string) {
  await expect(page.locator("#app")).toHaveAttribute("data-library", library, { timeout: 30_000 });
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
}

test("README pictures", async ({ page }) => {
  test.setTimeout(240_000);
  mkdirSync(dir!, { recursive: true });
  await page.setViewportSize({ width: 1500, height: 1120 });
  await page.goto("/");
  await ready(page, "triga-jsi-242");
  await page.selectOption(".vr-bar select >> nth=0", "triga-jsi-242-openmc");
  await ready(page, "triga-jsi-242-openmc");
  await page.selectOption('[data-op="layout"]', "instructor");
  await inst(page, "scenario-choice").selectOption("triga-242-openmc-low-power-ascension");
  await inst(page, "scenario-start").click();
  await expect.poll(() => page.evaluate(() => (window as any).vr.instructor?.scenario?.id), { timeout: 30_000 }).toBe("triga-242-openmc-low-power-ascension");
  await ready(page, "triga-jsi-242-openmc");

  // The operator withdraws the transient and safety rods fully, the shim rod to its critical position (0.573) and the regulating
  // rod a little past it (0.60); the page stops each rod from the snapshot stream. The clock runs at 10x.
  await page.evaluate(() => {
    const vr = (window as any).vr;
    const stops: Record<string, number> = { shim: 0.573, regulating: 0.6 };
    const stopped = new Set<string>();
    vr.client.on("snapshot", (m: any) => {
      for (const [rid, limit] of Object.entries(stops)) {
        if (!stopped.has(rid) && m.snapshot.truth.rods[rid].position >= limit) {
          stopped.add(rid);
          void vr.client.command({ type: "rod.move", rod: rid, direction: "stop" }, undefined, "operator");
        }
      }
    });
    // not awaited: while the clock is paused a command is acknowledged only at the next step
    for (const rod of ["transient", "safety", "shim", "regulating"]) void vr.client.command({ type: "rod.move", rod, direction: "out" }, undefined, "operator");
    vr.client.setTime({ rate: 10, paused: false });
  });
  // run until the power is a few decades above the source level (a few watts), or give up after 100 s of wall time
  const start = Date.now();
  let power = 0;
  while (Date.now() - start < 100_000) {
    await page.waitForTimeout(500);
    power = await page.evaluate(() => (window as any).vr.snapshot?.truth?.power ?? 0);
    if (power > 3) break;
  }
  await page.evaluate(() => (window as any).vr.client.setTime({ paused: true }));
  await page.waitForTimeout(2500); // let the charts and the 3D overlay catch up
  console.log(`power at the pictures: ${power} W`);

  await page.screenshot({ path: join(dir!, "instructor.png") });
  await page.selectOption('[data-op="layout"]', "split");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: join(dir!, "operator-and-core.png") });
});
