/**
 * Scenarios (docs/m5-scenarios-design.md): the format, its validator, and the goal tracker.
 * A scenario is a teaching unit: a library, a start state, allowed controls, scripted events and goals.
 * The runtime runs it (runtime.ts). This file has no Worker or DOM code, so the tests use it directly.
 */

import { validateCommand } from "../contracts/validate";
import { sha256Hex } from "../library/platform";
import type { Issue } from "../library/validate";
import { Engine, evalPredicate } from "../sim/engine";
import type { Library } from "../sim/library";
import { isCoarse } from "./protocol";

export const SCENARIO_FORMAT = "virtual-reactor-scenario";
export const SCENARIO_VERSION = 1;

/** The engine's command types (schema/command.schema.json). */
export const COMMAND_TYPES = [
  "rod.move",
  "rod.fire",
  "mode.set",
  "pump.set",
  "scram",
  "trip.reset",
  "fault.instrument",
  "fault.reactivity",
] as const;

/** The outer steps a scenario may use: fine (pulses allowed) and coarse (M6 D5). */
export const SCENARIO_OUTER_DTS = [0.01, 1];

const OPS = ["eq", "ne", "between", "gt", "ge", "lt", "le", "absGt"];
const TRUTH_SIGNALS = ["truth.power", "truth.fuelTemp", "truth.coolantTemp", "truth.xenon", "truth.mode", "truth.period"];

/** A leaf of a goal check: the library's predicate leaf, or a threshold taken from a trip setpoint. */
export type Check =
  | { all: Check[] }
  | { any: Check[] }
  | { not: Check }
  | { signal: string; op: string; value?: unknown; fromTrip?: string; times?: number | [number, number] };

export interface ScenarioGoal {
  id: string;
  text: string;
  check: Check;
  /** The check must hold this long without a break (s of sim time). Default: one step. */
  for?: number;
  /** The goal opens only when this earlier goal is met. */
  after?: string;
  /** The goal fails if it is not met this long after it opens (s). */
  within?: number;
  /** Where the goal's plain numbers come from (D5). */
  source?: string;
}

export interface ScenarioEvent {
  at: number;
  cmd: Record<string, unknown>;
  note?: string;
  source?: string;
}

export interface ScenarioFile {
  format: typeof SCENARIO_FORMAT;
  version: number;
  id: string;
  library: string;
  title: string;
  brief?: string;
  outerDt: number;
  seed?: number;
  init: Record<string, any> & { rods?: "reference" | "shutdown" | Record<string, number>; source?: string };
  controls: { allow: string[] };
  faultsVisible?: boolean;
  expectTrips?: string[];
  events?: ScenarioEvent[];
  goals: ScenarioGoal[];
  hints?: string[];
}

/** A goal whose check has only plain values (the `fromTrip` thresholds resolved). */
export interface ResolvedGoal extends Omit<ScenarioGoal, "check"> {
  check: Check;
}

/** A validated scenario, ready for a library. */
export interface PreparedScenario {
  file: ScenarioFile;
  /** SHA-256 of the scenario's canonical JSON. The session file pins it. */
  digest: string;
  /** The engine's `init` (rod presets resolved, `source` notes removed). */
  init: Record<string, any>;
  seed: number;
  outerDt: number;
  goals: ResolvedGoal[];
  /** The resolved `fromTrip` thresholds, by "goalId/leaf" (amendment 2: recorded in the session file). */
  thresholds: Record<string, number | [number, number]>;
  /** Each event with the engine step it is due at (the first boundary at or after `at`). */
  events: { step: number; cmd: Record<string, unknown>; note: string }[];
}

type Leaf = Extract<Check, { signal: string }>;

function issue(code: string, path: string, message: string): Issue {
  return { code, path, message };
}

/** The first step boundary at or after `at` seconds. */
export function dueStep(at: number, outerDt: number): number {
  return Math.max(0, Math.ceil(at / outerDt - 1e-9));
}

/** A trip's setpoint: the value of a simple predicate, or the one non-zero bound of an `all` (for example period-short: `gt 0`, `lt 3`). */
export function tripSetpoint(lib: Library, id: string): number | null {
  const trip = lib.trips.find((x: any) => x.id === id) as any;
  if (!trip) return null;
  const p = trip.predicate;
  if (typeof p?.value === "number") return p.value;
  if (Array.isArray(p?.all)) {
    const bounds = p.all.filter((x: any) => typeof x?.value === "number" && x.value !== 0);
    if (bounds.length === 1) return bounds[0].value;
  }
  return null;
}

function leaves(c: Check, path: string, out: { leaf: Leaf; path: string }[] = []): { leaf: Leaf; path: string }[] {
  if ("all" in c) c.all.forEach((x, i) => leaves(x, `${path}/all/${i}`, out));
  else if ("any" in c) c.any.forEach((x, i) => leaves(x, `${path}/any/${i}`, out));
  else if ("not" in c) leaves(c.not, `${path}/not`, out);
  else out.push({ leaf: c, path });
  return out;
}

function isCheck(c: unknown): c is Check {
  if (typeof c !== "object" || c === null) return false;
  const o = c as Record<string, unknown>;
  if (Array.isArray(o["all"])) return o["all"].every(isCheck);
  if (Array.isArray(o["any"])) return o["any"].every(isCheck);
  if ("not" in o) return isCheck(o["not"]);
  return typeof o["signal"] === "string" && typeof o["op"] === "string";
}

function isNumberPair(v: unknown): v is [number, number] {
  return Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === "number" && Number.isFinite(x));
}

/** The engine's `init` for a scenario: rod presets resolved (amendment 1), `source` notes removed. */
export function engineInit(file: ScenarioFile, lib: Library): Record<string, any> {
  const { source: _s, rods, power, ...rest } = file.init ?? {};
  const init: Record<string, any> = { ...rest };
  if (rods === "reference") init["rods"] = { ...lib.refRods };
  else if (rods === "shutdown") init["rods"] = Object.fromEntries(lib.rods.map((r) => [r.id, 0]));
  else if (rods !== undefined) init["rods"] = { ...rods };
  if (power !== undefined) {
    const { source: _p, ...p } = power as Record<string, unknown>;
    init["power"] = p;
  }
  return init;
}

/** Check a scenario against the library it names. An empty list means it is valid. */
export function validateScenario(obj: unknown, lib: Library): Issue[] {
  const out: Issue[] = [];
  const f = obj as ScenarioFile;
  if (typeof f !== "object" || f === null) return [issue("E_SCN_FIELD", "", "a scenario must be an object")];
  if (f.format !== SCENARIO_FORMAT || f.version !== SCENARIO_VERSION) {
    out.push(issue("E_SCN_FIELD", "/format", `not a ${SCENARIO_FORMAT} file, version ${SCENARIO_VERSION}`));
  }
  if (typeof f.id !== "string" || !/^[a-z0-9-]+$/.test(f.id)) out.push(issue("E_SCN_FIELD", "/id", "id must be [a-z0-9-]+"));
  if (typeof f.title !== "string" || f.title.trim() === "") out.push(issue("E_SCN_FIELD", "/title", "a title is needed"));
  if (f.library !== lib.id) out.push(issue("E_SCN_FIELD", "/library", `the scenario is for ${String(f.library)}, not ${lib.id}`));
  if (!SCENARIO_OUTER_DTS.includes(f.outerDt)) {
    out.push(issue("E_SCN_COARSE", "/outerDt", `outerDt must be one of ${SCENARIO_OUTER_DTS.join(", ")}`));
  }
  const coarse = typeof f.outerDt === "number" && isCoarse(f.outerDt);
  if (f.seed !== undefined && !Number.isInteger(f.seed)) out.push(issue("E_SCN_FIELD", "/seed", "seed must be an integer"));
  const tripIds = new Set(lib.trips.map((t: any) => t.id as string));
  for (const [i, t] of (f.expectTrips ?? []).entries()) {
    if (t !== "manual" && !tripIds.has(t)) out.push(issue("E_SCN_FIELD", `/expectTrips/${i}`, `unknown trip ${String(t)}`));
  }

  // init (amendment 1)
  const init = f.init;
  if (typeof init !== "object" || init === null) out.push(issue("E_SCN_INIT", "/init", "init must be an object"));
  else {
    const rods = init.rods;
    if (rods !== undefined && rods !== "reference" && rods !== "shutdown") {
      if (typeof rods !== "object" || rods === null) out.push(issue("E_SCN_ROD", "/init/rods", 'rods must be "reference", "shutdown" or per-rod values'));
      else {
        for (const id of Object.keys(rods)) {
          if (!lib.rods.some((r) => r.id === id)) out.push(issue("E_SCN_ROD", `/init/rods/${id}`, `unknown rod ${id}`));
        }
      }
    }
    const levels = [init.Tfuel, init.Tcoolant, init.power?.value, init.poisons?.I, init.poisons?.X].some((v) => v !== undefined);
    if (levels && !(typeof init.source === "string" && init.source.trim())) {
      out.push(issue("E_SCN_SOURCE", "/init/source", "init has a level (power, temperature or poisons), so it needs a source"));
    }
    if (coarse && init.mode === "pulse") out.push(issue("E_SCN_COARSE", "/init/mode", "a coarse scenario cannot start in pulse mode"));
    if (!out.some((x) => x.code === "E_SCN_ROD")) {
      try {
        new Engine(lib, engineInit(f, lib), Number.isInteger(f.seed) ? f.seed : 1, { outerDt: SCENARIO_OUTER_DTS.includes(f.outerDt) ? f.outerDt : 0.01 });
      } catch (err) {
        out.push(issue("E_SCN_INIT", "/init", String((err as Error).message ?? err)));
      }
    }
  }

  // controls
  const allow = f.controls?.allow;
  if (!Array.isArray(allow)) out.push(issue("E_SCN_CONTROL", "/controls/allow", "controls.allow must be a list"));
  else {
    for (const [i, c] of allow.entries()) {
      if (!(COMMAND_TYPES as readonly string[]).includes(c)) out.push(issue("E_SCN_CONTROL", `/controls/allow/${i}`, `unknown command type ${String(c)}`));
      else if (coarse && c === "rod.fire") out.push(issue("E_SCN_COARSE", `/controls/allow/${i}`, "a coarse scenario cannot allow rod.fire"));
    }
  }

  // events
  const periodTrips = lib.trips.filter((t: any) => t.input === "truth.period").map((t: any) => t.id as string);
  for (const [i, ev] of (f.events ?? []).entries()) {
    const p = `/events/${i}`;
    if (typeof ev?.at !== "number" || !(ev.at >= 0)) out.push(issue("E_SCN_EVENT", `${p}/at`, "at must be a number >= 0"));
    if (validateCommand(ev?.cmd).length > 0) {
      out.push(issue("E_SCN_EVENT", `${p}/cmd`, "the command does not pass the command schema"));
      continue;
    }
    const type = ev.cmd["type"];
    if (coarse && (type === "rod.fire" || (type === "mode.set" && ev.cmd["mode"] === "pulse"))) {
      out.push(issue("E_SCN_COARSE", `${p}/cmd`, "a coarse scenario cannot fire a rod or enter pulse mode"));
    }
    if (type === "fault.reactivity") {
      if (!(typeof ev.source === "string" && ev.source.trim())) out.push(issue("E_SCN_SOURCE", `${p}/source`, "a reactivity insertion needs a source"));
      // amendment 4: a step insertion trips an unlagged period trip at once
      const missing = periodTrips.filter((t) => !(f.expectTrips ?? []).includes(t));
      if (missing.length > 0) {
        out.push(issue("E_SCN_REACTIVITY_STEP", `${p}/cmd`, `a reactivity step trips ${missing.join(", ")} at once; avoid it, or list it in expectTrips`));
      }
    }
  }

  // goals
  const measured = new Set(lib.instruments.map((i: any) => i.signal as string));
  const seen = new Set<string>();
  const goals = Array.isArray(f.goals) ? f.goals : [];
  if (goals.length === 0) out.push(issue("E_SCN_GOAL", "/goals", "a scenario needs at least one goal"));
  for (const [i, g] of goals.entries()) {
    const p = `/goals/${i}`;
    if (typeof g?.id !== "string" || !/^[a-z0-9-]+$/.test(g.id) || seen.has(g.id)) out.push(issue("E_SCN_GOAL", `${p}/id`, "goal ids must be unique [a-z0-9-]+"));
    if (typeof g?.text !== "string" || !g.text.trim()) out.push(issue("E_SCN_GOAL", `${p}/text`, "a goal needs a text"));
    if (g?.after !== undefined && !seen.has(g.after)) out.push(issue("E_SCN_GOAL", `${p}/after`, `after must name an earlier goal`));
    for (const k of ["for", "within"] as const) {
      if (g?.[k] !== undefined && !(typeof g[k] === "number" && g[k]! > 0)) out.push(issue("E_SCN_GOAL", `${p}/${k}`, `${k} must be > 0`));
    }
    if (typeof g?.id === "string") seen.add(g.id);
    if (!isCheck(g?.check)) {
      out.push(issue("E_SCN_CHECK", `${p}/check`, "the check must use the library's predicate format"));
      continue;
    }
    let plainNumber = false;
    for (const { leaf, path } of leaves(g.check, `${p}/check`)) {
      const sig = leaf.signal;
      const known =
        TRUTH_SIGNALS.includes(sig) ||
        (sig.startsWith("truth.rod.") && lib.rods.some((r) => r.id === sig.slice("truth.rod.".length))) ||
        (sig.startsWith("indicated.") && lib.instruments.some((x: any) => x.id === sig.slice("indicated.".length)));
      if (!known) out.push(issue("E_SCN_CHECK", `${path}/signal`, `unknown signal ${sig}`));
      if (!OPS.includes(leaf.op)) out.push(issue("E_SCN_CHECK", `${path}/op`, `unknown operator ${leaf.op}`));
      // amendment 5: an operator-facing goal reads the instrument where one exists
      if (sig.startsWith("truth.") && measured.has(sig)) {
        out.push(issue("E_SCN_TRUTH_GOAL", `${path}/signal`, `an instrument measures ${sig}; use its indicated.* reading`));
      }
      if (leaf.fromTrip !== undefined) {
        if (leaf.value !== undefined) out.push(issue("E_SCN_CHECK", path, "use value or fromTrip, not both"));
        if (tripSetpoint(lib, leaf.fromTrip) === null) out.push(issue("E_SCN_CHECK", `${path}/fromTrip`, `no setpoint for trip ${leaf.fromTrip}`));
        const t = leaf.times ?? 1;
        const okTimes = leaf.op === "between" ? isNumberPair(t) : typeof t === "number" && Number.isFinite(t);
        if (!okTimes) out.push(issue("E_SCN_CHECK", `${path}/times`, leaf.op === "between" ? "times must be a pair for between" : "times must be a number"));
      } else {
        const v = leaf.value;
        const okValue =
          leaf.op === "between" ? isNumberPair(v) : leaf.op === "eq" || leaf.op === "ne" ? typeof v === "number" || typeof v === "string" : typeof v === "number";
        if (!okValue) out.push(issue("E_SCN_CHECK", `${path}/value`, "the value does not fit the operator"));
        if (typeof v === "number" || isNumberPair(v)) plainNumber = true;
      }
    }
    if (plainNumber && !(typeof g.source === "string" && g.source.trim())) {
      out.push(issue("E_SCN_SOURCE", `${p}/source`, "a goal with a plain number needs a source (or use fromTrip)"));
    }
  }
  return out;
}

/** JSON with sorted keys, so the digest does not depend on key order. */
export function canonicalJson(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonicalJson).join(",")}]`;
  if (v !== null && typeof v === "object") {
    const o = v as Record<string, unknown>;
    return `{${Object.keys(o)
      .sort()
      .filter((k) => o[k] !== undefined)
      .map((k) => `${JSON.stringify(k)}:${canonicalJson(o[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(v);
}

function resolveCheck(c: Check, lib: Library, path: string, thresholds: Record<string, number | [number, number]>): Check {
  if ("all" in c) return { all: c.all.map((x, i) => resolveCheck(x, lib, `${path}/all/${i}`, thresholds)) };
  if ("any" in c) return { any: c.any.map((x, i) => resolveCheck(x, lib, `${path}/any/${i}`, thresholds)) };
  if ("not" in c) return { not: resolveCheck(c.not, lib, `${path}/not`, thresholds) };
  if (c.fromTrip === undefined) return { signal: c.signal, op: c.op, value: c.value };
  const sp = tripSetpoint(lib, c.fromTrip)!;
  const t = c.times ?? 1;
  const value: number | [number, number] = Array.isArray(t) ? [sp * t[0], sp * t[1]] : sp * t;
  thresholds[path] = value;
  return { signal: c.signal, op: c.op, value };
}

/** Validate and prepare a scenario for a library. Throws a ScenarioError with the issues when it is not valid. */
export async function prepareScenario(obj: unknown, lib: Library): Promise<PreparedScenario> {
  const issues = validateScenario(obj, lib);
  if (issues.length > 0) throw new ScenarioError(issues);
  const file = structuredClone(obj) as ScenarioFile;
  const thresholds: Record<string, number | [number, number]> = {};
  const goals = file.goals.map((g) => ({ ...g, check: resolveCheck(g.check, lib, g.id, thresholds) }));
  return {
    file,
    digest: await sha256Hex(new TextEncoder().encode(canonicalJson(file))),
    init: engineInit(file, lib),
    seed: file.seed ?? 1,
    outerDt: file.outerDt,
    goals,
    thresholds,
    events: (file.events ?? [])
      .map((e) => ({ step: dueStep(e.at, file.outerDt), cmd: e.cmd, note: e.note ?? String(e.cmd["type"]) }))
      .sort((a, b) => a.step - b.step),
  };
}

export class ScenarioError extends Error {
  constructor(readonly issues: Issue[]) {
    super(issues.slice(0, 5).map((i) => `${i.code} ${i.path}: ${i.message}`).join("; "));
    this.name = "ScenarioError";
  }
}

export type GoalStatus = "waiting" | "open" | "met" | "failed";

export interface GoalState {
  id: string;
  status: GoalStatus;
  /** When the goal opened (s). */
  openedAt: number | null;
  /** Since when the check has held without a break (s). */
  holdSince: number | null;
  /** When the goal was met or failed (s). */
  t: number | null;
}

/**
 * Tracks each goal after each engine step (D3a). A goal is met the first time its check holds for `for` seconds
 * without a break. A goal with `after` opens when that goal is met. A goal with `within` fails if not met in time.
 */
export class GoalTracker {
  states: GoalState[];

  constructor(
    readonly goals: ResolvedGoal[],
    states?: GoalState[],
  ) {
    this.states = states ? structuredClone(states) : goals.map((g) => ({ id: g.id, status: "waiting", openedAt: null, holdSince: null, t: null }));
  }

  clone(): GoalTracker {
    return new GoalTracker(this.goals, this.states);
  }

  /** Evaluate every goal on the engine's current state. True when a goal changed status. */
  evaluate(e: Engine): boolean {
    const t = e.t;
    const eps = 1e-9 * Math.max(1, e.config.outerDt);
    const get = (sig: string) => e._signal(sig, e.t, e.y);
    let changed = false;
    this.goals.forEach((g, i) => {
      const st = this.states[i]!;
      if (st.status === "waiting") {
        const parent = g.after === undefined ? null : this.states.find((s) => s.id === g.after)!;
        if (parent === null || parent.status === "met") {
          st.status = "open";
          st.openedAt = t;
          changed = true;
        }
      }
      if (st.status !== "open") return;
      if (evalPredicate(g.check, get)) {
        st.holdSince ??= t;
        if (t - st.holdSince >= (g.for ?? 0) - eps) {
          st.status = "met";
          st.t = t;
          changed = true;
          return;
        }
      } else {
        st.holdSince = null;
      }
      if (g.within !== undefined && t - st.openedAt! > g.within + eps) {
        st.status = "failed";
        st.t = t;
        changed = true;
      }
    });
    return changed;
  }

  /** The instructor ends the scenario at time `t`: every goal that is not met fails. True when a goal changed. */
  endAt(t: number): boolean {
    let changed = false;
    for (const st of this.states) {
      if (st.status === "met" || st.status === "failed") continue;
      st.status = "failed";
      st.t = t;
      st.holdSince = null;
      changed = true;
    }
    return changed;
  }

  /** The goals as the views show them. */
  view(): { id: string; text: string; status: GoalStatus; t: number | null }[] {
    return this.goals.map((g, i) => ({ id: g.id, text: g.text, status: this.states[i]!.status, t: this.states[i]!.t }));
  }

  done(): boolean {
    return this.states.every((s) => s.status === "met" || s.status === "failed");
  }
}
