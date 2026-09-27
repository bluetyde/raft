/**
 * Time settings of the instructor view (docs/m6-instructor-design.md, D5 and amendment 1).
 * The outer step is fixed per session, so the instructor picks it when a session starts.
 */

import { isCoarse } from "../../runtime/protocol";

export interface OuterStep {
  id: "fine" | "coarse";
  outerDt: number;
  label: string;
}

export const OUTER_STEPS: OuterStep[] = [
  { id: "fine", outerDt: 0.01, label: "fine (10 ms): pulses allowed" },
  { id: "coarse", outerDt: 1, label: "coarse (1 s): no pulses, up to 3600×" },
];

/** The rates a session can offer. C6 measured about 150× (steady) at 10 ms and 11 000× or more (steady) at 1 s, on one core. */
export function ratesFor(outerDt: number): number[] {
  return isCoarse(outerDt) ? [1, 10, 60, 600, 3600] : [0.1, 1, 10, 30, 100];
}

/** The outer step as the time bar shows it, for example "10 ms (fine)" or "1 s (coarse)". */
export function formatOuterStep(outerDt: number): string {
  const text = outerDt < 1 ? `${+(outerDt * 1000).toPrecision(6)} ms` : `${+outerDt.toPrecision(6)} s`;
  return `${text} (${isCoarse(outerDt) ? "coarse" : "fine"})`;
}
