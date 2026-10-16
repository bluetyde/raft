import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Engine } from "../sim/engine";
import { repoRoot } from "../sim/testing";
import { Runtime } from "./runtime";
import type { ScenarioFile } from "./scenario";
import { FakeHost, readFolder, send } from "./test-helpers";

/**
 * The bank-withdrawal lesson (docs/validation/m8-near-critical-protocol.md): scripted operators, each run once; their outcomes were written before the runs.
 * Careful: bank C out in one motion to half its travel, then a few seconds at a time with a pause, to its critical position; then in and out by a second or two to hold.
 * Reckless: bank C all the way out without stopping (trips the startup-rate trip). Idle: nothing. Timid: bank C to 0.4 of its travel and no further.
 */
const LIB = join(repoRoot, "libraries", "pwr-beavrs-hzp-openmc");
const SC = JSON.parse(readFileSync(join(repoRoot, "web", "src", "app", "scenarios", "pwr-beavrs-hzp-bank-withdrawal.json"), "utf-8")) as ScenarioFile;

type Op = (c: Record<string, unknown>) => Promise<void>;

async function play(operator: (e: Engine, op: Op) => Promise<void>, limit = 5000) {
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
const posC = (e: Engine) => (e.snapshot().truth.rods as Record<string, { position: number }>)["c"]!.position;

describe("the bank-withdrawal lesson", () => {
  it("starts with banks C and D in, the others out, 900 ppm and about 850 pcm below critical", async () => {
    const host = new FakeHost();
    const rt = new Runtime(host);
    await send(rt, { kind: "load", protocol: 1, source: { kind: "files", files: readFolder(LIB) }, scenario: SC });
    const e = rt.engine!;
    const rods = e.snapshot().truth.rods as Record<string, { position: number }>;
    expect(Object.fromEntries(Object.entries(rods).map(([k, v]) => [k, v.position]))).toEqual({ a: 1, b: 1, c: 0, d: 0, sa: 1, sb: 1, sc: 1, sd: 1, se: 1 });
    expect(e.reactivity(0, e.y)["total"] * 1e5).toBeCloseTo(-851, -1);       // the sixteenth protocol's library value at N-C-0
    expect(e.indicated["log"] as number).toBeGreaterThan(0.005);
    expect(e.indicated["log"] as number).toBeLessThan(0.01);
    expect(e.validity().reasons).not.toContain("R_JOINT_UNCHECKED"); // the start state is one of the checked states
  });

  it("moving another bank away from its place leaves the checked states: the banner says so", async () => {
    let started = false;
    const { e } = await play(async (e, op) => {
      if (!started) {
        started = true;
        await op({ type: "rod.move", rod: "a", direction: "in" });
      } else if (e.t >= 20) {
        await op({ type: "rod.move", rod: "a", direction: "stop" });
      }
    }, 30);
    expect(Number((e.snapshot().truth.rods as Record<string, { position: number }>)["a"]!.position)).toBeLessThan(0.9);
    expect(e.validity().reasons).toContain("R_JOINT_UNCHECKED");
  });

  it("a careful operator meets every goal with no trip", async () => {
    let phase = 0;
    let t0 = 0;
    let pulse = 0; // seconds left of a nudge in progress
    const { view, rejected, peak } = await play(async (e, op) => {
      const c = posC(e);
      const log = e.indicated["log"] as number;
      const per = e.snapshot().truth.period as number;
      if (pulse > 0) {
        pulse -= 1;
        if (pulse === 0) await op({ type: "rod.move", rod: "c", direction: "stop" });
      } else if (phase === 0) {
        phase = 1;
        await op({ type: "rod.move", rod: "c", direction: "out" });
      } else if (phase === 1 && c >= 0.5) {
        phase = 2;
        t0 = e.t;
        await op({ type: "rod.move", rod: "c", direction: "stop" });
      } else if (phase === 2 && e.t - t0 >= 15) {
        t0 = e.t;
        if (c < 0.597) {
          pulse = 2; // creep out two seconds, then look again
          await op({ type: "rod.move", rod: "c", direction: "out" });
        } else {
          phase = 3;
        }
      } else if (phase === 3) {
        if (per > 0 && per < 600 && log > 0.1) {
          pulse = 1; // rising fast: a second in
          await op({ type: "rod.move", rod: "c", direction: "in" });
        } else if (per < 0 && per > -600 && log < 0.15) {
          pulse = 1; // falling: a second out
          await op({ type: "rod.move", rod: "c", direction: "out" });
        }
      }
    });
    expect(status(view)).toEqual({ approach: "met", critical: "met", hold: "met", "position-band": "met" });
    expect(view.score.trips).toBe(0);
    expect(rejected).toEqual([]);
    expect(peak).toBeLessThan(5);
  }, 240_000);

  /** The careful operator's approach (out to half, then a few seconds at a time to 0.597 and a little beyond), with the hold left to `hold`. */
  function approachThen(stopAt: number, hold: (e: Engine, nudge: (direction: "in" | "out") => Promise<void>) => Promise<void>) {
    let phase = 0;
    let t0 = 0;
    let pulse = 0;
    return async (e: Engine, op: Op) => {
      const c = posC(e);
      if (pulse > 0) {
        pulse -= 1;
        if (pulse === 0) await op({ type: "rod.move", rod: "c", direction: "stop" });
      } else if (phase === 0) {
        phase = 1;
        await op({ type: "rod.move", rod: "c", direction: "out" });
      } else if (phase === 1 && c >= 0.5) {
        phase = 2;
        t0 = e.t;
        await op({ type: "rod.move", rod: "c", direction: "stop" });
      } else if (phase === 2 && e.t - t0 >= 15) {
        t0 = e.t;
        if (c < stopAt) {
          pulse = 2;
          await op({ type: "rod.move", rod: "c", direction: "out" });
        } else {
          phase = 3;
        }
      } else if (phase === 3) {
        await hold(e, async (direction) => {
          pulse = 1; // a second in or out, then stop
          await op({ type: "rod.move", rod: "c", direction });
        });
      }
    };
  }

  it("an operator who stops bank C short of its critical position sees a power above 0.1 W (source multiplication) but is not critical", async () => {
    const { view } = await play(approachThen(0.575, async () => {}), 2500);
    expect(view.goals.find((g) => g.id === "approach")!.status).toBe("met");
    expect(view.goals.find((g) => g.id === "critical")!.status).toBe("failed");
    expect(view.score.trips).toBe(0);
  }, 240_000);

  it("an operator who parks bank C just past critical and leaves it loses the hold: the power runs out of the window", async () => {
    const { view } = await play(approachThen(0.597, async () => {}), 3000);
    expect(view.goals.find((g) => g.id === "critical")!.status).toBe("met");
    expect(view.goals.find((g) => g.id === "hold")!.status).toBe("failed");
  }, 240_000);

  it("an operator who holds with a short but steady period (under 10 minutes) fails the hold even with the power inside the window", async () => {
    const { view, peak } = await play(approachThen(0.597, async (e, nudge) => {
      const per = e.snapshot().truth.period as number;
      if (per > 0 && per < 100) await nudge("in");
    }), 3000);
    expect(view.goals.find((g) => g.id === "critical")!.status).toBe("met");
    expect(view.goals.find((g) => g.id === "hold")!.status).toBe("failed");
    expect(peak).toBeLessThan(5);
  }, 240_000);

  it("an operator who holds for only two minutes and then lets the power run does not meet the five-minute hold", async () => {
    let t1 = -1;
    const { view } = await play(approachThen(0.597, async (e, nudge) => {
      const per = e.snapshot().truth.period as number;
      const log = e.indicated["log"] as number;
      if (t1 < 0) t1 = e.t;
      if (e.t - t1 < 120) {
        if (per > 0 && per < 600 && log > 0.1) await nudge("in");
        else if (per < 0 && per > -600 && log < 0.15) await nudge("out");
      } else {
        await nudge("out"); // two minutes in, push the bank out a second at a time: the period shortens
      }
    }), 3000);
    expect(view.goals.find((g) => g.id === "critical")!.status).toBe("met");
    expect(view.goals.find((g) => g.id === "hold")!.status).toBe("failed");
  }, 240_000);

  it("an operator who crosses critical and then retreats deep into subcritical loses the hold: the power falls out of the window", async () => {
    let last = -10;
    const { view, e } = await play(approachThen(0.605, async (e, nudge) => {
      if (e.t - last >= 3 && posC(e) > 0.45) {
        last = e.t;
        await nudge("in"); // one second at a time, down to 0.45 of travel
      }
    }), 3000);
    expect(view.goals.find((g) => g.id === "critical")!.status).toBe("met");
    expect(view.goals.find((g) => g.id === "hold")!.status).toBe("failed");
    expect(posC(e)).toBeLessThan(0.5);
    expect(view.score.trips).toBe(0);
  }, 240_000);

  it("a reckless operator, who withdraws bank C all the way, trips the startup-rate trip and fails the hold", async () => {
    let started = false;
    const { view, e } = await play(async (_e, op) => {
      if (!started) {
        started = true;
        await op({ type: "rod.move", rod: "c", direction: "out" });
      }
    });
    expect(view.goals.find((g) => g.id === "approach")!.status).toBe("met");
    expect(view.goals.find((g) => g.id === "hold")!.status).toBe("failed");
    expect(view.score.trips).toBe(1);
    expect(e.latched).toEqual(["period-short"]);
  }, 240_000);

  it("an operator who does nothing fails the first goal on time", async () => {
    const { view } = await play(async () => {});
    expect(view.goals.find((g) => g.id === "approach")!.status).toBe("failed");
    expect(view.score.met).toBe(0);
  }, 240_000);

  it("a timid operator, who stops bank C at 0.4 of its travel, never reaches the first goal", async () => {
    let started = false;
    const { view } = await play(async (e, op) => {
      if (!started) {
        started = true;
        await op({ type: "rod.move", rod: "c", direction: "out" });
      } else if (posC(e) >= 0.4) {
        await op({ type: "rod.move", rod: "c", direction: "stop" });
      }
    });
    expect(view.goals.find((g) => g.id === "approach")!.status).toBe("failed");
    expect(view.score.trips).toBe(0);
  }, 240_000);
});
