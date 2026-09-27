/**
 * Browser end-to-end check of the runtime on the synthetic fixture (TODO Next #8):
 * a malformed library, a trip, pause and resume, and replay. It runs the real Web Worker in Chromium
 * against the production build. The trip is checked against the engine's golden vector.
 */

import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

declare global {
  interface Window {
    e2e: any;
  }
}

const vector = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../../schema/engine-vectors/period-trip.json", import.meta.url)), "utf8"),
);
const trip = vector.events.find((e: any) => e.type === "trip");

async function state(page: Page, id: number) {
  return page.evaluate((id) => window.e2e.state(id), id);
}

/** The parts of a snapshot that must match exactly between two runs (diagnostics count solver work, which differs after a restore). */
function physics(s: any) {
  return { t: s.t, truth: s.truth, indicated: s.indicated, trips: s.trips, tripped: s.tripped, validity: s.validity };
}

test.beforeEach(async ({ page }) => {
  await page.goto("/src/app/e2e/index.html");
  await expect(page.locator("#status")).toHaveText("ready");
});

for (const [how, code] of [
  ["json", "E_JSON"],
  ["digest", "E_DIGEST_MISMATCH"],
] as const) {
  test(`a malformed library (${how}) is refused with ${code}`, async ({ page }) => {
    const r = await page.evaluate((how) => window.e2e.start({ corrupt: how }), how);
    expect(r.loaded).toBeNull();
    expect(r.issues).toContain(code);
    // the worker is still usable: commands are refused because nothing is loaded
    const ack = await page.evaluate((id) => window.e2e.command(id, { type: "scram" }), r.id);
    expect(ack).toMatchObject({ status: "rejected", reason: "REJ_NO_LIBRARY" });
  });
}

test("a trip: the period trip fires at the golden vector's time, and the peak matches", async ({ page }) => {
  const r = await page.evaluate(
    (v) => window.e2e.start({ init: v.init, seed: v.seed, config: v.config }),
    { init: vector.init, seed: vector.seed, config: vector.config },
  );
  expect(r.loaded).not.toBeNull();
  expect(r.loaded.digest).toBe(vector.pins.libraryDigest);
  // the vector's command at step 0, sent while paused (it applies on the first step), then run at 20x
  // (the trip comes at about 17 s of sim time, so the pause lands well before the vector's last step)
  await page.evaluate(({ id, cmd }) => window.e2e.send(id, cmd), { id: r.id, cmd: vector.script[0].cmd });
  await page.evaluate((id) => window.e2e.time(id, { rate: 20, paused: false }), r.id);
  await expect
    .poll(async () => (await state(page, r.id)).events.some((e: any) => e.type === "trip"), { timeout: 30_000 })
    .toBe(true);
  await page.evaluate((id) => window.e2e.time(id, { paused: true }), r.id);

  const s = await state(page, r.id);
  const got = s.events.find((e: any) => e.type === "trip");
  expect(got.id).toBe(trip.id);
  expect(Math.abs(got.t - trip.t)).toBeLessThanOrEqual(vector.tolerances.eventTime.abs);
  expect(s.acks[0]).toMatchObject({ status: "accepted", seq: 1 });

  // run on to the vector's last step, then compare the recorded peak
  await expect.poll(async () => (await state(page, r.id)).clock?.paused, { timeout: 10_000 }).toBe(true);
  const step = Math.round((await state(page, r.id)).snapshot.t / vector.config.outerDt);
  expect(step).toBeLessThan(vector.steps);
  await page.evaluate(({ id, n }) => window.e2e.step(id, n), { id: r.id, n: vector.steps - step });
  await expect
    .poll(async () => Math.round((await state(page, r.id)).snapshot.t / vector.config.outerDt), { timeout: 30_000 })
    .toBe(vector.steps);
  const end = (await state(page, r.id)).snapshot;
  expect(end.tripped).toBe(true);
  const tol = vector.tolerances.power;
  expect(Math.abs(end.truth.peakPower - vector.final.peakPower)).toBeLessThanOrEqual(tol.abs + tol.rel * vector.final.peakPower);
  expect(Math.abs(end.truth.peakTime - vector.final.peakTime)).toBeLessThanOrEqual(vector.tolerances.eventTime.abs);
});

test("pause and resume: no sim time passes while paused", async ({ page }) => {
  const r = await page.evaluate(() => window.e2e.start());
  await page.evaluate((id) => window.e2e.time(id, { rate: 10, paused: false }), r.id);
  await expect.poll(async () => (await state(page, r.id)).snapshot?.t ?? 0, { timeout: 10_000 }).toBeGreaterThan(1);
  await page.evaluate((id) => window.e2e.time(id, { paused: true }), r.id);
  await expect.poll(async () => (await state(page, r.id)).clock?.paused, { timeout: 5_000 }).toBe(true);
  const t0 = (await state(page, r.id)).snapshot.t;
  await page.waitForTimeout(500);
  expect((await state(page, r.id)).snapshot.t).toBe(t0);
  await page.evaluate((id) => window.e2e.time(id, { paused: false }), r.id);
  await expect.poll(async () => (await state(page, r.id)).snapshot.t, { timeout: 10_000 }).toBeGreaterThan(t0 + 1);
  const clock = (await state(page, r.id)).clock;
  expect(clock.paused).toBe(false);
  expect(clock.rate).toBe(10);
  expect((await state(page, r.id)).errors).toEqual([]);
});

test("replay: a session exported from one worker and imported into another gives the same state; rewind too", async ({ page }) => {
  const a = await page.evaluate(
    (v) => window.e2e.start({ init: v.init, seed: 3 }),
    { init: vector.init },
  );
  await page.evaluate((id) => window.e2e.send(id, { type: "rod.move", rod: "transient", direction: "out" }), a.id);
  await page.evaluate((id) => window.e2e.step(id, 600), a.id);
  await page.evaluate((id) => window.e2e.send(id, { type: "fault.instrument", instrument: "log", kind: "stuck" }), a.id);
  await page.evaluate((id) => window.e2e.step(id, 900), a.id);
  await expect.poll(async () => (await state(page, a.id)).snapshot.t, { timeout: 30_000 }).toBeCloseTo(15, 9);
  const atEnd = physics((await state(page, a.id)).snapshot);
  const file = await page.evaluate((id) => window.e2e.exportSession(id), a.id);
  expect(file.endStep).toBe(1500);
  expect(file.session.commands).toHaveLength(2);

  const b = await page.evaluate(() => window.e2e.start());
  const imported = await page.evaluate(({ id, file }) => window.e2e.importSession(id, file), { id: b.id, file });
  expect(imported.step).toBe(1500);
  await expect.poll(async () => (await state(page, b.id)).snapshot.t, { timeout: 10_000 }).toBeCloseTo(15, 9);
  expect(physics((await state(page, b.id)).snapshot)).toEqual(atEnd);

  // rewind A to step 1200 (just after the checkpoint at step 1000, which already holds both commands),
  // run the same 300 steps again: same state as before the rewind
  const rw = await page.evaluate((id) => window.e2e.rewind(id, 1200), a.id);
  expect(rw).toMatchObject({ step: 1200, previousEnd: 1500 });
  await page.evaluate((id) => window.e2e.step(id, 300), a.id);
  await expect.poll(async () => (await state(page, a.id)).snapshot.t, { timeout: 30_000 }).toBeCloseTo(15, 9);
  expect(physics((await state(page, a.id)).snapshot)).toEqual(atEnd);
});
