import { describe, expect, it } from "vitest";
import { Engine } from "../../sim/engine";
import { loadSyntheticCore } from "../../sim/testing";
import { elementPowers, formatPeriod, formatPower, powerColors, rodPositionsFrom } from "./live";
import { viridis } from "./styles";

describe("snapshot to view", () => {
  it("rod positions come from snapshot.truth.rods", async () => {
    const L = await loadSyntheticCore();
    const e = new Engine(L, {}, 1);
    e.submit({ type: "rod.move", rod: "regulating", direction: "out" });
    e.advance(1);
    const rods = rodPositionsFrom(e.snapshot());
    expect(Object.keys(rods).sort()).toEqual(L.rods.map((r) => r.id).sort());
    expect(rods["regulating"]).toBeCloseTo(e.rodPosition("regulating", e.t), 15);
  });

  it("element powers from the engine's live shape add up to the total power", async () => {
    const L = await loadSyntheticCore();
    const e = new Engine(L, {}, 1);
    const snap = e.snapshot(true);
    const bins = L.shapes.bins;
    const A = bins.axialEdgesCm.length - 1;
    const p = elementPowers(Float32Array.from(snap.truth.shape), bins.elements, A, snap.truth.power);
    expect(p.size).toBe(bins.elements.length);
    const sum = [...p.values()].reduce((a, b) => a + b, 0);
    expect(sum / snap.truth.power).toBeCloseTo(1, 6);
    // one element by hand
    const e0 = snap.truth.shape.slice(0, A).reduce((a: number, b: number) => a + b, 0);
    const tot = snap.truth.shape.reduce((a: number, b: number) => a + b, 0);
    expect(p.get(bins.elements[0])! / snap.truth.power).toBeCloseTo(e0 / tot, 6);
  });

  it("rejects a shape of the wrong size", () => {
    expect(() => elementPowers([1, 2, 3], ["a", "b"], 2, 1)).toThrow(RangeError);
  });

  it("colours scale to the hottest element", () => {
    const c = powerColors(new Map([["a", 0], ["b", 5], ["c", 10]]));
    expect(c.get("c")).toEqual(viridis(1));
    expect(c.get("b")).toEqual(viridis(0.5));
    expect(c.get("a")).toEqual(viridis(0));
    expect(powerColors(new Map([["a", 0]])).get("a")).toEqual(viridis(0));
  });
});

describe("display formats", () => {
  it.each([
    [0, "0 W"],
    [1.234e6, "1.23 MW"],
    [999, "999 W"],
    [2.5e-3, "2.50 mW"],
    [1.5e-12, "1.50e-12 W"],
    [-4.2e3, "-4.20 kW"],
  ])("formatPower(%s) = %s", (w, s) => {
    expect(formatPower(w)).toBe(s);
  });

  it("formatPeriod shows ∞ when steady", () => {
    expect(formatPeriod(null)).toBe("∞");
    expect(formatPeriod(Infinity)).toBe("∞");
    expect(formatPeriod(12.345)).toBe("12.3 s");
    expect(formatPeriod(-80)).toBe("-80.0 s");
  });
});
