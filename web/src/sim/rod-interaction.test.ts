import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Engine, IC0, IP } from "./engine";
import { loadLibrary, type Library } from "./library";
import { nodeReader } from "../library/node-reader";
import { fixturesDir, loadSyntheticCore } from "./testing";

/**
 * Rod interaction (capability point-kinetics/rod-interaction-v1): a correction added to the sum of the single-rod reactivities, a function of that sum.
 * The same cases as physics_ref/tests/test_rod_interaction.py.
 *
 * The fixture's planted correction is minus 10 % of the sum, clamped beyond +0.03 (pipeline/library/synthetic.py), so the right answer is a formula written out here.
 */

const S_MAX = 0.03; // the table's last point; beyond it the correction clamps
const SHADOW = 0.1;

function plantedCorrection(s: number): number {
  return s >= -0.01 ? -SHADOW * Math.min(s, S_MAX) : -SHADOW * -0.01;
}

async function make(rods: Record<string, number>, name = "synthetic-core-rod-interaction") {
  const lib = await loadLibrary(nodeReader(join(fixturesDir, name)));
  const e = new Engine(lib, { rods, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } }, 1);
  return { lib, e };
}

function rodSum(lib: Library, rods: Record<string, number>): number {
  let s = 0.0;
  for (const r of lib.rods) {
    s += r.worth.at(rods[r.id]!);
  }
  return s;
}

describe("rod interaction (point-kinetics/rod-interaction-v1)", () => {
  it("the correction is the planted function of the summed reactivity", async () => {
    const configs: Record<string, number>[] = [
      { safety: 0.3, regulating: 0.7, transient: 0.5 },
      { safety: 0.1, regulating: 0.1, transient: 0.1 },
      { safety: 0.9, regulating: 0.9, transient: 0.9 },
      { safety: 0.5, regulating: 0.5, transient: 0.5 },
    ];
    for (const rods of configs) {
      const { lib, e } = await make(rods);
      const s = rodSum(lib, rods);
      const r = e.reactivity(0.0, e.y);
      expect(r.rodInteraction, JSON.stringify(rods)).toBeCloseTo(plantedCorrection(s), 12);
      expect(r.total).toBeCloseTo(
        r.reference + r.calibration + r.fault + r.rods + r.fuel + r.coolant + r.xenon + r.rodInteraction,
        12,
      );
      expect(r.rods).toBeCloseTo(s, 12);
    }
  });

  it("the end of the axis clamps", async () => {
    const rods = { safety: 1.0, regulating: 1.0, transient: 1.0 }; // the sum is +0.0525, beyond the last point at 0.03
    const { lib, e } = await make(rods);
    expect(rodSum(lib, rods)).toBeGreaterThan(S_MAX);
    expect(e.reactivity(0.0, e.y).rodInteraction).toBeCloseTo(-SHADOW * S_MAX, 12);
  });

  it("every rod at its reference adds nothing", async () => {
    const { e } = await make({ safety: 0.0, regulating: 0.0, transient: 0.0 });
    const r = e.reactivity(0.0, e.y);
    expect(Math.abs(r.rodInteraction)).toBe(0); // exact zero; the engine yields -0 here, which Python's == 0 also accepts
    const plain = await loadSyntheticCore();
    const e0 = new Engine(plain, { rods: { safety: 0.0, regulating: 0.0, transient: 0.0 }, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } }, 1);
    expect(r.total).toBe(e0.reactivity(0.0, e0.y).total);
  });

  it("a library without the capability has no field", async () => {
    const plain = await loadSyntheticCore();
    const e = new Engine(
      plain,
      { rods: { safety: 0.3, regulating: 0.3, transient: 0.3 }, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } },
      1,
    );
    expect(plain.hasRodInteraction).toBe(false);
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
    lib.rodInteraction!.outOfRange = "reject";
    e.step();
    expect(e.halted).toBe("R_TABLE_REJECT_rodInteraction");

    const low = await make({ safety: 0.1, regulating: 0.1, transient: 0.1 });
    low.lib.rodInteraction!.outOfRange = "reject";
    low.e.step();
    expect(low.e.halted).toBeNull(); // inside the axis: no halt
  });
});

describe("rod interaction validity", () => {
  it("a summed worth beyond the axis is out of domain", async () => {
    const { e } = await make({ safety: 1.0, regulating: 1.0, transient: 1.0 }); // +0.0525, the axis ends at 0.03
    const v = e.validity();
    expect(v.status).toBe("outOfDomain");
    expect(v.reasons).toContain("R_DOMAIN_ROD_INTERACTION");
    const inside = await make({ safety: 0.5, regulating: 0.5, transient: 0.5 }); // +0.026, inside
    expect(inside.e.validity().reasons).not.toContain("R_DOMAIN_ROD_INTERACTION");
  });

  it("one rod away with a nonzero correction needs a joint check", async () => {
    const one = { safety: 0.5, regulating: 0.0, transient: 0.0 };
    const { lib, e } = await make(one);
    expect(e.reactivity(0.0, e.y).rodInteraction).not.toBe(0);
    expect(e.validity().reasons).toContain("R_JOINT_UNCHECKED");
    lib.domain.jointChecked = [{ rods: one, maxShapeErr: 0, rhoErr: 0 }];
    expect(e.validity().reasons).not.toContain("R_JOINT_UNCHECKED");
    const plain = await loadSyntheticCore();
    const e3 = new Engine(plain, { rods: one, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } }, 1);
    expect(e3.validity().reasons).not.toContain("R_JOINT_UNCHECKED"); // without the capability one moved rod never needed it
  });
});

