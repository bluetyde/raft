/**
 * The explorer's view of a library: render primitives (docs/library-format.md section 12), rod travel,
 * and the reference power shape. This adapter keeps the viewer independent of the engine's Library
 * class (TD-07), and a later CSG renderer would read the same model.
 *
 * Coordinates here are the library's: cm, right-handed, z up.
 */

import type { Library } from "../../sim/library";

export type Vec3 = [number, number, number];

export type Primitive =
  | { type: "cylinder"; center: Vec3; radius: number; height: number }
  | { type: "annulus"; center: Vec3; rInner: number; radius: number; height: number }
  | { type: "box"; center: Vec3; size: Vec3 };

export type PrimitiveInfo = Primitive & {
  /** Position in `geometry.primitives`: the stable pick id (primitives have no id field). */
  index: number;
  material: string;
  element?: string;
  rod?: string;
};

export interface ViewerModel {
  libraryId: string;
  primitives: PrimitiveInfo[];
  /** Rod travel in cm, by rod id. A rod primitive moves up by position × travel. */
  rodTravelCm: Record<string, number>;
  /** Reference rod positions (fraction withdrawn). */
  refRods: Record<string, number>;
  elements: string[];
  axialEdgesCm: number[];
  /** Reference shape, [E, A] element-major, sums to 1. */
  baseShape: number[];
}

export function modelFromLibrary(lib: Library): ViewerModel {
  const g = lib.manifest.geometry;
  const primitives: PrimitiveInfo[] = g.primitives.map((p: any, index: number) => ({ ...structuredClone(p), index }));
  const rodTravelCm: Record<string, number> = {};
  for (const r of lib.rods) rodTravelCm[r.id] = r.travelCm;
  const bins = lib.shapes.bins;
  return {
    libraryId: lib.id,
    primitives,
    rodTravelCm,
    refRods: { ...lib.refRods },
    elements: [...bins.elements],
    axialEdgesCm: [...bins.axialEdgesCm],
    baseShape: [...lib.arrays[lib.shapes.base]!],
  };
}

/** Each element's share of the reference power (sum of its axial bins). */
export function elementShares(m: ViewerModel): Map<string, number> {
  const A = m.axialEdgesCm.length - 1;
  const out = new Map<string, number>();
  m.elements.forEach((id, e) => {
    let s = 0;
    for (let a = 0; a < A; a++) s += m.baseShape[e * A + a]!;
    out.set(id, s);
  });
  return out;
}

/** The z offset of a primitive for the given rod positions (0 for primitives that are not rods). */
export function rodOffsetCm(p: PrimitiveInfo, m: ViewerModel, rods: Record<string, number>): number {
  if (p.rod === undefined) return 0;
  const x = Object.hasOwn(rods, p.rod) ? rods[p.rod]! : (m.refRods[p.rod] ?? 0);
  return x * (m.rodTravelCm[p.rod] ?? 0);
}

// ---- exact picking on the analytic primitives ----

/** A half-space kept by the cutaway: points with n·p + c >= 0 stay (the three.js clipping convention). */
export interface HalfSpace {
  normal: Vec3;
  constant: number;
}

export interface PickHit {
  index: number;
  t: number;
  point: Vec3;
  /** True when the ray enters the solid through the cutaway face. */
  onCut: boolean;
}

type Interval = [number, number];

function slab(o: number, d: number, lo: number, hi: number): Interval | null {
  if (Math.abs(d) < 1e-15) return o >= lo && o <= hi ? [-Infinity, Infinity] : null;
  const a = (lo - o) / d;
  const b = (hi - o) / d;
  return a < b ? [a, b] : [b, a];
}

/** Where the ray is inside the infinite z-cylinder of radius r around (cx, cy). */
function radial(o: Vec3, d: Vec3, cx: number, cy: number, r: number): Interval | null {
  const ox = o[0] - cx;
  const oy = o[1] - cy;
  const A = d[0] * d[0] + d[1] * d[1];
  const C = ox * ox + oy * oy - r * r;
  if (A < 1e-15) return C <= 0 ? [-Infinity, Infinity] : null;
  const B = 2 * (ox * d[0] + oy * d[1]);
  const disc = B * B - 4 * A * C;
  if (disc < 0) return null;
  const s = Math.sqrt(disc);
  return [(-B - s) / (2 * A), (-B + s) / (2 * A)];
}

function intersect(a: Interval | null, b: Interval | null): Interval | null {
  if (!a || !b) return null;
  const lo = Math.max(a[0], b[0]);
  const hi = Math.min(a[1], b[1]);
  return lo <= hi ? [lo, hi] : null;
}

/** The parts of the ray inside the solid, as sorted intervals of t. */
export function solidIntervals(p: Primitive, zOffset: number, o: Vec3, d: Vec3): Interval[] {
  const [cx, cy, cz0] = p.center;
  const cz = cz0 + zOffset;
  if (p.type === "box") {
    const [sx, sy, sz] = p.size;
    const i = intersect(
      intersect(slab(o[0], d[0], cx - sx / 2, cx + sx / 2), slab(o[1], d[1], cy - sy / 2, cy + sy / 2)),
      slab(o[2], d[2], cz - sz / 2, cz + sz / 2),
    );
    return i ? [i] : [];
  }
  const z = slab(o[2], d[2], cz - p.height / 2, cz + p.height / 2);
  const outer = intersect(radial(o, d, cx, cy, p.radius), z);
  if (!outer) return [];
  if (p.type === "cylinder") return [outer];
  const hole = radial(o, d, cx, cy, p.rInner);
  if (!hole || hole[1] <= outer[0] || hole[0] >= outer[1]) return [outer];
  const parts: Interval[] = [];
  if (hole[0] > outer[0]) parts.push([outer[0], hole[0]]);
  if (hole[1] < outer[1]) parts.push([hole[1], outer[1]]);
  return parts;
}

function keptInterval(h: HalfSpace, o: Vec3, d: Vec3): Interval | null {
  const no = h.normal[0] * o[0] + h.normal[1] * o[1] + h.normal[2] * o[2] + h.constant;
  const nd = h.normal[0] * d[0] + h.normal[1] * d[1] + h.normal[2] * d[2];
  if (Math.abs(nd) < 1e-15) return no >= 0 ? [-Infinity, Infinity] : null;
  const t = -no / nd;
  return nd > 0 ? [t, Infinity] : [-Infinity, t];
}

/**
 * The first primitive the ray enters, in library coordinates. `pickable` filters materials (water
 * surrounds everything, so the viewer leaves it out). A primitive that contains the ray origin is
 * skipped, so from inside a solid (noclip) you pick what is ahead.
 */
export function pick(
  m: ViewerModel,
  o: Vec3,
  d: Vec3,
  opts: { rods?: Record<string, number>; cut?: HalfSpace | null; pickable?: (p: PrimitiveInfo) => boolean } = {},
): PickHit | null {
  const kept = opts.cut ? keptInterval(opts.cut, o, d) : ([-Infinity, Infinity] as Interval);
  if (!kept) return null;
  let best: PickHit | null = null;
  for (const p of m.primitives) {
    if (opts.pickable && !opts.pickable(p)) continue;
    const zOff = rodOffsetCm(p, m, opts.rods ?? {});
    for (const iv of solidIntervals(p, zOff, o, d)) {
      const v = intersect(iv, kept);
      if (!v || v[0] < 0) continue; // behind, or the origin is inside
      if (v[1] - v[0] < 1e-9) continue; // grazing
      if (!best || v[0] < best.t) {
        best = { index: p.index, t: v[0], point: [o[0] + v[0] * d[0], o[1] + v[0] * d[1], o[2] + v[0] * d[2]], onCut: v[0] > iv[0] };
      }
      break; // intervals are sorted; the first kept one is the entry
    }
  }
  return best;
}
