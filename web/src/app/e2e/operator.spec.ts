/**
 * M5 end-to-end check of the operator panel (docs/m5-operator-design.md section 6), with real clicks
 * on the production build and the synthetic core.
 */

import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

async function view(page: Page) {
  return page.evaluate(() => (window as any).vr.operator.lastView);
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
  await page.selectOption(".vr-bar select >> nth=0", "synthetic-core");
  await expect(page.locator("#app")).toHaveAttribute("data-library", "synthetic-core", { timeout: 30_000 });
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true");
});

test("the default layout is split: the operator panel with a 3D inset, and no truth read-out", async ({ page }) => {
  await expect(page.locator("#app")).toHaveAttribute("data-layout", "split");
  await expect(page.locator(".vr-opbox")).toBeVisible();
  await expect(page.locator(".vr-view")).toBeVisible();
  await expect(page.locator(".vr-side")).toBeHidden(); // the M4 truth read-out
  await expect(page.locator(".vr-panel")).toBeHidden(); // the explorer's own panel, in the inset
  // every library instrument has a meter, plus the derived period
  for (const id of ["linear", "log", "fuel-tc", "pool-temp", "period"]) await expect(page.locator(`[data-meter="${id}"]`)).toBeVisible();
});

test("withdrawing a rod from the operator panel raises the log reading, and the period meter reads", async ({ page }) => {
  const log0 = (await view(page)).indicated.log;
  await expect(page.locator('[data-meter="period"] .vr-value')).toHaveText("—");
  await page.click('[data-op="play"]');
  await page.selectOption('[data-op="rate"]', "10");
  await page.click('[data-op="regulating:out"]');
  await expect(page.locator(".vr-operator > .vr-note")).toContainText("rod.move accepted", { timeout: 10_000 });
  await expect.poll(async () => (await view(page)).indicated.log, { timeout: 20_000 }).toBeGreaterThan(1.5 * log0);
  // at 10x, 30 Hz snapshots are 0.33 s of sim time apart: too few readings in the 2 s window, so "—"
  await expect(page.locator('[data-meter="period"] .vr-value')).toHaveText("—");
  // at 1x there are about 60 readings per window, and the meter reads
  await page.selectOption('[data-op="rate"]', "1");
  await expect.poll(() => page.locator('[data-meter="period"] .vr-value').textContent(), { timeout: 15_000 }).not.toBe("—");
  // the operator panel's view never holds truth physics
  const v = await view(page);
  expect(Object.keys(v).sort()).toEqual(["console", "indicated"]);
  expect(JSON.stringify(v)).not.toContain('"power"');
});

test("SCRAM needs its cover lifted; the trip tile flashes until acknowledged; a withdrawal is then rejected", async ({ page }) => {
  await page.click('[data-op="play"]');
  await page.selectOption('[data-op="rate"]', "10");
  await page.click('[data-op="regulating:out"]');
  await expect(page.locator('[data-light="regulating:down"]')).not.toHaveClass(/on/, { timeout: 15_000 });
  await expect(page.locator('[data-op="scram"]')).toBeHidden();
  await page.click('[data-op="scram-cover"]');
  await page.click('[data-op="scram"]');
  const tile = page.locator('[data-tile="trip:manual"]');
  await expect(tile).toHaveAttribute("data-state", "flashing", { timeout: 10_000 });
  await page.click('[data-op="ack"]');
  await expect(tile).toHaveAttribute("data-state", "lit");
  for (const rod of ["safety", "regulating", "transient"]) {
    await expect(page.locator(`[data-light="${rod}:down"]`)).toHaveClass(/on/, { timeout: 20_000 });
  }
  await page.click('[data-op="safety:out"]');
  await expect(page.locator(".vr-operator > .vr-note")).toContainText("rejected: REJ_TRIPPED", { timeout: 10_000 });
});

test("the cover closes again on Esc, without a SCRAM", async ({ page }) => {
  await page.click('[data-op="scram-cover"]');
  await expect(page.locator('[data-op="scram"]')).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-op="scram"]')).toBeHidden();
  expect((await view(page)).console.tripped).toBe(false);
});

test("realism hides the 3D inset and the truth read-out; explorer brings the M4 view back", async ({ page }) => {
  await page.selectOption('[data-op="layout"]', "realism");
  await expect(page.locator(".vr-view")).toBeHidden();
  await expect(page.locator(".vr-side")).toBeHidden();
  await expect(page.locator(".vr-opbox")).toBeVisible();
  await page.selectOption('[data-op="layout"]', "explorer");
  await expect(page.locator(".vr-opbox")).toBeHidden();
  await expect(page.locator(".vr-view")).toBeVisible();
  await expect(page.locator(".vr-side")).toBeVisible();
});

test("a pulse peak between snapshots reaches the log chart at full height; the period shows — in pulse mode", async ({ page }) => {
  // a real pulse: the golden pulse vector's start state (pulse mode, rods near critical); it peaks at about 1.8e8 W at 0.14 s
  const pulse = JSON.parse(readFileSync(fileURLToPath(new URL("../../../../schema/engine-vectors/pulse.json", import.meta.url)), "utf8"));
  await page.evaluate(async (init) => {
    const w = window as any;
    await w.vr.show("synthetic-core", { init });
    w.__snaps = [];
    w.vr.client.on("snapshot", (m: any) => w.__snaps.push({ log: m.snapshot.indicated.log, ext: m.extremes?.log?.max ?? null }));
  }, pulse.init);
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
  await expect(page.locator('[data-op="transient:fire"]')).toBeEnabled({ timeout: 10_000 });
  if (process.env.VR_E2E_THROTTLE) {
    // reproduce a slow CI runner: slow the page's CPU (the worker runs slower too)
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: Number(process.env.VR_E2E_THROTTLE) });
  }
  // FIRE while paused: the command queues and applies on step 0 (D2 of the C6 design), so the pulse timing does not
  // depend on how fast the page is. Then run.
  await page.click('[data-op="transient:fire"]');
  await page.click('[data-op="play"]');
  await expect(page.locator(".vr-operator > .vr-note")).toContainText("rod.fire accepted", { timeout: 30_000 });
  // wait in sim time, not wall time: pulse steps are slow (about 60 ms each here, more on CI), and the peak is at 0.14 s
  await expect.poll(async () => (await view(page))?.console.t ?? 0, { timeout: 60_000 }).toBeGreaterThan(0.6);
  const r = await page.evaluate(() => {
    const w = window as any;
    const snaps: { log: number; ext: number | null }[] = w.__snaps;
    const chart = w.vr.operator.charts.find((c: any) => c.meter !== "period" && c.meter.id === "log");
    return {
      plainMax: Math.max(...snaps.map((s) => s.log ?? -Infinity)),
      extMax: Math.max(...snaps.map((s) => s.ext ?? -Infinity)),
      chartMax: chart.buffer.max,
    };
  });
  expect(r.extMax).toBeGreaterThan(1e6); // it was a real pulse
  expect(r.extMax).toBeGreaterThanOrEqual(r.plainMax);
  // the chart keeps exactly the highest reading the worker saw. (During this pulse the runtime is CPU-bound, about
  // 60 ms per step, so it often sends a snapshot per step and the peak may also be in a plain snapshot; that the peak
  // survives between snapshots is tested deterministically in runtime.test.ts and operator.test.ts.)
  expect(r.chartMax).toBe(r.extMax);
  await expect(page.locator('[data-meter="period"] .vr-value')).toHaveText("—");
});
