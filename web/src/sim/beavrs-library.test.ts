import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Engine } from "./engine";
import { loadLibrary } from "./library";
import { nodeReader } from "../library/node-reader";
import { repoRoot } from "./testing";

/** The shipped BEAVRS library (pipeline.library.export_beavrs): both engines must agree on its critical boron, here the TypeScript one (the Python one is checked in pipeline/tests). */
const LIB = join(repoRoot, "libraries", "pwr-beavrs-hzp-openmc");

describe("pwr-beavrs-hzp-openmc", () => {
  it("is critical near 983 ppm at the benchmark rods, and the all-in state is far subcritical", async () => {
    const L = await loadLibrary(nodeReader(LIB));
    expect(L.hasBoron).toBe(true);
    const at = (ppm: number, rods?: Record<string, number>) => {
      const e = new Engine(L, { boron: ppm, rods: rods ?? {}, power: { mode: "given", value: 1e-3 }, poisons: { mode: "zero" } }, 1);
      return e.reactivity(0, e.y).total as number;
    };
    expect(at(975)).toBeCloseTo(0.00101385, 7);
    expect(Math.abs(at(983.18))).toBeLessThan(2e-6);
    const allIn = Object.fromEntries(L.rods.map((r) => [r.id, 0]));
    expect(at(975, allIn)).toBeLessThan(-0.05);
  });
});
