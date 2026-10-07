import { describe, expect, it } from "vitest";
import { Engine } from "../../sim/engine";
import { loadSyntheticCore } from "../../sim/testing";
import { nearCriticalRods } from "../../sim/vectors";
import { Annunciator } from "./annunciator";
import { CONSOLE_TRUTH_FIELDS, consoleState, operatorView, stripTruthPhysics } from "./console";
import { isPegged, kelvinToCelsius, meterReading, metersFrom, roleOf, type InstrumentSpec } from "./meters";
import { PeriodEstimator } from "./period";
import { chartPoints, StripBuffer } from "./strip";

describe("what the operator may read", () => {
  it("consoleState returns only the whitelisted fields, and no truth physics", async () => {
    const L = await loadSyntheticCore();
    const e = new Engine(L, {}, 1);
    e.advance(0.5);
    const c = consoleState(e.snapshot(true));
    expect(Object.keys(c).sort()).toEqual(["mode", "pumps", "rods", "t", "tripped", "trips", "validity"]);
    expect(Object.keys(c.rods).sort()).toEqual(L.rods.map((r) => r.id).sort());
    for (const r of Object.values(c.rods)) expect(Object.keys(r).sort()).toEqual(["moving", "position"]);
    const flat = JSON.stringify(c);
    for (const physics of ["power", "period", "fuelTemp", "coolantTemp", "reactivity", "xenon", "iodine", "precursors", "shape", "peak"]) {
      expect(flat).not.toContain(`"${physics}`);
    }
  });

  it("truth guard: a snapshot without truth physics gives the same operator view (console fields kept)", async () => {
    const L = await loadSyntheticCore();
    const e = new Engine(L, {}, 1);
    e.submit({ type: "rod.move", rod: "regulating", direction: "out" });
    e.advance(2);
    const snap = e.snapshot(true);
    const stripped = stripTruthPhysics(snap);
    expect(Object.keys(stripped.truth).sort()).toEqual([...CONSOLE_TRUTH_FIELDS].sort());
    expect(stripped.truth.power).toBeUndefined();
    expect(operatorView(stripped)).toEqual(operatorView(snap));
  });
});

describe("meters", () => {
  const specs: InstrumentSpec[] = [
    { id: "log", signal: "truth.power", scale: "log", range: [1e-4, 1e9], lag: 0, noise: 0 },
    { id: "linear", signal: "truth.power", scale: "linear", range: [0, 300000], lag: 0, noise: 0 },
    { id: "tc", signal: "truth.fuelTemp", scale: "linear", range: [273.15, 1273.15], lag: 0, noise: 0 },
  ];
  const [log, lin, tc] = metersFrom(specs);

  it("roles come from the signal", () => {
    expect([log!.role, lin!.role, tc!.role]).toEqual(["power", "power", "fuelTemp"]);
    expect(roleOf("truth.coolantTemp")).toBe("coolantTemp");
    expect(roleOf("truth.mode")).toBe("other");
  });

  it("log and linear needles, pegging and failure", () => {
    expect(meterReading(log!, 1e-4).fraction).toBeCloseTo(0, 12);
    expect(meterReading(log!, 1e9).fraction).toBeCloseTo(1, 12);
    expect(meterReading(log!, 10 ** 2.5).fraction).toBeCloseTo(6.5 / 13, 12);
    expect(meterReading(lin!, 150000).fraction).toBeCloseTo(0.5, 12);
    expect(meterReading(lin!, 4e5)).toEqual({ fraction: 1, peg: "over", failed: false });
    expect(meterReading(log!, 1e-6)).toEqual({ fraction: 0, peg: "under", failed: false });
    expect(meterReading(lin!, null)).toEqual({ fraction: 0, peg: null, failed: true });
    expect(isPegged(lin!, 4e5)).toBe(true);
    expect(isPegged(lin!, 1)).toBe(false);
    expect(isPegged(lin!, null)).toBe(false);
  });

  it("temperatures show in °C", () => {
    expect(kelvinToCelsius(273.15)).toBe(0);
    expect(kelvinToCelsius(873.15)).toBeCloseTo(600, 12);
  });
});

describe("derived period (D3, amendment 2)", () => {
  it("matches the engine's true period from the noisy, lagged log channel", async () => {
    const L = await loadSyntheticCore();
    // the golden period-trip setup, with the transient rod stopped just before the trip: a short, slowly lengthening period
    const e = new Engine(L, { rods: { regulating: 0.6584003609387292, safety: 1.0, transient: 0.0 } }, 11);
    e.submit({ type: "rod.move", rod: "transient", direction: "out" });
    e.advance(16.3);
    e.submit({ type: "rod.move", rod: "transient", direction: "stop" });
    const log = L.instruments.find((i: any) => i.id === "log")!;
    expect(log.lag).toBeGreaterThan(0);
    expect(log.noise).toBeGreaterThan(0);
    const meter = metersFrom([log])[0]!;
    const est = new PeriodEstimator();
    const checks: [number, number][] = [];
    let samples = 0;
    for (let i = 0; i < 1000; i++) {
      e.step();
      if (e.stepIndex % 3 === 0) {
        // about 30 Hz of sim time, as a panel at 1x sees it
        const v = e.indicated["log"];
        est.push(e.t, v, isPegged(meter, v));
        const got = est.read(e.mode);
        if (got !== null && ++samples % 30 === 0) checks.push([got, e.snapshot().truth.period]);
      }
    }
    expect(e.snapshot().tripped).toBe(false);
    expect(checks.length).toBeGreaterThan(5);
    for (const [got, truth] of checks) {
      expect(truth).toBeGreaterThan(3);
      expect(truth).toBeLessThan(15);
      expect(Math.abs(got / truth - 1)).toBeLessThan(0.1);
    }
  });

  it("noise on a steady or very slow change reads as steady (∞), not as a jumping number", () => {
    const est = new PeriodEstimator();
    let seed = 7;
    const rand = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31) * 2 - 1;
    const readings: (number | null)[] = [];
    for (let k = 0; k <= 600; k++) {
      const t = k / 30;
      est.push(t, Math.exp(t / 1000) * (1 + 0.02 * rand()), false); // 1000 s period under 2 % noise
      if (k > 60) readings.push(est.read("steady"));
    }
    const infinite = readings.filter((r) => r === Infinity).length;
    expect(infinite / readings.length).toBeGreaterThan(0.95);
    // what matters to an operator: noise never shows a short, alarming period (60 s is 20 times the libraries' 3 s trip setpoint)
    for (const r of readings) if (r !== null && r !== Infinity) expect(Math.abs(r)).toBeGreaterThan(60);
  });

  it("skips null and pegged readings, and shows — when too few points remain", () => {
    const est = new PeriodEstimator({ windowS: 2, minPoints: 8 });
    for (let k = 0; k <= 60; k++) est.push(k / 30, Math.exp(k / 30 / 10), false); // period 10 s
    expect(est.read("steady")).toBeCloseTo(10, 6);
    // a dead or pegged channel adds nothing; once the window passes, there is no reading
    for (let k = 61; k <= 200; k++) est.push(k / 30, k % 2 ? null : 1e20, k % 2 === 0);
    est.push(200 / 30 + 0.01, 5, false);
    expect(est.size).toBe(1);
    expect(est.read("steady")).toBeNull();
  });

  it("drops points from before a rewind, and shows — in pulse mode", () => {
    const est = new PeriodEstimator();
    for (let k = 0; k <= 90; k++) est.push(k / 30, Math.exp(k / 30 / 5), false);
    expect(est.read("steady")).toBeCloseTo(5, 6);
    expect(est.read("pulse")).toBeNull();
    est.push(1.0, 3, false); // time went back: a rewind
    expect(est.size).toBe(1);
    expect(est.read("steady")).toBeNull();
  });

  it("a steady reading is ∞", () => {
    const est = new PeriodEstimator();
    for (let k = 0; k <= 90; k++) est.push(k / 30, 7, false);
    expect(est.read("steady")).toBe(Infinity);
  });
});

describe("strip-chart buffer (amendment 1)", () => {
  it("a 10 ms spike survives at full height, however much the buffer thins", () => {
    const b = new StripBuffer(600, 3000); // 0.2 s buckets
    for (let i = 0; i <= 60_000; i++) {
      const t = i * 0.01; // one reading per 10 ms step, 600 s
      b.push(t, i === 31_234 ? 5e8 : 1 + 0.01 * Math.sin(i));
    }
    expect(b.max).toBe(5e8);
    const pts = b.points().filter((p): p is [number, number] => p !== null);
    const spike = pts.find(([, v]) => v === 5e8)!;
    expect(spike[0]).toBeCloseTo(312.34, 9);
    expect(Math.min(...pts.map(([, v]) => v))).toBeGreaterThan(0.98);
    expect(b.bucketCount).toBeLessThanOrEqual(3001);
  });

  it("dropAfter(-Infinity) empties it, so a replaced timeline starts a clean chart", () => {
    const b = new StripBuffer(600, 3000);
    for (let i = 0; i < 1000; i++) b.push(i * 0.01, 1 + i);
    expect(b.points().length).toBeGreaterThan(0);
    b.dropAfter(-Infinity);
    expect(b.points()).toEqual([]);
    b.push(2, 5);
    expect(b.points()).toEqual([[2, 5]]); // only the new reading
  });

  it("stays bounded over a long run, keeping the last window", () => {
    const b = new StripBuffer(10, 50);
    for (let i = 0; i < 100_000; i++) b.push(i * 0.01, i);
    expect(b.size).toBeLessThanOrEqual(100);
    const pts = b.points().filter((p): p is [number, number] => p !== null);
    expect(pts[0]![0]).toBeGreaterThanOrEqual(999.99 - 10 - 0.2);
  });

  it("a null reading makes one gap; a rewind drops later points", () => {
    const b = new StripBuffer(10, 50);
    for (let i = 0; i < 100; i++) b.push(i * 0.05, i < 40 || i > 60 ? 1 : null);
    expect(b.points().filter((p) => p === null)).toHaveLength(1);
    b.push(1.0, 2); // back in time
    const pts = b.points().filter((p): p is [number, number] => p !== null);
    expect(Math.max(...pts.map(([t]) => t))).toBeLessThanOrEqual(1.0);
    expect(pts.at(-1)).toEqual([1.0, 2]);
  });
});

describe("chart points from a snapshot (amendment 1)", () => {
  it("adds the extremes since the last snapshot, in time order, then the reading", () => {
    const ext = { min: 0.5, tMin: 1.23, max: 9e7, tMax: 1.21 };
    expect(chartPoints(1.3, 2, ext)).toEqual([
      [1.21, 9e7],
      [1.23, 0.5],
      [1.3, 2],
    ]);
    // a peak between snapshots reaches the buffer at full height
    const b = new StripBuffer(600, 3000);
    b.push(1.0, 1);
    for (const [t, v] of chartPoints(1.3, 2, ext)) b.push(t, v);
    expect(b.max).toBe(9e7);
    expect(chartPoints(1.3, null)).toEqual([[1.3, null]]);
  });
});

describe("annunciator (D1)", () => {
  const make = () => new Annunciator(["power-high", "period-short"], ["linear"], [{ id: "fire-needs-pulse-mode" }]);
  const state = (a: Annunciator, id: string) => a.list().find((t) => t.id === id)!.state;

  it("flashes a new trip until acknowledged, then stays lit while latched, then goes off", () => {
    const a = make();
    a.update({ latched: [], active: [] }, [{ id: "linear", failed: false, pegged: false }]);
    expect(state(a, "trip:power-high")).toBe("off");
    a.update({ latched: ["power-high"], active: [] }, [{ id: "linear", failed: false, pegged: false }]);
    expect(state(a, "trip:power-high")).toBe("flashing");
    a.acknowledge();
    expect(state(a, "trip:power-high")).toBe("lit");
    a.update({ latched: [], active: [] }, [{ id: "linear", failed: false, pegged: false }]);
    expect(state(a, "trip:power-high")).toBe("off");
  });

  it("an alarm that cleared before acknowledgement keeps flashing until acknowledged", () => {
    const a = make();
    a.update({ latched: [], active: [] }, [{ id: "linear", failed: true, pegged: false }]);
    a.update({ latched: [], active: [] }, [{ id: "linear", failed: false, pegged: false }]);
    expect(state(a, "failed:linear")).toBe("flashing");
    a.acknowledge();
    expect(state(a, "failed:linear")).toBe("off");
  });

  it("an interlock rejection flashes with its reason, and goes off when acknowledged", () => {
    const a = make();
    a.interlockRejected("REJ_INTERLOCK:fire-needs-pulse-mode", "The transient rod can only be fired in pulse mode.");
    const t = a.list().find((x) => x.id === "interlock:fire-needs-pulse-mode")!;
    expect(t.state).toBe("flashing");
    expect(t.detail).toContain("pulse mode");
    a.interlockRejected("REJ_TRIPPED"); // not an interlock: no tile
    a.acknowledge();
    expect(state(a, "interlock:fire-needs-pulse-mode")).toBe("off");
  });

  it("over range lights the range tile; reset forgets history", () => {
    const a = make();
    a.update({ latched: ["period-short"], active: [] }, [{ id: "linear", failed: false, pegged: true }]);
    expect(state(a, "range:linear")).toBe("flashing");
    a.reset();
    expect(a.list().every((t) => t.state === "off")).toBe(true);
  });
});
