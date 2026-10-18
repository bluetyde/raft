import { describe, expect, it } from "vitest";
import { Engine } from "../../sim/engine";
import { loadSyntheticCore } from "../../sim/testing";
import { faultLabel, instrumentFault, pumpFault, reactivityFault, WAITING_FOR_ENGINE } from "./faults";
import { formatOuterStep, OUTER_STEPS, ratesFor } from "./time";
import { Timeline } from "./timeline";
import { activeFaultLines, formatPcm, formatSignal, instrumentRows, PCM, REACTIVITY_SOURCES, reactivityBars } from "./truth";

describe("time settings (D5, amendment 1)", () => {
  it("offers rates that the outer step can reach", () => {
    expect(ratesFor(0.01)).toEqual([0.1, 1, 10, 30, 100]);
    expect(ratesFor(0.001)).toEqual([0.1, 1, 10, 30, 100]);
    expect(ratesFor(1)).toContain(3600);
    expect(Math.max(...ratesFor(0.01))).toBeLessThanOrEqual(150);
  });

  it("names the session's outer step", () => {
    expect(formatOuterStep(0.01)).toBe("10 ms (fine)");
    expect(formatOuterStep(0.001)).toBe("1 ms (fine)");
    expect(formatOuterStep(1)).toBe("1 s (coarse)");
    expect(formatOuterStep(0.1)).toBe("100 ms (coarse)");
    expect(OUTER_STEPS.map((s) => s.outerDt)).toEqual([0.01, 1]);
  });
});

describe("timeline", () => {
  it("shows the worker's marks, the notes and the branch point in time order, and maps the bar to steps", () => {
    const tl = new Timeline();
    tl.set(
      [
        { kind: "rejected", t: 2, label: "operator: REJ_TRIPPED" },
        { kind: "trip", t: 3, label: "trip period-short" },
      ],
      [{ id: 1, step: 400, t: 4, text: "note" }],
      1,
    );
    expect(tl.markers().map((m) => [m.kind, m.t])).toEqual([
      ["fork", 1],
      ["rejected", 2],
      ["trip", 3],
      ["note", 4],
    ]);
    expect(tl.endT).toBe(4);
    tl.setEnd(10);
    expect(tl.position(5)).toBe(0.5);
    expect(tl.stepAt(0.5, 0.01)).toBe(500);
    expect(tl.stepAt(2, 0.01)).toBe(1000);
    expect(tl.stepAt(-1, 0.01)).toBe(0);
  });

  it("ends at the rewind point, and a reset clears all", () => {
    const tl = new Timeline();
    tl.set([{ kind: "trip", t: 5, label: "b" }], [], null);
    tl.rewoundTo(2);
    expect(tl.endT).toBe(2);
    tl.set([], [], null);
    expect(tl.markers()).toHaveLength(0);
    tl.setEnd(3);
    tl.reset();
    expect(tl.endT).toBe(0);
  });
});

describe("faults (D3, amendment 2)", () => {
  it("builds the engine's fault commands", () => {
    expect(instrumentFault("log", "stuck")).toEqual({ type: "fault.instrument", instrument: "log", kind: "stuck" });
    expect(pumpFault("primary", false)).toEqual({ type: "pump.set", pump: "primary", on: false });
    expect(reactivityFault(50)).toEqual({ type: "fault.reactivity", deltaRho: 50 * PCM });
    expect(() => reactivityFault(0)).toThrow();
    expect(() => reactivityFault(Number.NaN)).toThrow();
    expect(faultLabel(reactivityFault(-20))).toBe("reactivity -20.0 pcm");
  });

  it("offers no reactivity clear until the engine has one", () => {
    expect(WAITING_FOR_ENGINE).toContain("clear of inserted reactivity");
  });
});

describe("truth panel on the real engine", () => {
  it("shows a stuck and a dead instrument against the true value, and the inserted reactivity as a source", async () => {
    const lib = await loadSyntheticCore();
    const e = new Engine(lib, { rods: { regulating: 0.6584003609387292, safety: 1.0, transient: 0.0 } }, 1);
    e.step();
    const before = e.indicated["log"]!;
    e.submit(instrumentFault("log", "stuck"), "instructor");
    e.submit(instrumentFault("linear", "dead"), "instructor");
    e.submit(reactivityFault(80), "instructor");
    e.submit({ type: "rod.move", rod: "transient", direction: "out" }, "operator");
    e.advance(5);
    const s = e.snapshot();
    const faults = { instruments: { ...e.faults }, extraRho: e.extraRho };
    const rows = instrumentRows(lib.instruments, s, faults);
    const log = rows.find((r) => r.id === "log")!;
    const linear = rows.find((r) => r.id === "linear")!;
    expect(log.fault).toBe("stuck");
    expect(log.truth).toBe(s.truth.power);
    // the stuck reading keeps its value from before the fault, while the true power changes
    // (the step insertion trips period-short at once, so the true power falls after the scram)
    expect(log.indicated).toBe(before);
    expect(s.tripped).toBe(true);
    expect(Math.abs(s.truth.power - before)).toBeGreaterThan(0.5 * before);
    expect(linear).toMatchObject({ fault: "dead", indicated: null });
    const { bars, totalPcm } = reactivityBars(s.truth.reactivity);
    expect(bars.find((b) => b.source === "fault")!.pcm).toBeCloseTo(80, 9);
    expect(totalPcm).toBeCloseTo(s.truth.reactivity.total / PCM, 9);
    expect(Math.max(...bars.map((b) => b.size))).toBe(1);
    expect(activeFaultLines(faults, s.truth.pumps)).toEqual([
      "instrument linear: dead",
      "instrument log: stuck",
      "reactivity inserted: 80.0 pcm",
    ]);
  });

  it("the reactivity bars include every source the engine reports, so they add up to the total", () => {
    const r = { total: 0.0123, reference: -0.01, calibration: 0.01, fault: 0.0, rods: 0.005, fuel: -0.001, coolant: 0.0, xenon: 0.0, boron: 0.0073, rodInteraction: 0.0010 };
    const { bars, totalPcm } = reactivityBars(r);
    expect(bars.map((b) => b.source)).toEqual([...REACTIVITY_SOURCES, "boron", "rodInteraction"]);
    expect(bars.reduce((a, b) => a + b.pcm, 0)).toBeCloseTo(totalPcm, 9);
  });

  it("lists a pump that is off", () => {
    expect(activeFaultLines({ instruments: {}, extraRho: 0 }, { primary: false })).toEqual(["pump primary: off"]);
    expect(activeFaultLines({ instruments: {}, extraRho: 0 }, { primary: true })).toEqual([]);
  });
});

describe("truth panel formats", () => {
  it("shows power in W, temperatures in °C, and no -0.0 pcm", () => {
    expect(formatSignal("truth.fuelTemp", 293.15)).toBe("20.00 °C");
    expect(formatSignal("truth.coolantTemp", 373.15)).toBe("100.00 °C");
    expect(formatSignal("truth.power", 1e-3)).toContain("W");
    expect(formatSignal("truth.power", null)).toBe("—");
    expect(formatSignal("truth.other", 1.234567)).toBe("1.2346");
    expect(formatPcm(-1e-9)).toBe("0.0");
    expect(formatPcm(-12.34)).toBe("-12.3");
  });
});
