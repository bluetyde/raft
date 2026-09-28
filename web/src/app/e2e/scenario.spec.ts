/**
 * M5 scenarios, slice SC1 (docs/m5-scenarios-design.md section 7): the instructor starts a scenario, the goals show,
 * a control the scenario does not allow is rejected with REJ_SCENARIO, a goal is met, and the session file names the scenario.
 */

import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const inst = (page: Page, name: string) => page.locator(`[data-inst="${name}"]`);
const t = (page: Page) => page.evaluate(() => (window as any).vr.snapshot?.t ?? -1);

async function ready(page: Page, library = "synthetic-core") {
  await expect(page.locator("#app")).toHaveAttribute("data-library", library, { timeout: 30_000 });
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
}

test.beforeEach(async ({ page }) => {
  if (process.env.VR_E2E_THROTTLE) {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: Number(process.env.VR_E2E_THROTTLE) });
  }
  await page.goto("/");
  await ready(page, "triga-jsi-242");
  await page.selectOption(".vr-bar select >> nth=0", "synthetic-core");
  await ready(page);
  await page.selectOption('[data-op="layout"]', "instructor");
});

async function start(page: Page, id: string) {
  await inst(page, "scenario-choice").selectOption(id);
  await inst(page, "scenario-start").click();
  await expect.poll(() => page.evaluate(() => (window as any).vr.instructor?.scenario?.id), { timeout: 30_000 }).toBe(id);
  await ready(page);
}

test("the instructor starts a scenario; its goals show; a control it does not allow is rejected; a goal is met", async ({ page }) => {
  expect(await inst(page, "scenario-choice").locator("option").allTextContents()).toEqual(["Power ascension", "Scram and restart"]);
  await start(page, "synthetic-power-ascension");
  const box = inst(page, "scenario");
  await expect(box).toContainText("Power ascension");
  await expect(box.locator('[data-goal="one-percent"]')).toHaveAttribute("data-status", "open");
  await expect(box.locator('[data-goal="ten-percent"]')).toHaveAttribute("data-status", "waiting");
  await expect(inst(page, "scenario-score")).toHaveText("goals met 0 of 3, unexpected trips 0");

  // the scenario allows rod.move and scram only: the mode switch is refused, with the reason text
  await page.click('[data-op="play"]');
  await page.selectOption('[data-op="mode"]', "pulse");
  const note = page.locator(".vr-operator > .vr-note");
  await expect(note).toContainText("mode.set rejected: REJ_SCENARIO", { timeout: 10_000 });
  await expect(note).toContainText("the scenario does not allow this control");

  await page.click('[data-op="safety:out"]');
  await page.click('[data-op="regulating:out"]');
  await inst(page, "rate").selectOption("100");
  await expect(box.locator('[data-goal="one-percent"]')).toHaveAttribute("data-status", "met", { timeout: 30_000 });
  await expect(box.locator('[data-goal="ten-percent"]')).toHaveAttribute("data-status", "open");
  await expect(inst(page, "scenario-score")).toContainText("goals met 1 of 3");
});

test("a scripted event shows on the timeline, and the session file names the scenario and its thresholds", async ({ page }) => {
  await start(page, "synthetic-scram-and-restart");
  await inst(page, "rate").selectOption("100");
  await inst(page, "play").click();
  await expect.poll(() => t(page), { timeout: 30_000 }).toBeGreaterThan(61); // the pool thermometer sticks at 60 s
  await inst(page, "play").click();
  await expect(inst(page, "timeline").locator('[data-kind="scripted"]')).toHaveCount(1);
  await expect(inst(page, "active-faults")).toContainText("instrument pool-temp: stuck");

  const [dl] = await Promise.all([page.waitForEvent("download"), inst(page, "export-session").click()]);
  const path = await dl.path();
  const file = JSON.parse(readFileSync(path, "utf8"));
  expect(file.version).toBe(3);
  expect(file.scenario).toMatchObject({ id: "synthetic-scram-and-restart", thresholds: { steady: [2750, 137500], restart: 2750 } });

  // the file imports again with its scenario (the app finds it by id)
  await inst(page, "import").setInputFiles(path);
  await expect(inst(page, "export-message")).toContainText("imported", { timeout: 30_000 });
  expect(await page.evaluate(() => (window as any).vr.instructor.scenario.id)).toBe("synthetic-scram-and-restart");
});
