import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { compareDocs } from "./compare";
import { Engine, InitError } from "./engine";
import { runScenario, sampleFromEngine } from "./vectors";
import { loadLibrary } from "./library";
import { nodeReader } from "../library/node-reader";
import { fixturesDir } from "./testing";

/** The guards of the reference engine found by the whole-repo review. The same cases as physics_ref/tests/test_engine_guards.py. */

const INIT = { rods: { safety: 0, regulating: 0, transient: 0 }, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } };

async function engine(init: Record<string, unknown> = INIT, config: Record<string, unknown> = {}) {
  const lib = await loadLibrary(nodeReader(join(fixturesDir, "synthetic-core")));
  return new Engine(lib, { ...init }, 1, config as any);
}

describe("the engine guards", () => {
  it("a zero, negative or non-finite interval is refused", async () => {
    for (const key of ["outerDt", "rtol", "hInit", "hMin", "eventTol"]) {
      for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, "0.01", null, true]) {
        await expect(engine(INIT, { [key]: bad })).rejects.toBeInstanceOf(InitError);
      }
    }
    await engine(INIT, { outerDt: 0.02 }); // a valid change is accepted
  });

  it("a non-finite initial power is refused", async () => {
    for (const value of [Number.NaN, Number.POSITIVE_INFINITY, -1, undefined]) {
      await expect(engine({ ...INIT, power: { mode: "given", value } })).rejects.toBeInstanceOf(InitError);
    }
  });

  it("a reactivity fault that is not a finite number is rejected and changes nothing", async () => {
    const e = await engine();
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, "bad"]) {
      e.submit({ type: "fault.reactivity", deltaRho: bad });
      e.step();
      expect(e.extraRho).toBe(0.0);
      const last = e.events[e.events.length - 1]!;
      expect([last.status, last.reason]).toEqual(["rejected", "REJ_BAD_ARGUMENT"]);
    }
    e.submit({ type: "fault.reactivity", deltaRho: 1.0e-4 });
    e.step();
    expect(e.extraRho).toBe(1.0e-4);
  });

  it("the rod and drift faults that only this engine had are refused", async () => {
    const e = await engine();
    e.submit({ type: "fault.rod", rod: "safety", kind: "stuck" });
    e.submit({ type: "fault.instrument", instrument: "log", kind: "drift", rate: 0.1 });
    e.step();
    const reasons = e.events.filter((x) => x.type === "command").map((x) => x.reason);
    expect(reasons).toEqual(["REJ_UNKNOWN_COMMAND", "REJ_BAD_ARGUMENT"]);
  });

  it("advance returns the steps taken and stops when halted", async () => {
    const e = await engine();
    expect(e.advance(0.1)).toBe(10);
    expect(e.stepIndex).toBe(10);
    e.halted = "R_TABLE_REJECT_test";
    expect(e.advance(5.0)).toBe(0);
    expect(e.stepIndex).toBe(10);
  });

  it("a state that is not a number halts the engine with the reason", async () => {
    const e = await engine();
    (e as any)._integrate = () => {
      e.y = e.y.map(() => Number.NaN);
    };
    e.step();
    expect(e.halted).toBe("R_NONFINITE_STATE");
    expect(e.events[e.events.length - 1]!.type).toBe("halt");
    expect(e.validity()["status"]).toBe("outOfDomain");
    const before = e.stepIndex;
    expect(e.advance(1.0)).toBe(0);
    expect(e.stepIndex).toBe(before);
  });
});

describe("the golden-vector tools", () => {
  it("a scenario that halts is an error, not a shorter vector", async () => {
    const lib = await loadLibrary(nodeReader(join(fixturesDir, "synthetic-core")));
    const sc: any = { name: "halts", description: "x", init: INIT, seed: 1, config: {}, steps: 50, sampleEvery: 10, script: [] };
    const orig = Engine.prototype.step;
    Engine.prototype.step = function (this: Engine) {
      orig.call(this);
      if (this.stepIndex === 7) {
        this.halted = "R_TABLE_REJECT_test";
      }
    };
    try {
      expect(() => runScenario(lib, sc)).toThrow(/halted at step 7/);
    } finally {
      Engine.prototype.step = orig;
    }
  });

  it("a sample carries the validity reasons", async () => {
    const e = await engine();
    const s = sampleFromEngine(e);
    expect(s["validityStatus"]).toBe(e.validity()["status"]);
    expect(s["validityReasons"]).toEqual(e.validity()["reasons"]);
  });

  it("a value that is not finite never compares equal", () => {
    const tol = {};
    expect(compareDocs({ power: 1.0 }, { power: Number.NaN }, tol).length).toBeGreaterThan(0);
    expect(compareDocs({ power: Number.NaN }, { power: Number.NaN }, tol).length).toBeGreaterThan(0);
    expect(compareDocs({ power: Number.POSITIVE_INFINITY }, { power: 1.0 }, tol).length).toBeGreaterThan(0);
    expect(compareDocs({ power: 1.0 }, { power: 1.0 }, tol)).toEqual([]);
  });
});
