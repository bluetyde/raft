import { beforeAll, describe, expect, it } from "vitest";
import { join } from "node:path";
import { nodeReader } from "../../library/node-reader";
import { loadLibrary } from "../../sim/library";
import { repoRoot } from "../../sim/testing";
import { cutawayHalfSpace } from "./explorer";
import { elementShares, modelFromLibrary, pick, solidIntervals, type PrimitiveInfo, type Vec3, type ViewerModel } from "./model";
import { styleFor } from "./styles";

const LIBS = ["schema/vectors/synthetic-core", "libraries/triga-jsi-242"];
const models: Record<string, ViewerModel> = {};

beforeAll(async () => {
  for (const name of LIBS) models[name] = modelFromLibrary(await loadLibrary(nodeReader(join(repoRoot, name))));
});

const pickable = (p: PrimitiveInfo) => styleFor(p.material).pickable;
const down: Vec3 = [0, 0, -1];

/** A point on the primitive's top face: the centre, or mid-ring for an annulus. */
function topPoint(p: PrimitiveInfo): [number, number] {
  if (p.type === "annulus") return [p.center[0] + (p.rInner + p.radius) / 2, p.center[1]];
  return [p.center[0], p.center[1]];
}

describe.each(LIBS)("exact picking on %s", (name) => {
  it("every element and rod primitive is pickable from above, by its index", () => {
    const m = models[name]!;
    const tagged = m.primitives.filter((p) => p.element !== undefined || p.rod !== undefined);
    expect(tagged.length).toBeGreaterThan(0);
    for (const p of tagged) {
      const [x, y] = topPoint(p);
      // rods fully inserted, so every rod sits in the core like the elements
      const rods = Object.fromEntries(Object.keys(m.rodTravelCm).map((r) => [r, 0]));
      const hit = pick(m, [x, y, 500], down, { rods, pickable });
      expect(hit?.index, `primitive ${p.index} (${p.material} ${p.element ?? p.rod})`).toBe(p.index);
    }
  });

  it("a withdrawn rod is picked at its new height, and not at the old one", () => {
    const m = models[name]!;
    const rod = m.primitives.find((p) => p.rod !== undefined)!;
    const travel = m.rodTravelCm[rod.rod!]!;
    const side: Vec3 = [1, 0, 0];
    const zIn = rod.center[2];
    const zOut = rod.center[2] + travel;
    // From the side, other solids may be in front, so this uses a model with only the rod.
    const only = { ...m, primitives: [rod] };
    expect(pick(only, [rod.center[0] - 200, rod.center[1], zOut], side, { rods: { [rod.rod!]: 1 } })?.index).toBe(rod.index);
    expect(pick(only, [rod.center[0] - 200, rod.center[1], zIn], side, { rods: { [rod.rod!]: 1 } })).toBeNull();
    expect(pick(only, [rod.center[0] - 200, rod.center[1], zIn], side, { rods: { [rod.rod!]: 0 } })?.index).toBe(rod.index);
  });

  it("the cutaway removes what it cuts: a cut at x = 0 hides elements with x > 0 from above", () => {
    const m = models[name]!;
    const cut = cutawayHalfSpace({ axis: "x", position: 0, flip: false }); // keep x <= 0
    for (const p of m.primitives.filter((q) => q.element !== undefined && q.material === "fuel")) {
      const [x, y] = topPoint(p);
      const hit = pick(m, [x, y, 500], down, { cut, pickable });
      if (p.center[0] - (p.type === "box" ? 0 : p.radius) > 1e-9) {
        expect(hit === null || hit.index !== p.index).toBe(true);
      } else if (p.center[0] + (p.type === "box" ? 0 : p.radius) < -1e-9) {
        expect(hit?.index).toBe(p.index);
      }
    }
  });

  it("a ray into a cut solid enters through the cut face", () => {
    const m = models[name]!;
    const fuel = m.primitives.find((q) => q.material === "fuel" && q.element !== undefined)!;
    // keep z <= centre: the top half is removed, so a ray from above enters the fuel at the cut
    const cut = cutawayHalfSpace({ axis: "z", position: fuel.center[2], flip: false });
    const hit = pick(m, [fuel.center[0], fuel.center[1], 500], down, { cut, pickable })!;
    expect(hit.index).toBe(fuel.index);
    expect(hit.onCut).toBe(true);
    expect(hit.point[2]).toBeCloseTo(fuel.center[2], 9);
  });

  it("element shares sum to 1 (the base shape is normalized)", () => {
    const s = [...elementShares(models[name]!).values()].reduce((a, b) => a + b, 0);
    expect(s).toBeCloseTo(1, 4);
  });
});

describe("ray-solid intervals", () => {
  const ann: PrimitiveInfo = { type: "annulus", center: [0, 0, 0], rInner: 1, radius: 2, height: 4, material: "steel", index: 0 };
  const m: ViewerModel = { libraryId: "t", primitives: [ann], rodTravelCm: {}, refRods: {}, elements: [], axialEdgesCm: [0, 1], baseShape: [1] };

  it("a ray through an annulus's hole along its axis misses it", () => {
    expect(pick(m, [0, 0, 10], down)).toBeNull();
  });

  it("a ray across an annulus gives two parts, with the hole between", () => {
    const iv = solidIntervals(ann, 0, [-10, 0, 0], [1, 0, 0]);
    expect(iv).toHaveLength(2);
    expect(iv[0]![0]).toBeCloseTo(8, 12);
    expect(iv[0]![1]).toBeCloseTo(9, 12);
    expect(iv[1]![0]).toBeCloseTo(11, 12);
    expect(iv[1]![1]).toBeCloseTo(12, 12);
  });

  it("from inside a solid, the solid is skipped (noclip)", () => {
    expect(pick(m, [1.5, 0, 0], [1, 0, 0])).toBeNull();
    expect(pick(m, [1.5, 0, 0], [-1, 0, 0])?.index).toBe(0); // across the hole to the other side
  });

  it("boxes use the slab test", () => {
    const box: PrimitiveInfo = { type: "box", center: [0, 0, 5], size: [2, 4, 6], material: "steel", index: 0 };
    const iv = solidIntervals(box, 0, [0, -10, 5], [0, 1, 0]);
    expect(iv).toEqual([[8, 12]]);
    expect(solidIntervals(box, 0, [5, -10, 5], [0, 1, 0])).toEqual([]);
  });
});
