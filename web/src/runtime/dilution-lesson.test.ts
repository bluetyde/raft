import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Engine } from "../sim/engine";
import { repoRoot } from "../sim/testing";
import { Runtime } from "./runtime";
import type { ScenarioFile } from "./scenario";
import { FakeHost, readFolder, send } from "./test-helpers";

/**
 * The dilution lesson (docs/m8-dilution-lesson-plan.md): three scripted operators, each run once, the thresholds fixed in the plan beforehand.
 * Careful: dilute, then back off when the log channel passes 0.5 W. Reckless: dilute to the end. Idle: do nothing.
 */
const LIB = join(repoRoot, "libraries", "pwr-beavrs-hzp-openmc");
const SC = JSON.parse(readFileSync(join(repoRoot, "web", "src", "app", "scenarios", "pwr-beavrs-hzp-dilution.json"), "utf-8")) as ScenarioFile;

type Op = (c: Record<string, unknown>) => Promise<void>;

async function play(operator: (e: Engine, op: Op) => Promise<void>, limit = 4000) {
  const host = new FakeHost();
  const rt = new Runtime(host);
  await send(rt, { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(LIB) }, scenario: SC });
  if (!rt.engine) throw new Error(JSON.stringify(host.last("loadFailed")));
  let n = 1;
  const op: Op = (c) => send(rt, { kind: "command", clientSeq: n++, clientId: "operator", cmd: c });
  const view = () => host.last("scenario")!.scenario!;
  let peak = 0;
  while (!view().done && rt.engine.t < limit) {
    await operator(rt.engine, op);
    await send(rt, { kind: "step", n: 1 });
    peak = Math.max(peak, rt.engine.snapshot().truth.power);
  }
  return { view: view(), rejected: host.of("ack").filter((a) => a.status === "rejected"), peak, e: rt.engine };
}

const status = (v: { goals: { id: string; status: string }[] }) => Object.fromEntries(v.goals.map((g) => [g.id, g.status]));

describe("the dilution lesson", () => {
  it("a careful operator meets every goal with no trip", async () => {
    let phase = 0;
    const { view, rejected, peak } = await play(async (e, op) => {
      if (phase === 0) {
        phase = 1;
        await op({ type: "boron.set", ppm: 900 });
      } else if (phase === 1 && (e.indicated["log"] as number) > 0.5) {
        phase = 2;
        await op({ type: "boron.set", ppm: 984 });
      }
    });
    expect(status(view)).toEqual({ approach: "met", critical: "met", hold: "met", "boron-band": "met" });
    expect(view.score.trips).toBe(0);
    expect(rejected).toEqual([]);
    expect(peak).toBeLessThan(30);
  }, 120_000);

  it("a reckless operator, who dilutes to the end, trips the startup-rate trip and fails the hold", async () => {
    let sent = false;
    const { view, e } = await play(async (_e, op) => {
      if (!sent) {
        sent = true;
        await op({ type: "boron.set", ppm: 900 });
      }
    });
    expect(view.goals.find((g) => g.id === "approach")!.status).toBe("met");
    expect(view.goals.find((g) => g.id === "hold")!.status).toBe("failed");
    expect(view.score.trips).toBeGreaterThanOrEqual(1);
    expect(e.snapshot().truth.reactivity.total).toBeLessThan(-0.02); // scrammed
  }, 120_000);

  it("an operator who does nothing fails the first goal on time", async () => {
    const { view } = await play(async () => {});
    expect(view.goals.find((g) => g.id === "approach")!.status).toBe("failed");
    expect(view.score.met).toBe(0);
  }, 120_000);
});
