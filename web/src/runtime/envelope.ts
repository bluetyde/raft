/**
 * The supported operating envelope of a lesson, and the validity warnings a window shows.
 *
 * A scenario may carry an `envelope`: the region the lesson is meant for. Every limit comes from the library
 * (`fromTrip`) or carries a `source`, like every other threshold in a scenario (docs/m5-scenarios-design.md, D5).
 * The runtime checks each snapshot against it and against the engine's own validity status (library-format
 * section 13), and turns both into one plain-language view with a level:
 *   ok       supported, inside the envelope
 *   caution  inside the envelope (or none), but the model is not validated for this state
 *   warning  outside the data range or outside the lesson's envelope
 */

import type { Issue } from "../library/validate";
import type { Library } from "../sim/library";

export interface EnvelopeSpec {
  /** One line: what the lesson is and what it is not. */
  summary: string;
  /** Highest power, as a multiple of a trip setpoint from the library. */
  power?: { fromTrip: string; times: number; source: string };
  /** Highest fuel temperature (K). */
  fuelTemp?: { max: number; source: string };
  /** Allowed engine modes (`truth.mode`), for example ["steady"]: no pulses. */
  modes?: string[];
  /** Where the model is known to disagree with measurement, in plain words, each with its source. Always shown. */
  knownLimits?: { text: string; source: string }[];
}

export interface ResolvedEnvelope {
  summary: string;
  powerMaxW: number | null;
  powerSource: string | null;
  fuelTempMaxK: number | null;
  fuelTempSource: string | null;
  modes: string[] | null;
  knownLimits: string[];
}

export interface ValidityView {
  level: "ok" | "caution" | "warning";
  /** The engine's status for the library and rod state. */
  library: string;
  /** Inside, outside, or "none" when the scenario has no envelope. */
  envelope: "inside" | "outside" | "none";
  /** What the lesson is, from the envelope. */
  summary: string | null;
  /** Plain-language reasons, most serious first. */
  messages: string[];
}

const issue = (code: string, path: string, message: string): Issue => ({ code, path, message });

const tripValue = (lib: Library, id: string): number | null => {
  const t = (lib.trips as any[]).find((x) => x.id === id);
  const v = t?.predicate?.value;
  return typeof v === "number" ? v : null;
};

export function validateEnvelope(env: unknown, lib: Library): Issue[] {
  const out: Issue[] = [];
  const e = env as EnvelopeSpec;
  if (typeof e !== "object" || e === null) return [issue("E_SCN_ENVELOPE", "/envelope", "the envelope must be an object")];
  if (typeof e.summary !== "string" || e.summary.trim() === "") out.push(issue("E_SCN_ENVELOPE", "/envelope/summary", "a summary is needed"));
  const sourced = (o: { source?: unknown } | undefined, p: string) => {
    if (!(typeof o?.source === "string" && o.source.trim())) out.push(issue("E_SCN_SOURCE", `${p}/source`, "an envelope limit needs a source"));
  };
  if (e.power !== undefined) {
    if (typeof e.power.fromTrip !== "string" || tripValue(lib, e.power.fromTrip) === null) {
      out.push(issue("E_SCN_ENVELOPE", "/envelope/power/fromTrip", `the library has no trip "${String(e.power.fromTrip)}" with a setpoint`));
    }
    if (!(typeof e.power.times === "number" && Number.isFinite(e.power.times) && e.power.times > 0)) {
      out.push(issue("E_SCN_ENVELOPE", "/envelope/power/times", "times must be a positive number"));
    }
    sourced(e.power, "/envelope/power");
  }
  if (e.fuelTemp !== undefined) {
    if (!(typeof e.fuelTemp.max === "number" && Number.isFinite(e.fuelTemp.max) && e.fuelTemp.max > 0)) {
      out.push(issue("E_SCN_ENVELOPE", "/envelope/fuelTemp/max", "max must be a positive temperature in K"));
    }
    sourced(e.fuelTemp, "/envelope/fuelTemp");
  }
  for (const [i, k] of (e.knownLimits ?? []).entries()) {
    if (typeof k?.text !== "string" || k.text.trim() === "") out.push(issue("E_SCN_ENVELOPE", `/envelope/knownLimits/${i}/text`, "a known limit needs its text"));
    sourced(k, `/envelope/knownLimits/${i}`);
  }
  if (e.modes !== undefined && !(Array.isArray(e.modes) && e.modes.length > 0 && e.modes.every((m) => typeof m === "string"))) {
    out.push(issue("E_SCN_ENVELOPE", "/envelope/modes", "modes must be a non-empty list of mode names"));
  }
  return out;
}

export function resolveEnvelope(e: EnvelopeSpec, lib: Library): ResolvedEnvelope {
  const sp = e.power ? tripValue(lib, e.power.fromTrip) : null;
  return {
    summary: e.summary,
    powerMaxW: e.power && sp !== null ? sp * e.power.times : null,
    powerSource: e.power ? `${e.power.times * 100}% of the ${e.power.fromTrip} setpoint (${e.power.source})` : null,
    fuelTempMaxK: e.fuelTemp ? e.fuelTemp.max : null,
    fuelTempSource: e.fuelTemp ? e.fuelTemp.source : null,
    modes: e.modes ?? null,
    knownLimits: (e.knownLimits ?? []).map((k) => k.text),
  };
}

const LIBRARY_TEXT: Record<string, string> = {
  R_LIBRARY_EXPERIMENTAL: "The model is experimental: it has not been checked against measured reactor data yet.",
  R_LIBRARY_SYNTHETIC: "This is a synthetic teaching library, not a real reactor.",
  R_JOINT_UNCHECKED:
    "Several rods are away from their reference positions together, in a combination not checked against full transport runs. The rod worths are added as if the rods did not affect each other.",
  R_DOMAIN_TFUEL: "Fuel temperature is outside the range the data covers.",
  R_DOMAIN_TCOOLANT: "Coolant temperature is outside the range the data covers.",
  R_DOMAIN_XENON: "Xenon is outside the range the data covers.",
};

export function describeReason(code: string): string {
  if (LIBRARY_TEXT[code]) return LIBRARY_TEXT[code]!;
  if (code.startsWith("R_DOMAIN_ROD_")) return `The ${code.slice("R_DOMAIN_ROD_".length)} rod is outside the range the data covers.`;
  return code;
}

const watts = (w: number) => `${w.toExponential(2)} W`;

/** Combine the engine's validity with the lesson's envelope into the view a window shows. */
export function evaluateValidity(
  validity: { status: string; reasons: string[] } | undefined,
  env: ResolvedEnvelope | null,
  s: { power: number; fuelTemp: number; mode: string },
): ValidityView {
  const library = validity?.status ?? "unknown";
  const outside: string[] = [];
  if (env) {
    if (env.powerMaxW !== null && s.power > env.powerMaxW) {
      outside.push(`Power ${watts(s.power)} is above this lesson's limit of ${watts(env.powerMaxW)}.`);
    }
    if (env.fuelTempMaxK !== null && s.fuelTemp > env.fuelTempMaxK) {
      outside.push(`Fuel temperature ${s.fuelTemp.toFixed(0)} K is above this lesson's limit of ${env.fuelTempMaxK} K.`);
    }
    if (env.modes !== null && !env.modes.includes(s.mode)) {
      outside.push(`The reactor is in ${s.mode} mode; this lesson covers ${env.modes.join(", ")} operation only.`);
    }
  }
  const reasons = (validity?.reasons ?? []).map(describeReason);
  const outOfData = library === "outOfDomain";
  const known = env?.knownLimits ?? [];
  const level: ValidityView["level"] = outOfData || outside.length > 0 ? "warning" : library === "supported" && known.length === 0 ? "ok" : "caution";
  return {
    level,
    library,
    envelope: env ? (outside.length > 0 ? "outside" : "inside") : "none",
    summary: env?.summary ?? null,
    // the lesson's own limits first, then where the model disagrees with measurement, then the data range, then the model's general status
    messages: [...outside, ...known, ...reasons.filter((_, i) => (validity!.reasons[i] ?? "").startsWith("R_DOMAIN")), ...reasons.filter((_, i) => !(validity!.reasons[i] ?? "").startsWith("R_DOMAIN"))],
  };
}
