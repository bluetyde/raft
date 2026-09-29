import { describe, expect, it } from "vitest";
import { DeterministicPID } from "./controller";

/** Deterministic pseudo-noise, so the test does not flake. */
function noise(seed: number) {
  let x = seed;
  return () => ((x = (x * 1664525 + 1013904223) >>> 0) / 2 ** 32 - 0.5) * 2; // [-1, 1)
}

/** Run the controller on a reading at `power(t)` with relative noise `rel`; return each command change. */
function run(power: (t: number) => number, seconds: number, rel: number, dt = 0.01) {
  const pid = new DeterministicPID();
  pid.enable(1);
  const n = noise(7);
  const cmds: string[] = [];
  let last = "stop";
  for (let t = 0; t < seconds; t += dt) {
    const c = pid.calculate(power(t) * (1 + rel * n()), dt, false);
    if (c !== last) cmds.push(c);
    last = c;
  }
  return cmds;
}

describe("DeterministicPID", () => {
  it("does not move the rod for 3% sensor noise at the target", () => {
    expect(run(() => 1, 120, 0.03)).toEqual([]);
  });

  it("makes at most a few motion changes when power sits 30% high, and only inward", () => {
    const cmds = run(() => 1.3, 60, 0.03);
    expect(cmds[0]).toBe("in");
    expect(cmds.length).toBeLessThanOrEqual(2);
    expect(cmds).not.toContain("out");
  });

  it("starts or reverses motion no faster than the dwell allows", () => {
    const pid = new DeterministicPID();
    pid.enable(1);
    const seen: string[] = [];
    // alternate far above and far below the target every 0.1 s; a relay without dwell would flip constantly
    for (let i = 0; i < 200; i++) seen.push(pid.calculate(i % 2 ? 0.2 : 5, 0.1, false));
    let starts = 0;
    for (let i = 1; i < seen.length; i++) if (seen[i] !== seen[i - 1] && seen[i] !== "stop") starts++;
    expect(starts).toBeLessThanOrEqual(20 / 0.5); // 20 s of run, at most one start per 0.5 s dwell
  });
});
