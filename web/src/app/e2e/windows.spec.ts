/**
 * M6 slice S3 end-to-end check (docs/m6-instructor-design.md section 7): two windows of one session share one
 * SharedWorker. The operator window has instruments only, and the worker refuses its time, rewind and fault requests
 * (amendment 3). Closing a window does not stop the session.
 */

import { expect, test, type Page } from "@playwright/test";

test.beforeEach(async ({ context }) => {
  if (!process.env.VR_E2E_THROTTLE) return;
  // reproduce a slow CI runner: slow each new page's CPU
  context.on("page", async (p) => {
    const cdp = await context.newCDPSession(p);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: Number(process.env.VR_E2E_THROTTLE) });
  });
});

async function ready(page: Page, library = "synthetic-core") {
  await expect(page.locator("#app")).toHaveAttribute("data-library", library, { timeout: 30_000 });
  await expect(page.locator("#app")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
}

const t = (page: Page) => page.evaluate(() => (window as any).vr.snapshot?.t ?? -1);

/** An instructor window (role full) on session `id` with the synthetic core loaded. */
async function fullWindow(page: Page, id: string) {
  await page.goto(`/?session=${id}`);
  await ready(page, "triga-jsi-242"); // the default library
  await page.selectOption(".vr-bar select >> nth=0", "synthetic-core");
  await ready(page);
}

test("two windows share one session: a command in one shows in the other", async ({ context }) => {
  const a = await context.newPage();
  await fullWindow(a, "share1");
  const b = await context.newPage();
  await b.goto("/?session=share1&role=operator");
  await ready(b); // B did not load anything: it attached and built its panels for A's session
  expect(await b.evaluate(() => (window as any).vr.role)).toBe("operator");
  // the session is paused, but B has its state at once: a snapshot at t = 0 and the readings on its meters
  await expect.poll(() => t(b), { timeout: 5_000 }).toBe(0);
  await expect(b.locator('[data-meter="linear"] .vr-value')).not.toHaveText("");
  await expect(b.locator('[data-op="window"]')).toHaveText("operator window, session share1");

  // the operator window: instruments only, no time controls, and it cannot load a library
  expect(await b.locator('[data-op="layout"] option').allTextContents()).toEqual(["split", "realism"]);
  await expect(b.locator('[data-op="play"]')).toHaveCount(0);
  await expect(b.locator(".vr-bar select >> nth=0")).toBeDisabled();
  await expect(b.locator('[data-op="open-operator"]')).toBeHidden();

  await b.click('[data-op="regulating:out"]'); // from the operator window
  await a.click('[data-op="play"]'); // time from the instructor's window
  await expect
    .poll(() => a.evaluate(() => (window as any).vr.snapshot.truth.rods.regulating.moving), { timeout: 10_000 })
    .toBe("out");
  await expect.poll(() => t(b), { timeout: 10_000 }).toBeGreaterThan(0.5);
  await expect(b.locator('.vr-operator > .vr-note[data-op="message"]')).toContainText("rod.move accepted");
  // the operator's own panel shows the time, set by the instructor
  await expect(b.locator(".vr-opclock")).toContainText("achieved");
});

test("amendment 3: the worker refuses an operator window's time, rewind and fault requests", async ({ context }) => {
  const a = await context.newPage();
  await fullWindow(a, "roles1");
  await a.click('[data-op="play"]');
  const b = await context.newPage();
  await b.goto("/?session=roles1&role=operator");
  await ready(b);
  const got = await b.evaluate(async () => {
    const c = (window as any).vr.client;
    const errors: [string, string][] = [];
    c.on("error", (m: any) => errors.push([m.request, m.code]));
    c.setTime({ paused: true });
    c.step(1);
    const ack = await c.command({ type: "fault.instrument", instrument: "log", kind: "stuck" });
    let rewind = "";
    try {
      await c.rewind(0);
    } catch (err) {
      rewind = String(err);
    }
    await new Promise((r) => setTimeout(r, 300));
    return { errors, ack, rewind };
  });
  expect(got.errors).toEqual(
    expect.arrayContaining([
      ["time", "E_ROLE"],
      ["step", "E_ROLE"],
      ["rewind", "E_ROLE"],
    ]),
  );
  expect(got.ack).toMatchObject({ status: "rejected", reason: "REJ_ROLE" });
  expect(got.rewind).toContain("E_ROLE");
  // the refused pause did not stop the session
  const t0 = await t(a);
  await expect.poll(() => t(a), { timeout: 10_000 }).toBeGreaterThan(t0 + 0.5);
  expect(await a.evaluate(() => (window as any).vr.instructor.lastFaults.instruments)).toEqual({});
});

test("closing the instructor's window does not stop the session, and a new window picks it up", async ({ context }) => {
  const a = await context.newPage();
  await fullWindow(a, "close1");
  await a.selectOption('[data-op="rate"]', "10");
  await a.click('[data-op="play"]');
  const b = await context.newPage();
  await b.goto("/?session=close1&role=operator");
  await ready(b);
  await expect.poll(() => t(b), { timeout: 10_000 }).toBeGreaterThan(1);
  await a.close();
  const t1 = await t(b);
  await expect.poll(() => t(b), { timeout: 10_000 }).toBeGreaterThan(t1 + 2);

  // a new instructor window on the same session adopts the running session (it does not load the default library)
  const c = await context.newPage();
  await c.goto("/?session=close1");
  await ready(c);
  expect(await t(c)).toBeGreaterThan(t1);
  await expect(c.locator('[data-op="play"]')).toHaveText(/pause/);
});

test("the open-operator button opens a second window of the same session", async ({ context }) => {
  const a = await context.newPage();
  await fullWindow(a, "open1");
  const [b] = await Promise.all([context.waitForEvent("page"), a.click('[data-op="open-operator"]')]);
  await ready(b);
  const url = new URL(b.url());
  expect(url.searchParams.get("session")).toBe("open1");
  expect(url.searchParams.get("role")).toBe("operator");
});

test("a new window without a session id gets its own session, kept in the URL", async ({ context }) => {
  const a = await context.newPage();
  await a.goto("/");
  await ready(a, "triga-jsi-242");
  const id = new URL(a.url()).searchParams.get("session");
  expect(id).toMatch(/^[A-Za-z0-9_-]{1,40}$/);
  const b = await context.newPage();
  await b.goto("/");
  await ready(b, "triga-jsi-242");
  expect(new URL(b.url()).searchParams.get("session")).not.toBe(id);
});

test("without SharedWorker, the app runs in one window with a dedicated worker", async ({ page }) => {
  await page.addInitScript(() => {
    delete (window as any).SharedWorker;
  });
  await page.goto("/?session=nosw&role=operator");
  await ready(page, "triga-jsi-242");
  expect(await page.evaluate(() => [(window as any).vr.shared, (window as any).vr.role])).toEqual([false, "full"]);
  await expect(page.locator('[data-op="open-operator"]')).toBeHidden();
  await expect(page.locator('[data-op="window"]')).toContainText("no SharedWorker");
  await page.click('[data-op="play"]');
  await expect.poll(() => t(page), { timeout: 10_000 }).toBeGreaterThan(0.2);
});
