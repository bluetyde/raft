/**
 * M4 end-to-end check of the app: the runtime worker drives the explorer, and the controls
 * send commands through the bus. Real clicks in Chromium on the production build.
 */

import { expect, test, type Page } from "@playwright/test";

async function rods(page: Page): Promise<Record<string, number>> {
  return page.evaluate(() => (window as any).vr.explorer.rodPositions);
}

async function readout(page: Page, key: string): Promise<string> {
  return (await page.locator(`[data-readout="${key}"]`).textContent()) ?? "";
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
  await page.selectOption(".vr-bar select >> nth=0", "synthetic-core");
  await expect(page.locator("#app")).toHaveAttribute("data-library", "synthetic-core", { timeout: 30_000 });
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true");
  // these checks are for the M4 explorer layout (3D, truth read-out and controls)
  await page.selectOption('[data-op="layout"]', "explorer");
});

test("withdrawing a rod moves it in the 3D view, raises power, and colours the fuel by live power", async ({ page }) => {
  const r0 = (await rods(page))["regulating"]!;
  const power = () => page.evaluate(() => (window as any).vr.snapshot.truth.power as number);
  const p0 = await power();
  await page.click('[data-control="play"]');
  await page.selectOption('[data-control="rate"]', "10");
  await page.click('[data-control="regulating:out"]');
  await expect(page.locator(".vr-controls .vr-note")).toContainText("rod.move accepted", { timeout: 10_000 });
  await expect.poll(async () => (await rods(page))["regulating"]!, { timeout: 15_000 }).toBeGreaterThan(r0 + 0.05);

  // the rod in the 3D scene is where the read-out says it is: both come from the same snapshot handler, so read
  // them in one page task (two separate reads race the moving rod: 20 %/s at 10x)
  const both = await page.evaluate(() => {
    const row = [...document.querySelectorAll(".vr-controls .vr-row")].find((r) => r.textContent!.includes("regulating"))!;
    return { shown: Number.parseFloat(row.querySelector(".vr-pos")!.textContent!), scene: (window as any).vr.explorer.rodPositions.regulating };
  });
  expect(Math.abs(both.shown - 100 * both.scene)).toBeLessThanOrEqual(0.051); // the read-out rounds to 0.1 %

  // live overlay: fuel instances carry colours, and they are not all the same
  const colours = await page.evaluate(() => {
    const core = (window as any).vr.explorer.core;
    const fuel = core.groups.filter((g: any) => g.material === "fuel");
    const out: string[] = [];
    for (const g of fuel) {
      const arr = g.mesh.instanceColor?.array;
      if (!arr) continue;
      for (let i = 0; i < g.mesh.count; i++) out.push(`${arr[3 * i].toFixed(3)},${arr[3 * i + 1].toFixed(3)},${arr[3 * i + 2].toFixed(3)}`);
    }
    return out;
  });
  expect(colours.length).toBeGreaterThan(0);
  expect(new Set(colours).size).toBeGreaterThan(1);
  expect(await readout(page, "trips")).toBe("none");
  await expect.poll(power, { timeout: 15_000 }).toBeGreaterThan(1.5 * p0);
});

test("SCRAM trips the reactor and drops the rods; a withdrawal is then rejected with the engine's reason", async ({ page }) => {
  await page.click('[data-control="play"]');
  await page.selectOption('[data-control="rate"]', "10");
  // the synthetic core starts with every rod in, so withdraw one first and see it up in the 3D view
  await page.click('[data-control="regulating:out"]');
  await expect.poll(async () => (await rods(page))["regulating"]!, { timeout: 15_000 }).toBeGreaterThan(0.05);
  await page.click('[data-control="scram"]');
  await expect(page.locator(".vr-controls .vr-note")).toContainText("scram accepted", { timeout: 10_000 });
  await expect.poll(() => readout(page, "trips"), { timeout: 10_000 }).toContain("manual");
  await expect
    .poll(async () => Math.max(...Object.values(await rods(page))), { timeout: 20_000 })
    .toBeLessThan(0.01);
  await page.click('[data-control="safety:out"]');
  await expect(page.locator(".vr-controls .vr-note")).toContainText("rejected: REJ_TRIPPED", { timeout: 10_000 });
});

test("pause stops sim time; the clock shows the achieved rate while running", async ({ page }) => {
  await page.click('[data-control="play"]');
  await expect(page.locator(".vr-clock")).toContainText("achieved", { timeout: 10_000 });
  await page.click('[data-control="play"]');
  await expect(page.locator(".vr-clock")).toContainText("paused", { timeout: 10_000 });
  const t = await readout(page, "sim time");
  await page.waitForTimeout(400);
  expect(await readout(page, "sim time")).toBe(t);
});
