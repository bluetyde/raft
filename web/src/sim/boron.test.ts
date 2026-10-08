import { describe, expect, it } from "vitest";
import { Engine, InitError } from "./engine";
import { loadBoronCore, loadSyntheticCore } from "./testing";
import { nearCriticalRods } from "./vectors";

/** Soluble boron (capability point-kinetics/boron-v1): the same cases as physics_ref/tests/test_boron.py. */
async function make(lib?: Awaited<ReturnType<typeof loadBoronCore>>) {
  const L = lib ?? (await loadBoronCore());
  return { L, e: new Engine(L, { rods: nearCriticalRods(L, -0.0005) }, 1) };
}

describe("soluble boron", () => {
  it("the reference concentration adds nothing", async () => {
    const { e: withBoron } = await make();
    const plain = await loadSyntheticCore();
    const without = new Engine(plain, { rods: nearCriticalRods(plain, -0.0005) }, 1);
    expect(withBoron.reactivity(0, withBoron.y).total).toBe(without.reactivity(0, without.y).total);
    withBoron.advance(5);
    without.advance(5);
    expect(withBoron.y[0]).toBe(without.y[0]);
  });

  it("the ramp is exactly the rate and stops at the target", async () => {
    const { L, e } = await make();
    expect(L.boronMaxRate).toBe(0.5);
    e.submit({ type: "boron.set", ppm: 990 });
    e.advance(10);
    expect(e.boronValue(e.t)).toBeCloseTo(995, 9);
    expect(e.snapshot().truth.boronTarget).toBe(990);
    e.advance(10);
    expect(e.boronValue(e.t)).toBe(990);
    expect(e.snapshot().truth.boronTarget).toBeNull();
    e.advance(10);
    expect(e.boronValue(e.t)).toBe(990);
    const r = e.snapshot().truth.reactivity;
    expect(r.boron).toBeCloseTo(10 * 1.2e-4, 12);
  });

  it("a new target in mid-ramp starts from the current value", async () => {
    const { e } = await make();
    e.submit({ type: "boron.set", ppm: 900 });
    e.advance(20);
    e.submit({ type: "boron.set", ppm: 1000 });
    e.advance(10);
    expect(e.boronValue(e.t)).toBeCloseTo(995, 9);
    e.submit({ type: "boron.set", ppm: e.boronValue(e.t) });
    e.advance(10);
    expect(e.boronValue(e.t)).toBeCloseTo(995, 9);
  });

  it("rejects what it should, and a library without boron does not know the command", async () => {
    const { L, e } = await make();
    for (const ppm of [2500, -1, "lots", null, true, Infinity]) e.submit({ type: "boron.set", ppm });
    e.advance(0.1);
    const reasons = e.events.filter((x) => x.type === "command").map((x) => x.reason);
    expect(reasons).toEqual(["REJ_OUT_OF_RANGE", "REJ_OUT_OF_RANGE", "REJ_BAD_ARGUMENT", "REJ_BAD_ARGUMENT", "REJ_BAD_ARGUMENT", "REJ_BAD_ARGUMENT"]);
    expect(e.boronValue(e.t)).toBe(1000);
    expect(() => new Engine(L, { boron: 2500 }, 1)).toThrow(InitError);
    const plain = new Engine(await loadSyntheticCore(), {}, 1);
    plain.submit({ type: "boron.set", ppm: 900 });
    plain.step();
    expect(plain.events.filter((x) => x.type === "command").map((x) => x.reason)).toEqual(["REJ_UNKNOWN_COMMAND"]);
    expect(() => new Engine(plain.lib, { boron: 900 }, 1)).toThrow(InitError);
  });

  it("init.boron must be a finite number in range", async () => {
    const L = await loadBoronCore();
    for (const bad of [true, "900", null, [], {}, NaN, Infinity, 2500]) {
      expect(() => new Engine(L, { boron: bad }, 1), JSON.stringify(bad)).toThrow(InitError);
    }
    expect(new Engine(L, { boron: 900 }, 1).boronValue(0)).toBe(900);
  });

  it("an interlock can block the command", async () => {
    const L = await loadBoronCore();
    L.interlocks.push({ id: "no-boron-change", when: { signal: "truth.mode", op: "eq", value: "steady" }, blocks: ["boron.set"], reason: "test" });
    const { e } = await make(L);
    e.submit({ type: "boron.set", ppm: 900 });
    e.step();
    expect(e.events.filter((x) => x.type === "command").map((x) => x.reason)).toEqual(["REJ_INTERLOCK:no-boron-change"]);
  });

  it("a checkpoint in mid-ramp resumes the same run, and a session replays to it", async () => {
    const { L, e: a } = await make();
    a.submit({ type: "boron.set", ppm: 980 });
    a.advance(7.5);
    const b = Engine.restore(L, a.checkpoint());
    a.advance(40);
    b.advance(40);
    expect(b.y).toEqual(a.y);
    expect(b.boronValue(b.t)).toBe(980);
    const c = Engine.replay(L, a.session(), a.stepIndex);
    expect(c.y).toEqual(a.y);
  });

  it("a trip can watch the concentration, located inside the step", async () => {
    const L = await loadBoronCore();
    L.boronMaxRate = 5;
    L.trips.push({ id: "boron-low", input: "truth.boron", predicate: { op: "lt", value: 950 }, latching: true });
    const { e } = await make(L);
    e.submit({ type: "boron.set", ppm: 900 });
    e.advance(12);
    expect(e.latched).toContain("boron-low");
    const trip = e.events.find((x) => x.type === "trip" && x.id === "boron-low")!;
    expect(Math.abs(trip.t - 10)).toBeLessThan(1e-6);
  });
});
