/**
 * Meters built from the library's instruments (plan 05: the panel is driven by the library).
 * The role comes from the instrument's signal; the label is its id.
 */

export type MeterRole = "power" | "fuelTemp" | "coolantTemp" | "other";

export interface InstrumentSpec {
  id: string;
  signal: string;
  scale: "linear" | "log";
  range: [number, number];
  lag: number;
  noise: number;
}

export interface Meter {
  id: string;
  role: MeterRole;
  scale: "linear" | "log";
  range: [number, number];
}

export function roleOf(signal: string): MeterRole {
  if (signal === "truth.power") return "power";
  if (signal === "truth.fuelTemp") return "fuelTemp";
  if (signal === "truth.coolantTemp") return "coolantTemp";
  return "other";
}

export function metersFrom(instruments: InstrumentSpec[]): Meter[] {
  return instruments.map((i) => ({ id: i.id, role: roleOf(i.signal), scale: i.scale, range: [i.range[0], i.range[1]] }));
}

export type Peg = "over" | "under" | null;

export interface MeterReading {
  /** Needle position in [0, 1]. */
  fraction: number;
  peg: Peg;
  failed: boolean;
}

/** Where the needle sits. Readings outside the range peg the meter at its end; a null reading is a failed instrument. */
export function meterReading(m: Meter, v: number | null | undefined): MeterReading {
  if (v === null || v === undefined || !Number.isFinite(v)) return { fraction: 0, peg: null, failed: true };
  const [lo, hi] = m.range;
  const peg: Peg = v >= hi ? "over" : v <= lo ? "under" : null;
  let f: number;
  if (m.scale === "log") {
    const a = Math.log10(lo);
    const b = Math.log10(hi);
    f = v > 0 ? (Math.log10(v) - a) / (b - a) : 0;
  } else {
    f = (v - lo) / (hi - lo);
  }
  return { fraction: Math.min(1, Math.max(0, f)), peg, failed: false };
}

/** True when the reading is outside the instrument's range (the meter is pegged). */
export function isPegged(m: Meter, v: number | null | undefined): boolean {
  return v !== null && v !== undefined && Number.isFinite(v) && (v >= m.range[1] || v <= m.range[0]);
}

/** Kelvin to degrees Celsius, for display only (ARCHITECTURE conventions: convert in one place). */
export function kelvinToCelsius(k: number): number {
  return k - 273.15;
}

export function unitOf(role: MeterRole): string {
  return role === "power" ? "W" : role === "fuelTemp" || role === "coolantTemp" ? "°C" : "";
}
