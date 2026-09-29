/**
 * Instructor scripts: an uploaded file of timed events ("instrument stuck at 5 minutes, pump trip at 12").
 * The runtime turns each event into an engine command at its step boundary, logged as a command from
 * "script", so a script run replays like any other session. A script needs no model and no scenario.
 *
 * Only faults the engine can model are accepted. Ones it cannot (LOCA, pipe or steamline break) are refused
 * by name with a plain message, never silently dropped.
 */

import { validateCommand } from "../contracts/validate";
import type { Issue } from "../library/validate";
import type { Library } from "../sim/library";
import { dueStep } from "./scenario";

export const SCRIPT_FORMAT = "virtual-reactor-instructor-script";
export const SCRIPT_VERSION = 1;
export const MAX_SCRIPT_EVENTS = 200;

/** Accidents the engine has no model for, with what to use in the meantime. */
export const UNSUPPORTED_ACTIONS: Record<string, string> = {
  loca: "the engine has no coolant-inventory model, so a LOCA cannot be simulated; a pump.trip (loss of flow) is the nearest supported fault",
  "pipe.burst": "the engine has no piping model, so a pipe burst cannot be simulated; a pump.trip (loss of flow) is the nearest supported fault",
  "steamline.break": "the engine has no secondary-side model, so a steamline break cannot be simulated; a reactivity.step models the cooldown's reactivity gain",
};

/** Faults the engine implements but the command contract does not list yet: refused until the schema has them. */
const NOT_IN_CONTRACT = "the engine has it, but the command contract (schema/command.schema.json) does not list it yet; add it there first";
for (const a of ["instrument.drift", "rod.stuck", "rod.drop", "rod.no-scram", "rod.clear", "reactivity.clear"]) UNSUPPORTED_ACTIONS[a] = NOT_IN_CONTRACT;

export interface ScriptEvent {
  /** Simulation time, from `atSeconds` or `atMinutes`. */
  atSeconds?: number;
  atMinutes?: number;
  action: string;
  note?: string;
  [param: string]: unknown;
}

export interface ScriptFile {
  format: typeof SCRIPT_FORMAT;
  version: number;
  name?: string;
  events: ScriptEvent[];
}

/** One event ready for the runtime: the engine step it is due at and the command to submit. */
export interface PreparedScriptEvent {
  step: number;
  t: number;
  cmd: Record<string, unknown>;
  note: string;
}

export interface PreparedScript {
  name: string;
  events: PreparedScriptEvent[];
}

const issue = (code: string, path: string, message: string): Issue => ({ code, path, message }) as Issue;

/** action -> command builder; `null` means the params are invalid (already reported). */
type Builder = (ev: ScriptEvent, lib: Library, path: string, out: Issue[]) => Record<string, unknown> | null;

const needString = (ev: ScriptEvent, key: string, path: string, out: Issue[], known: (id: string) => boolean, what: string): string | null => {
  const v = ev[key];
  if (typeof v !== "string" || !known(v)) {
    out.push(issue("E_SCRIPT_PARAM", `${path}/${key}`, `${key} must name a ${what} in the library${typeof v === "string" ? ` (no ${what} "${v}")` : ""}`));
    return null;
  }
  return v;
};

const instrumentFault = (kind: string): Builder => (ev, lib, path, out) => {
  const instrument = needString(ev, "instrument", path, out, (id) => lib.instruments.some((i: any) => i.id === id), "instrument");
  return instrument ? { type: "fault.instrument", instrument, kind } : null;
};

const BUILDERS: Record<string, Builder> = {
  "instrument.stuck": instrumentFault("stuck"),
  "instrument.dead": instrumentFault("dead"),
  "instrument.clear": instrumentFault("clear"),
  "reactivity.step": (ev, _lib, path, out) => {
    const d = ev["deltaRho"];
    if (typeof d !== "number" || !Number.isFinite(d) || d === 0) {
      out.push(issue("E_SCRIPT_PARAM", `${path}/deltaRho`, "deltaRho must be a non-zero number"));
      return null;
    }
    return { type: "fault.reactivity", deltaRho: d };
  },
  "pump.trip": (ev, lib, path, out) => {
    const pump = needString(ev, "pump", path, out, (id) => lib.pumps.includes(id), "pump");
    return pump ? { type: "pump.set", pump, on: false } : null;
  },
  "pump.start": (ev, lib, path, out) => {
    const pump = needString(ev, "pump", path, out, (id) => lib.pumps.includes(id), "pump");
    return pump ? { type: "pump.set", pump, on: true } : null;
  },
  scram: () => ({ type: "scram" }),
};

export const SCRIPT_ACTIONS = Object.keys(BUILDERS);

/** The time of one event in seconds, or null (reported). */
function eventTime(ev: ScriptEvent, path: string, out: Issue[]): number | null {
  const s = ev.atSeconds;
  const m = ev.atMinutes;
  if ((s === undefined) === (m === undefined)) {
    out.push(issue("E_SCRIPT_TIME", path, "give exactly one of atSeconds or atMinutes"));
    return null;
  }
  const t = s !== undefined ? s : (m as number) * 60;
  if (typeof t !== "number" || !Number.isFinite(t) || t < 0) {
    out.push(issue("E_SCRIPT_TIME", `${path}/${s !== undefined ? "atSeconds" : "atMinutes"}`, "the time must be a number >= 0"));
    return null;
  }
  return t;
}

/** Check a script against the library it will run on. An empty list means it is valid. */
export function validateScript(obj: unknown, lib: Library): Issue[] {
  const out: Issue[] = [];
  const f = obj as ScriptFile;
  if (typeof f !== "object" || f === null) return [issue("E_SCRIPT_FIELD", "", "a script must be an object")];
  if (f.format !== SCRIPT_FORMAT || f.version !== SCRIPT_VERSION) {
    out.push(issue("E_SCRIPT_FIELD", "/format", `not a ${SCRIPT_FORMAT} file, version ${SCRIPT_VERSION}`));
  }
  if (!Array.isArray(f.events) || f.events.length === 0) {
    out.push(issue("E_SCRIPT_EVENTS", "/events", "events must be a non-empty array"));
    return out;
  }
  if (f.events.length > MAX_SCRIPT_EVENTS) {
    out.push(issue("E_SCRIPT_EVENTS", "/events", `a script holds at most ${MAX_SCRIPT_EVENTS} events`));
    return out;
  }
  for (const [i, ev] of f.events.entries()) {
    const path = `/events/${i}`;
    if (typeof ev !== "object" || ev === null) {
      out.push(issue("E_SCRIPT_EVENT", path, "an event must be an object"));
      continue;
    }
    eventTime(ev, path, out);
    if (typeof ev.action !== "string") {
      out.push(issue("E_SCRIPT_ACTION", `${path}/action`, "action must be a string"));
    } else if (Object.hasOwn(UNSUPPORTED_ACTIONS, ev.action)) {
      out.push(issue("E_SCRIPT_UNSUPPORTED", `${path}/action`, UNSUPPORTED_ACTIONS[ev.action]!));
    } else if (!Object.hasOwn(BUILDERS, ev.action)) {
      out.push(issue("E_SCRIPT_ACTION", `${path}/action`, `unknown action "${ev.action}"; use one of ${SCRIPT_ACTIONS.join(", ")}`));
    } else {
      const cmd = BUILDERS[ev.action]!(ev, lib, path, out);
      // the engine takes some commands the command contract does not list; a script sticks to the contract
      if (cmd && validateCommand(cmd).length > 0) {
        out.push(issue("E_SCRIPT_CONTRACT", `${path}/action`, `"${ev.action}" is not in the command contract (schema/command.schema.json) yet`));
      }
    }
  }
  return out;
}

export class ScriptError extends Error {
  constructor(readonly issues: Issue[]) {
    super(issues.slice(0, 5).map((i) => `${i.code} ${i.path}: ${i.message}`).join("; "));
    this.name = "ScriptError";
  }
}

/** Validate and convert a script for a session with outer step `outerDt`. Throws ScriptError. */
export function prepareScript(obj: unknown, lib: Library, outerDt: number): PreparedScript {
  const issues = validateScript(obj, lib);
  if (issues.length > 0) throw new ScriptError(issues);
  const f = obj as ScriptFile;
  const events: PreparedScriptEvent[] = f.events.map((ev, i) => {
    const t = eventTime(ev, `/events/${i}`, [])!;
    const cmd = BUILDERS[ev.action]!(ev, lib, `/events/${i}`, [])!;
    const step = dueStep(t, outerDt);
    return { step, t: step * outerDt, cmd, note: ev.note ?? `${ev.action}` };
  });
  // stable: events at the same time keep the file's order
  events.sort((a, b) => a.step - b.step);
  return { name: f.name ?? "script", events };
}
