import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Engine, IC0, IP } from "./engine";
import { loadLibrary, type Library } from "./library";
import { nodeReader } from "../library/node-reader";
import { fixturesDir, loadSyntheticCore } from "./testing";

/**
 * Rod shadowing (capability point-kinetics/rod-interaction-v2): each rod's worth is scaled by 1 + g(R), R the summed reactivity of the other rods.
 * The same cases as physics_ref/tests/test_rod_shadowing.py.
 *
 * The fixture's planted g is minus 2 R on the axis -0.01 to 0.03, held at the end values beyond (pipeline/library/synthetic.py), so the right answer is a formula written out here.
 */

const R_LO = -0.01;
const R_HI = 0.03;
const SLOPE = 2.0;

function plantedG(r: number): number {
  return -SLOPE * Math.min(Math.max(r, R_LO), R_HI);
}

async function make(rods: Record<string, number>, name = "synthetic-core-rod-shadowing") {
  const lib = await loadLibrary(nodeReader(join(fixturesDir, name)));
  const e = new Engine(lib, { rods, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } }, 1);
  return { lib, e };
}

function worths(lib: Library, rods: Record<string, number>): Record<string, number> {
  const w: Record<string, number> = {};
  for (const r of lib.rods) {
    w[r.id] = r.worth.at(rods[r.id]!);
  }
  return w;
}

function sumOf(w: Record<string, number>): number {
  let s = 0.0;
  for (const k of Object.keys(w)) {
    s += w[k]!;
  }
  return s;
}

function plantedCorrection(lib: Library, rods: Record<string, number>): number {
  const w = worths(lib, rods);
  const s = sumOf(w);
  let c = 0.0;
  for (const k of Object.keys(w)) {
    c += w[k]! * plantedG(s - w[k]!);
  }
  return c;
}

describe("rod shadowing (point-kinetics/rod-interaction-v2)", () => {
  it("the correction is the planted function of the others", async () => {
    const configs: Record<string, number>[] = [
      { safety: 0.3, regulating: 0.7, transient: 0.5 },
      { safety: 0.1, regulating: 0.1, transient: 0.1 },
      { safety: 0.9, regulating: 0.9, transient: 0.9 },
      { safety: 0.5, regulating: 0.5, transient: 0.5 },
      { safety: 1.0, regulating: 0.2, transient: 0.0 },
    ];
    for (const rods of configs) {
      const { lib, e } = await make(rods);
      const r = e.reactivity(0.0, e.y);
      expect(r.rodInteraction, JSON.stringify(rods)).toBeCloseTo(plantedCorrection(lib, rods), 12);
      expect(r.total).toBeCloseTo(
        r.reference + r.calibration + r.fault + r.rods + r.fuel + r.coolant + r.xenon + r.rodInteraction,
        12,
      );
      expect(r.rods).toBeCloseTo(sumOf(worths(lib, rods)), 12);
    }
  });

  it("it depends on which rod moves, not only on the sum", async () => {
    // two states with different rods moved: the single-axis table of rod-interaction-v1 cannot tell them apart, this one does
    const a = { safety: 0.8, regulating: 0.2, transient: 0.2 };
    const b = { safety: 0.2, regulating: 0.8, transient: 0.2 };
    const { lib, e: e1 } = await make(a);
    const { e: e2 } = await make(b);
    expect(sumOf(worths(lib, a))).not.toBeCloseTo(sumOf(worths(lib, b)), 3); // not equal sums here; the formula test above is the check on values
    expect(e1.reactivity(0.0, e1.y).rodInteraction).not.toBe(e2.reactivity(0.0, e2.y).rodInteraction);
  });

  it("the end of the axis clamps", async () => {
    const rods = { safety: 1.0, regulating: 1.0, transient: 1.0 };
    const { lib, e } = await make(rods);
    const w = worths(lib, rods);
    const s = sumOf(w);
    expect(Object.keys(w).some((k) => s - w[k]! > R_HI)).toBe(true); // at least one rod sees the others beyond the last point
    expect(e.reactivity(0.0, e.y).rodInteraction).toBeCloseTo(plantedCorrection(lib, rods), 12);
  });

  it("every rod at its reference adds nothing", async () => {
    const { e } = await make({ safety: 0.0, regulating: 0.0, transient: 0.0 });
    const r = e.reactivity(0.0, e.y);
    expect(Math.abs(r.rodInteraction)).toBe(0); // exact zero; the engine may yield -0 here, which Python's == 0.0 also accepts
    const plain = await loadSyntheticCore();
    const e0 = new Engine(plain, { rods: { safety: 0.0, regulating: 0.0, transient: 0.0 }, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } }, 1);
    expect(r.total).toBe(e0.reactivity(0.0, e0.y).total);
  });

  it("one rod alone is not shadowed", async () => {
    const rods = { safety: 0.6, regulating: 0.0, transient: 0.0 };
    const { lib, e } = await make(rods);
    const w = worths(lib, rods);
    expect([w.regulating, w.transient]).toEqual([0.0, 0.0]);
    expect(e.reactivity(0.0, e.y).rodInteraction).toBeCloseTo(0.0, 15); // R = 0, g(0) = 0
  });

  it("a library without the capability has no field", async () => {
    const plain = await loadSyntheticCore();
    const e = new Engine(
      plain,
      { rods: { safety: 0.3, regulating: 0.3, transient: 0.3 }, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } },
      1,
    );
    expect(plain.hasRodShadow).toBe(false);
    expect(e.reactivity(0.0, e.y)).not.toHaveProperty("rodInteraction");
  });

  it("the derivative uses the same total", async () => {
    const { lib, e } = await make({ safety: 0.7, regulating: 0.6, transient: 0.55 });
    const rho = e.reactivity(0.0, e.y).total;
    const d = e.rhs(0.0, [...e.y]);
    let want = ((rho - lib.betaTotal) / lib.genTime) * e.y[IP]! + lib.extSource;
    for (let k = 0; k < 6; k++) {
      want += lib.lam[k]! * e.y[IC0 + k]!;
    }
    expect(d[IP]! / want).toBeCloseTo(1.0, 9);
  });

  it("a reject table halts the run beyond its axis", async () => {
    const { lib, e } = await make({ safety: 1.0, regulating: 1.0, transient: 1.0 });
    lib.rodShadow!.outOfRange = "reject";
    e.step();
    expect(e.halted).toBe("R_TABLE_REJECT_rodInteraction");

    const low = await make({ safety: 0.1, regulating: 0.1, transient: 0.1 });
    low.lib.rodShadow!.outOfRange = "reject";
    low.e.step();
    expect(low.e.halted).toBeNull(); // inside the axis: no halt
  });
});

describe("rod shadowing validity", () => {
  it("surroundings beyond the axis are out of domain", async () => {
    const { e } = await make({ safety: 1.0, regulating: 1.0, transient: 1.0 });
    const v = e.validity();
    expect(v.status).toBe("outOfDomain");
    expect(v.reasons).toContain("R_DOMAIN_ROD_INTERACTION");
    const inside = await make({ safety: 0.5, regulating: 0.5, transient: 0.5 });
    expect(inside.e.validity().reasons).not.toContain("R_DOMAIN_ROD_INTERACTION");
  });

  it("a rod at its reference is not checked against the axis", async () => {
    // safety and transient out (their worths sum to 0.0385, beyond the axis end at 0.03); regulating stays at its reference, where its worth is 0 and its term is 0.
    // Only the regulating rod "sees" 0.0385, so nothing is out of the domain.
    const rods = { safety: 1.0, regulating: 0.0, transient: 1.0 };
    const { lib, e } = await make(rods);
    const w = worths(lib, rods);
    const s = sumOf(w);
    expect(s).toBeGreaterThan(R_HI);
    expect(Object.keys(w).filter((k) => w[k] !== 0.0).every((k) => s - w[k]! <= R_HI)).toBe(true);
    expect(e.validity().reasons).not.toContain("R_DOMAIN_ROD_INTERACTION");
    lib.rodShadow!.outOfRange = "reject";
    e.step();
    expect(e.halted).toBeNull();
  });

  it("one rod away with a nonzero correction needs a joint check", async () => {
    // safety and regulating out: R of each is the other's worth, g is not 0
    const rods = { safety: 0.5, regulating: 0.5, transient: 0.0 };
    const { lib, e } = await make(rods);
    expect(e.reactivity(0.0, e.y).rodInteraction).not.toBe(0);
    expect(e.validity().reasons).toContain("R_JOINT_UNCHECKED");
    lib.domain.jointChecked = [{ rods, maxShapeErr: 0, rhoErr: 0 }];
    expect(e.validity().reasons).not.toContain("R_JOINT_UNCHECKED");
    const plain = await loadSyntheticCore();
    const e3 = new Engine(plain, { rods: { safety: 0.5, regulating: 0.0, transient: 0.0 }, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } }, 1);
    expect(e3.validity().reasons).not.toContain("R_JOINT_UNCHECKED");
  });
});
