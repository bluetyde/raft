/**
 * The fault commands the instructor view can send (docs/m6-instructor-design.md, D3 and amendment 2).
 * Only faults that the engine has today. The others wait for the engine (request D3a in docs/cloud-notes.md).
 */

import { PCM } from "./truth";

export type InstrumentFaultKind = "stuck" | "dead" | "clear";

export function instrumentFault(instrument: string, kind: InstrumentFaultKind): Record<string, unknown> {
  return { type: "fault.instrument", instrument, kind };
}

/** A reactivity insertion. There is no clear: the engine does not have one yet (amendment 2). */
export function reactivityFault(pcm: number): Record<string, unknown> {
  if (!Number.isFinite(pcm) || pcm === 0) throw new Error("the inserted reactivity must be a finite, non-zero number of pcm");
  return { type: "fault.reactivity", deltaRho: pcm * PCM };
}

/** A pump trip (on = false) or a pump restart (on = true). */
export function pumpFault(pump: string, on: boolean): Record<string, unknown> {
  return { type: "pump.set", pump, on };
}

/** Faults in plan 06 that the engine does not have yet. The panel lists them as not available. */
export const WAITING_FOR_ENGINE = [
  "rod stuck (will not move)",
  "rod will not scram",
  "rod drop",
  "instrument drift",
  "clear of inserted reactivity",
];

/** A short label for the timeline. */
export function faultLabel(cmd: Record<string, any>): string {
  if (cmd["type"] === "fault.instrument") return `${cmd["instrument"]}: ${cmd["kind"]}`;
  if (cmd["type"] === "fault.reactivity") return `reactivity ${(Number(cmd["deltaRho"]) / PCM).toFixed(1)} pcm`;
  if (cmd["type"] === "pump.set") return `pump ${cmd["pump"]} ${cmd["on"] ? "on" : "off"}`;
  return String(cmd["type"]);
}
