import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Engine } from "./engine";
import { loadLibrary } from "./library";
import { nodeReader } from "../library/node-reader";
import { fixturesDir } from "./testing";

/** A checked state may carry a boron window (library format section 13): it then covers only states whose boron lies inside it. The same cases as physics_ref/tests/test_joint_checked_boron.py. */

const RODS = { safety: 0.5, regulating: 0.5, transient: 0.0 }; // two rods away from their references: a joint state

async function engine(boron: number, windows: Record<string, unknown>[], rods: Record<string, number> = RODS, fixture = "synthetic-core-boron") {
  const lib = await loadLibrary(nodeReader(join(fixturesDir, fixture)));
  lib.manifest.domain.jointChecked = windows.map((w) => ({ rods: { ...RODS }, maxShapeErr: 0, rhoErr: 0, ...w }));
  const init: Record<string, unknown> = { rods: { ...rods }, power: { mode: "given", value: 1.0 }, poisons: { mode: "zero" } };
  if (fixture === "synthetic-core-boron") {
    init["boron"] = boron;
  }
  return new Engine(lib, init, 1);
}

const reasons = (e: Engine) => e.validity().reasons as string[];

describe("a boron window on a checked state", () => {
  it("a state with no window covers any boron", async () => {
    for (const b of [900, 1000, 1100]) {
      expect(reasons(await engine(b, [{}]))).not.toContain("R_JOINT_UNCHECKED");
    }
  });

  it("a window covers only its boron, and its ends are inside", async () => {
    const w = [{ boron: [990, 1010] }];
    expect(reasons(await engine(1000, w))).not.toContain("R_JOINT_UNCHECKED");
    expect(reasons(await engine(990, w))).not.toContain("R_JOINT_UNCHECKED");
    expect(reasons(await engine(1010, w))).not.toContain("R_JOINT_UNCHECKED");
    expect(reasons(await engine(989.9, w))).toContain("R_JOINT_UNCHECKED");
    expect(reasons(await engine(1010.1, w))).toContain("R_JOINT_UNCHECKED");
  });

  it("another entry for the same rods at another boron covers that boron", async () => {
    const w = [{ boron: [990, 1010] }, { boron: [880, 900] }];
    expect(reasons(await engine(890, w))).not.toContain("R_JOINT_UNCHECKED");
    expect(reasons(await engine(950, w))).toContain("R_JOINT_UNCHECKED");
  });

  it("the window does not make other rod positions covered", async () => {
    const w = [{ boron: [990, 1010] }];
    expect(reasons(await engine(1000, w, { safety: 0.9, regulating: 0.1, transient: 0.0 }))).toContain("R_JOINT_UNCHECKED");
  });

  it("a library without boron ignores a window it cannot carry", async () => {
    const e = await engine(0, [{ boron: [990, 1010] }], RODS, "synthetic-core");
    expect(reasons(e)).not.toContain("R_JOINT_UNCHECKED");
  });
});
