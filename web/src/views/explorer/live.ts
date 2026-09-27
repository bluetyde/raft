/**
 * M4: from runtime snapshots to what the explorer draws. Pure functions, tested in Node.
 * The explorer may show truth (ARCHITECTURE: only the explorer and instructor read `truth`).
 */

import { viridis } from "./styles";

/** Rod positions (fraction withdrawn) from a snapshot. */
export function rodPositionsFrom(snapshot: Record<string, any>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [id, r] of Object.entries<any>(snapshot.truth?.rods ?? {})) out[id] = r.position;
  return out;
}

/**
 * Power per element (W): the live shape ([E, A], element-major, as the runtime sends it) summed over
 * the axial bins, times the total power. The shape's total is normalized first, so a rounding drift
 * in the interpolated shape does not change the total.
 */
export function elementPowers(shape: ArrayLike<number>, elements: string[], axialBins: number, power: number): Map<string, number> {
  const E = elements.length;
  if (shape.length !== E * axialBins) {
    throw new RangeError(`shape has ${shape.length} values, expected ${E} x ${axialBins}`);
  }
  let total = 0;
  for (let i = 0; i < shape.length; i++) total += shape[i]!;
  const out = new Map<string, number>();
  for (let e = 0; e < E; e++) {
    let s = 0;
    for (let a = 0; a < axialBins; a++) s += shape[e * axialBins + a]!;
    out.set(elements[e]!, total > 0 ? (s / total) * power : 0);
  }
  return out;
}

/** Colours for element powers: viridis, scaled to the hottest element (so the pattern shows at any power). */
export function powerColors(powers: Map<string, number>): Map<string, [number, number, number]> {
  let max = 0;
  for (const v of powers.values()) max = Math.max(max, v);
  const out = new Map<string, [number, number, number]>();
  for (const [id, v] of powers) out.set(id, viridis(max > 0 ? v / max : 0));
  return out;
}

const PREFIXES: [number, string][] = [
  [1e9, "G"],
  [1e6, "M"],
  [1e3, "k"],
  [1, ""],
  [1e-3, "m"],
  [1e-6, "µ"],
  [1e-9, "n"],
];

/** A power in W with an SI prefix and 3 significant digits, for display only (ARCHITECTURE: units convert in one place). */
export function formatPower(w: number): string {
  if (!Number.isFinite(w)) return String(w);
  if (w === 0) return "0 W";
  const a = Math.abs(w);
  for (const [scale, p] of PREFIXES) {
    if (a >= scale) return `${(w / scale).toPrecision(3)} ${p}W`;
  }
  return `${w.toExponential(2)} W`;
}

/** A reactor period in s for display: "∞" when steady (the engine sends null or a non-finite value). */
export function formatPeriod(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s) || Math.abs(s) > 1e6) return "∞";
  return `${s.toPrecision(3)} s`;
}
