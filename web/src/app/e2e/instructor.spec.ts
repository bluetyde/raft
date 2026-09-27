/**
 * M6 slice S1 end-to-end check of the instructor panel (docs/m6-instructor-design.md section 7), with real clicks
 * on the production build and the synthetic core.
 */

import { expect, test, type Page } from "@playwright/test";

const inst = (page: Page, name: string) => page.locator(`[data-inst="${name}"]`);

async function snapshotT(page: Page): Promise<number> {
  return page.evaluate(() => (window as any).vr.snapshot.t);
}

async function ready(page: Page) {
  await expect(page.locator("#app")).toHaveAttribute("data-library", "synthetic-core", { timeout: 30_000 });
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
}

test.beforeEach(async ({ page }) => {
  if (process.env.VR_E2E_THROTTLE) {
    // reproduce a slow CI runner: slow the page's CPU
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: Number(process.env.VR_E2E_THROTTLE) });
  }
  await page.goto("/");
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
  await page.selectOption(".vr-bar select >> nth=0", "synthetic-core");
  await ready(page);
  await page.selectOption('[data-op="layout"]', "instructor");
});

test("the instructor layout shows the operator panel and the instructor panel, with the session's outer step", async ({ page }) => {
  await expect(page.locator(".vr-opbox")).toBeVisible();
  await expect(page.locator(".vr-instbox")).toBeVisible();
  await expect(page.locator(".vr-view")).toBeHidden();
  await expect(inst(page, "outer-step")).toHaveText("10 ms (fine)");
  const rates = await inst(page, "rate").locator("option").allTextContents();
  expect(rates).toContain("100×");
  expect(rates).not.toContain("3600×");
  await expect(inst(page, "truth")).toContainText("power");
  await expect(inst(page, "reactivity").locator('[data-source="rods"]')).toBeVisible();
});

test("instrument faults: stuck and dead show in the instructor panel, the operator sees only the readings", async ({ page }) => {
  await inst(page, "fault-instrument").selectOption("linear");
  await inst(page, "fault-dead").click();
  await inst(page, "step").click(); // a command sent while paused applies on the next step
  await expect(inst(page, "message")).toContainText("linear: dead: accepted", { timeout: 10_000 });
  await expect(inst(page, "active-faults")).toContainText("instrument linear: dead");
  await expect(inst(page, "instruments").locator('[data-instrument="linear"]')).toContainText("dead");
  const op = await page.evaluate(() => (window as any).vr.operator.lastView);
  expect(op.indicated.linear).toBeNull();
  // the operator panel's view still holds no truth and no fault list
  expect(Object.keys(op).sort()).toEqual(["console", "indicated"]);
  expect(JSON.stringify(op)).not.toContain("dead");

  await inst(page, "fault-instrument").selectOption("log");
  await inst(page, "fault-stuck").click();
  await inst(page, "step").click();
  await expect(inst(page, "active-faults")).toContainText("instrument log: stuck", { timeout: 10_000 });
  await inst(page, "fault-instrument").selectOption("linear");
  await inst(page, "fault-clear").click();
  await inst(page, "step").click();
  await expect(inst(page, "active-faults")).not.toContainText("linear", { timeout: 10_000 });
  await expect(inst(page, "active-faults")).toContainText("instrument log: stuck");
  await expect(inst(page, "timeline").locator('[data-kind="fault"]')).toHaveCount(3);
});

test("a reactivity insertion shows as its own source, and there is no reactivity clear (amendment 2)", async ({ page }) => {
  await expect(inst(page, "rho-clear")).toHaveCount(0);
  await inst(page, "rho").fill("50");
  await inst(page, "rho-insert").click();
  await inst(page, "step").click();
  await expect(inst(page, "active-faults")).toContainText("reactivity inserted: 50.0 pcm", { timeout: 10_000 });
  await expect(inst(page, "reactivity").locator('[data-source="fault"]')).toContainText("50.0");
  // on this core, the step trips period-short at once (the trip reads the true period), and the timeline marks it
  await expect(inst(page, "timeline").locator('[data-kind="trip"]')).toHaveCount(1, { timeout: 10_000 });
});

test("a coarse session shows its step, offers 3600x, and rejects pulse mode and rod firing (amendment 1)", async ({ page }) => {
  await inst(page, "outer-choice").selectOption("1");
  await inst(page, "restart").click();
  await ready(page);
  await expect(inst(page, "outer-step")).toHaveText("1 s (coarse)");
  expect(await inst(page, "rate").locator("option").allTextContents()).toContain("3600×");

  await page.click('[data-op="play"]');
  await page.selectOption('[data-op="mode"]', "pulse");
  const note = page.locator(".vr-operator > .vr-note");
  await expect(note).toContainText("mode.set rejected: REJ_COARSE_STEP", { timeout: 10_000 });
  await expect(note).toContainText("outer step of 10 ms or less");
  const fire = await page.evaluate(() => (window as any).vr.client.command({ type: "rod.fire", rod: "transient" }));
  expect(fire).toMatchObject({ status: "rejected", reason: "REJ_COARSE_STEP" });

  await inst(page, "rate").selectOption("3600");
  await expect.poll(() => snapshotT(page), { timeout: 20_000 }).toBeGreaterThan(600);
  // the operator panel's rate menu follows the clock, also for a rate it does not offer itself
  await expect(page.locator('[data-op="rate"]')).toHaveValue("3600");
});

test("a click on the timeline asks first, then rewinds to that step and pauses", async ({ page }) => {
  await inst(page, "rate").selectOption("10");
  await inst(page, "play").click();
  await expect.poll(() => snapshotT(page), { timeout: 20_000 }).toBeGreaterThan(4);
  await inst(page, "play").click();
  await expect(inst(page, "play")).toHaveText("play", { timeout: 5_000 });
  const end = Number(await inst(page, "timeline").getAttribute("data-end"));
  const box = (await inst(page, "timeline").boundingBox())!;
  await inst(page, "timeline").click({ position: { x: box.width / 2, y: box.height / 2 } });
  await expect(page.locator(".vr-inst-confirm")).toContainText("Rewind to step");
  await inst(page, "rewind-yes").click();
  await expect(inst(page, "message")).toContainText("rewound to step", { timeout: 10_000 });
  await expect.poll(() => snapshotT(page), { timeout: 10_000 }).toBeLessThan(end * 0.6);
  const t = await snapshotT(page);
  expect(t).toBeGreaterThan(end * 0.4);
  await expect(inst(page, "play")).toHaveText("play");
});
