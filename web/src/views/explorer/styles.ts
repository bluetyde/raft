/**
 * How the explorer draws each material tag. The library's `material` is a free tag; styling belongs
 * to the viewer (docs/library-format.md section 12). Unknown tags get a neutral grey.
 */

export interface MaterialStyle {
  color: number;
  opacity: number;
  /** Clicks go through it (water surrounds the whole core). */
  pickable: boolean;
  /** Draw a solid cap where the cutaway plane cuts it. */
  capped: boolean;
}

const STYLES: Record<string, MaterialStyle> = {
  fuel: { color: 0xc0873f, opacity: 1, pickable: true, capped: true },
  clad: { color: 0x9aa3ab, opacity: 1, pickable: true, capped: true },
  steel: { color: 0x9aa3ab, opacity: 1, pickable: true, capped: true },
  aluminum: { color: 0xc9ced3, opacity: 1, pickable: true, capped: true },
  graphite: { color: 0x3a3d42, opacity: 1, pickable: true, capped: true },
  b4c: { color: 0x2d2a26, opacity: 1, pickable: true, capped: true },
  water: { color: 0x3f7fbf, opacity: 0.08, pickable: false, capped: false },
  void: { color: 0x000000, opacity: 0, pickable: false, capped: false },
};

const DEFAULT: MaterialStyle = { color: 0x8a8a8a, opacity: 1, pickable: true, capped: true };

export function styleFor(material: string): MaterialStyle {
  return Object.hasOwn(STYLES, material) ? STYLES[material]! : DEFAULT;
}

// Viridis (matplotlib 3.x, CC0), 9 evenly spaced stops, from matplotlib.colormaps['viridis']. Perceptually uniform and colour-blind safe (plan 04).
const VIRIDIS: [number, number, number][] = [
  [0.267, 0.005, 0.329],
  [0.279, 0.175, 0.483],
  [0.23, 0.322, 0.546],
  [0.173, 0.449, 0.558],
  [0.128, 0.567, 0.551],
  [0.158, 0.684, 0.502],
  [0.369, 0.789, 0.383],
  [0.678, 0.864, 0.19],
  [0.993, 0.906, 0.144],
];

/** Viridis at u in [0, 1] (clamped), as sRGB components in [0, 1]. */
export function viridis(u: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, Number.isFinite(u) ? u : 0)) * (VIRIDIS.length - 1);
  const i = Math.min(VIRIDIS.length - 2, Math.floor(x));
  const w = x - i;
  const a = VIRIDIS[i]!;
  const b = VIRIDIS[i + 1]!;
  return [a[0] + w * (b[0] - a[0]), a[1] + w * (b[1] - a[1]), a[2] + w * (b[2] - a[2])];
}
