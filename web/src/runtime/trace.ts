/**
 * CSV traces of a session (docs/m6-instructor-design.md, D6a). The session is replayed from step 0,
 * and one row is written at step 0 and then every `everyS` of sim time (at least every step).
 * Replay is deterministic, so the rows equal what a step-by-step run shows at those steps.
 */

import { Engine } from "../sim/engine";
import type { Library } from "../sim/library";
import { replayCommands } from "./history";
import type { SessionFile } from "./protocol";

const TRUTH = ["power", "period", "fuelTemp", "coolantTemp", "iodine", "xenon"] as const;
const RHO = ["total", "reference", "calibration", "rods", "fuel", "coolant", "xenon", "fault"] as const;

function cell(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "1" : "0";
  if (typeof v === "number") {
    if (Number.isNaN(v)) return "nan";
    if (!Number.isFinite(v)) return v > 0 ? "inf" : "-inf";
    return String(v); // shortest text that reads back to the same number
  }
  const text = String(v);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function traceHeader(lib: Library): string[] {
  return [
    "t",
    ...lib.instruments.map((i: { id: string }) => `indicated.${i.id}`),
    ...TRUTH.map((k) => `truth.${k}`),
    ...RHO.map((k) => `reactivity.${k}`),
    "tripped",
    "mode",
  ];
}

export function traceRow(lib: Library, s: Record<string, any>): string[] {
  return [
    cell(s.t),
    ...lib.instruments.map((i: { id: string }) => cell(s.indicated[i.id])),
    ...TRUTH.map((k) => cell(s.truth[k])),
    ...RHO.map((k) => cell(s.truth.reactivity[k])),
    cell(s.tripped),
    cell(s.truth.mode),
  ];
}

/** The steps a trace samples: 0, then every round(everyS / outerDt) steps (at least 1), up to endStep. */
export function sampleEvery(everyS: number, outerDt: number): number {
  if (!(everyS > 0)) throw new RangeError("the sample interval must be > 0");
  return Math.max(1, Math.round(everyS / outerDt));
}

export function traceCsv(lib: Library, file: SessionFile, everyS = 0.1): string {
  const s = file.session;
  const e = new Engine(lib, s.init, s.seed, s.pins.config);
  const every = sampleEvery(everyS, e.config.outerDt);
  const lines = [traceHeader(lib).join(","), traceRow(lib, e.snapshot(false)).join(",")];
  replayCommands(e, s.commands, file.endStep, (x) => {
    if (x.stepIndex % every === 0) lines.push(traceRow(lib, x.snapshot(false)).join(","));
  });
  return lines.join("\n") + "\n";
}
