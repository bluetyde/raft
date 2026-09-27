import { beforeAll, describe, expect, it } from "vitest";
import * as THREE from "three";
import { join } from "node:path";
import { nodeReader } from "../../library/node-reader";
import { loadLibrary } from "../../sim/library";
import { repoRoot } from "../../sim/testing";
import { cutawayHalfSpace } from "./explorer";
import { modelFromLibrary, type ViewerModel } from "./model";
import { CoreScene, fromScene, planeFor, toScene } from "./scene";

const LIBS = ["schema/vectors/synthetic-core", "libraries/triga-jsi-242"];
const models: Record<string, ViewerModel> = {};

beforeAll(async () => {
  for (const name of LIBS) models[name] = modelFromLibrary(await loadLibrary(nodeReader(join(repoRoot, name))));
});

/** The primitive's extents in library coordinates (cm, z up), as [min, max]. */
function libraryBox(m: ViewerModel, i: number, zOff = 0): [number[], number[]] {
  const p = m.primitives[i]!;
  const [cx, cy, cz] = p.center;
  const [hx, hy, hz] = p.type === "box" ? p.size.map((s) => s / 2) : [p.radius, p.radius, p.height / 2];
  return [
    [cx - hx!, cy - hy!, cz + zOff - hz!],
    [cx + hx!, cy + hy!, cz + zOff + hz!],
  ];
}

describe("coordinates", () => {
  it("library z-up maps to three.js y-up and back, right-handed", () => {
    const v = toScene([1, 2, 3]);
    expect([v.x, v.y, v.z]).toEqual([1, 3, -2]);
    expect(fromScene(v)).toEqual([1, 2, 3]);
    // x cross y = z in the library must stay x cross y = z after mapping (no mirror)
    const x = toScene([1, 0, 0]);
    const y = toScene([0, 1, 0]);
    const z = toScene([0, 0, 1]);
    expect(new THREE.Vector3().crossVectors(x, y).distanceTo(z)).toBeLessThan(1e-12);
  });

  it("a cutaway half-space and its three.js plane keep the same points", () => {
    const h = cutawayHalfSpace({ axis: "y", position: 3, flip: false }); // keep y <= 3
    const plane = planeFor(h);
    expect(plane.distanceToPoint(toScene([0, 2, 0]))).toBeGreaterThan(0);
    expect(plane.distanceToPoint(toScene([0, 4, 0]))).toBeLessThan(0);
  });
});

describe.each(LIBS)("scene for %s", (name) => {
  it("draws every visible primitive exactly once, where the library puts it", () => {
    const m = models[name]!;
    const s = new CoreScene(m);
    const instances = s.groups.reduce((n, g) => n + g.mesh.count, 0);
    const visible = m.primitives.filter((p) => p.material !== "void").length;
    expect(instances).toBe(visible);
    for (const p of m.primitives) {
      if (p.material === "void") continue;
      const zOff = p.rod !== undefined ? (m.refRods[p.rod] ?? 0) * m.rodTravelCm[p.rod]! : 0;
      const [lo, hi] = libraryBox(m, p.index, zOff);
      const b = s.boundsOf(p.index);
      const bl = fromScene(b.min);
      const bh = fromScene(b.max);
      // three.js y-up to z-up flips one axis, so compare sorted per-axis extents.
      // three.js stores positions as float32 (about 1e-6 cm at 20 cm), so 1e-4 cm is the tolerance.
      for (let k = 0; k < 3; k++) {
        const got = [bl[k]!, bh[k]!].sort((a, b) => a - b);
        expect(got[0]).toBeCloseTo(lo[k]!, 4);
        expect(got[1]).toBeCloseTo(hi[k]!, 4);
      }
    }
  });

  it("groups equal primitives: few draw calls", () => {
    const s = new CoreScene(models[name]!);
    expect(s.drawCalls).toBeLessThanOrEqual(12);
    expect(s.triangles).toBeGreaterThan(0);
  });

  it("moving a rod moves its instance up by position x travel", () => {
    const m = models[name]!;
    const s = new CoreScene(m);
    const rod = m.primitives.find((p) => p.rod !== undefined)!;
    s.setRodPositions({ [rod.rod!]: 0 });
    const y0 = s.boundsOf(rod.index).min.y;
    s.setRodPositions({ [rod.rod!]: 0.5 });
    expect(s.boundsOf(rod.index).min.y - y0).toBeCloseTo(0.5 * m.rodTravelCm[rod.rod!]!, 4); // float32, see above
    const w = s.where[rod.index]!;
    const mat = new THREE.Matrix4();
    s.groups[w.group]!.mesh.getMatrixAt(w.instance, mat);
    expect(new THREE.Vector3().setFromMatrixPosition(mat).y).toBeCloseTo(rod.center[2] + 0.5 * m.rodTravelCm[rod.rod!]!, 4);
  });

  it("the cutaway clips every material and adds caps for solid materials only", () => {
    const s = new CoreScene(models[name]!);
    s.setCutaway(cutawayHalfSpace({ axis: "x", position: 0, flip: false }));
    for (const g of s.groups) expect((g.mesh.material as THREE.Material).clippingPlanes).toHaveLength(1);
    const caps = s.root.children.filter((o) => o.name.startsWith("cap:")).map((o) => o.name);
    expect(caps).toContain("cap:fuel");
    expect(caps).not.toContain("cap:water");
    s.setCutaway(null);
    for (const g of s.groups) expect((g.mesh.material as THREE.Material).clippingPlanes).toHaveLength(0);
    expect(s.root.children.filter((o) => o.name.startsWith("cap:"))).toHaveLength(0);
  });

  it("the power overlay colours fuel instances only, and clears", () => {
    const m = models[name]!;
    const s = new CoreScene(m);
    const colors = new Map(m.elements.map((id) => [id, [1, 0, 0] as [number, number, number]]));
    s.setElementColors(colors);
    const fuel = s.groups.filter((g) => g.material === "fuel");
    expect(fuel.length).toBeGreaterThan(0);
    const c = new THREE.Color();
    for (const g of fuel) {
      g.mesh.getColorAt(0, c);
      expect([c.r, c.g, c.b]).toEqual([1, 0, 0]);
    }
    for (const g of s.groups.filter((x) => x.material !== "fuel")) expect(g.mesh.instanceColor).toBeNull();
    s.setElementColors(null);
    for (const g of fuel) {
      g.mesh.getColorAt(0, c);
      expect([c.r, c.g, c.b]).toEqual([1, 1, 1]);
    }
  });
});
