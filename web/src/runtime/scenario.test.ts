import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { nodeReader } from "../library/node-reader";
import type { Engine } from "../sim/engine";
import { loadLibrary, type Library } from "../sim/library";
import { loadSyntheticCore, repoRoot } from "../sim/testing";
import { canonicalJson, dueStep, GoalTracker, prepareScenario, ScenarioError, tripSetpoint, validateScenario, type ScenarioFile } from "./scenario";

const DIR = join(repoRoot, "web", "src", "app", "scenarios");
const shipped = () => readdirSync(DIR).filter((f) => f.endsWith(".json")).map((f) => JSON.parse(readFileSync(join(DIR, f), "utf8")) as ScenarioFile);
const base = () => shipped().find((s) => s.id === "synthetic-power-ascension")!;
const codes = (s: unknown, lib: Library) => validateScenario(s, lib).map((i) => i.code);

describe("scenario validator (docs/m5-scenarios-design.md §3)", () => {
  it("passes every shipped scenario for its library", async () => {
    const libs: Record<string, Library> = {
      "synthetic-core": await loadSyntheticCore(),
      "triga-jsi-242": await loadLibrary(nodeReader(join(repoRoot, "libraries", "triga-jsi-242"))),
      "triga-jsi-242-openmc": await loadLibrary(nodeReader(join(repoRoot, "libraries", "triga-jsi-242-openmc"))),
      "pwr-beavrs-hzp-openmc": await loadLibrary(nodeReader(join(repoRoot, "libraries", "pwr-beavrs-hzp-openmc"))),
    };
    const all = shipped();
    expect(all.map((s) => s.id).sort()).toEqual([
      "pwr-beavrs-hzp-bank-withdrawal",
      "pwr-beavrs-hzp-dilution",
      "synthetic-power-ascension",
      "synthetic-scram-and-restart",
      "triga-242-openmc-low-power-ascension",
      "triga-power-ascension",
      "triga-scram-and-restart",
    ]);
    for (const s of all) expect(validateScenario(s, libs[s.library]!), s.id).toEqual([]);
  });

  it("E_SCN_FIELD: format, id, title, library and expected trips", async () => {
    const lib = await loadSyntheticCore();
    expect(codes({ ...base(), format: "x" }, lib)).toContain("E_SCN_FIELD");
    expect(codes({ ...base(), id: "Bad Id" }, lib)).toContain("E_SCN_FIELD");
    expect(codes({ ...base(), title: " " }, lib)).toContain("E_SCN_FIELD");
    expect(codes({ ...base(), library: "triga-jsi-242" }, lib)).toContain("E_SCN_FIELD");
    expect(codes({ ...base(), expectTrips: ["nope"] }, lib)).toContain("E_SCN_FIELD");
    expect(codes({ ...base(), expectTrips: ["manual", "period-short"] }, lib)).toEqual([]);
  });

  it("E_SCN_COARSE: the outer step, and no pulses in a coarse scenario", async () => {
    const lib = await loadSyntheticCore();
    expect(codes({ ...base(), outerDt: 0.5 }, lib)).toContain("E_SCN_COARSE");
    expect(codes({ ...base(), outerDt: 1, controls: { allow: ["rod.fire"] } }, lib)).toContain("E_SCN_COARSE");
    expect(codes({ ...base(), outerDt: 1, init: { rods: "shutdown", mode: "pulse" } }, lib)).toContain("E_SCN_COARSE");
    const ev = { at: 5, cmd: { type: "mode.set", mode: "pulse" } };
    expect(codes({ ...base(), outerDt: 1, events: [ev] }, lib)).toContain("E_SCN_COARSE");
    expect(codes({ ...base(), outerDt: 1 }, lib)).toEqual([]);
  });

  it("E_SCN_INIT and E_SCN_ROD (amendment 1): the engine's check, and unknown rods", async () => {
    const lib = await loadSyntheticCore();
    expect(codes({ ...base(), init: { rods: "shutdown", mode: "nope" } }, lib)).toContain("E_SCN_INIT");
    expect(codes({ ...base(), init: { rods: { safety: 1, nope: 0.5 } } }, lib)).toEqual(["E_SCN_ROD"]);
    expect(codes({ ...base(), init: { rods: "everything" } }, lib)).toEqual(["E_SCN_ROD"]);
    expect(codes({ ...base(), init: { rods: "reference" } }, lib)).toEqual([]);
    expect(codes({ ...base(), init: { rods: { safety: 1 } } }, lib)).toEqual([]);
  });

  it("E_SCN_CONTROL and E_SCN_EVENT", async () => {
    const lib = await loadSyntheticCore();
    expect(codes({ ...base(), controls: { allow: ["rod.teleport"] } }, lib)).toEqual(["E_SCN_CONTROL"]);
    expect(codes({ ...base(), controls: {} }, lib)).toEqual(["E_SCN_CONTROL"]);
    expect(codes({ ...base(), events: [{ at: -1, cmd: { type: "scram" } }] }, lib)).toEqual(["E_SCN_EVENT"]);
    expect(codes({ ...base(), events: [{ at: 1, cmd: { type: "rod.move", rod: "safety" } }] }, lib)).toEqual(["E_SCN_EVENT"]);
    expect(codes({ ...base(), events: [{ at: 1, cmd: { type: "scram" } }] }, lib)).toEqual([]);
  });

  it("E_SCN_CHECK and E_SCN_GOAL", async () => {
    const lib = await loadSyntheticCore();
    const goal = (g: object) => ({ ...base(), goals: [{ id: "g", text: "t", source: "test", ...g }] });
    expect(codes(goal({ check: { signal: "indicated.nope", op: "gt", value: 1 } }), lib)).toEqual(["E_SCN_CHECK"]);
    expect(codes(goal({ check: { signal: "indicated.linear", op: "about", value: 1 } }), lib)).toEqual(["E_SCN_CHECK"]);
    expect(codes(goal({ check: { signal: "indicated.linear", op: "gt", fromTrip: "nope" } }), lib)).toEqual(["E_SCN_CHECK"]);
    expect(codes(goal({ check: { signal: "indicated.linear", op: "gt", value: 1, fromTrip: "power-high" } }), lib)).toContain("E_SCN_CHECK");
    expect(codes(goal({ check: { signal: "indicated.linear", op: "between", value: 1 } }), lib)).toEqual(["E_SCN_CHECK"]);
    expect(codes(goal({ check: { signal: "indicated.linear", op: "between", fromTrip: "power-high", times: 0.5 } }), lib)).toEqual(["E_SCN_CHECK"]);
    expect(codes(goal({ check: "power > 1" }), lib)).toEqual(["E_SCN_CHECK"]);
    expect(codes(goal({ check: { signal: "truth.rod.nope", op: "lt", value: 0 } }), lib)).toEqual(["E_SCN_CHECK"]);
    const ok = { signal: "indicated.linear", op: "gt", fromTrip: "power-high", times: 0.01 };
    expect(codes(goal({ check: ok, within: 0 }), lib)).toEqual(["E_SCN_GOAL"]);
    expect(codes(goal({ check: ok, after: "later" }), lib)).toEqual(["E_SCN_GOAL"]);
    expect(codes({ ...base(), goals: [{ id: "a", text: "a", check: ok }, { id: "a", text: "b", check: ok }] }, lib)).toEqual(["E_SCN_GOAL"]);
    expect(codes({ ...base(), goals: [] }, lib)).toEqual(["E_SCN_GOAL"]);
  });

  it("E_SCN_SOURCE (D5): a plain number, a level in init, or a reactivity insertion needs a source", async () => {
    const lib = await loadSyntheticCore();
    const g = { id: "g", text: "t", check: { signal: "truth.period", op: "gt", value: 10 } };
    expect(codes({ ...base(), goals: [g] }, lib)).toEqual(["E_SCN_SOURCE"]);
    expect(codes({ ...base(), goals: [{ ...g, source: "a book" }] }, lib)).toEqual([]);
    expect(codes({ ...base(), init: { rods: "shutdown", power: { mode: "given", value: 10 } } }, lib)).toEqual(["E_SCN_SOURCE"]);
    expect(codes({ ...base(), init: { rods: "shutdown", power: { mode: "given", value: 10 }, source: "a book" } }, lib)).toEqual([]);
    const ev = { at: 1, cmd: { type: "fault.reactivity", deltaRho: 1e-4 } };
    expect(codes({ ...base(), expectTrips: ["period-short"], events: [ev] }, lib)).toEqual(["E_SCN_SOURCE"]);
  });

  it("E_SCN_REACTIVITY_STEP (amendment 4): a reactivity step must expect the period trip", async () => {
    const lib = await loadSyntheticCore();
    const ev = { at: 1, cmd: { type: "fault.reactivity", deltaRho: 1e-4 }, source: "a teaching choice" };
    expect(codes({ ...base(), events: [ev] }, lib)).toEqual(["E_SCN_REACTIVITY_STEP"]);
    expect(codes({ ...base(), expectTrips: ["period-short"], events: [ev] }, lib)).toEqual([]);
  });

  it("E_SCN_TRUTH_GOAL (amendment 5): a measured signal must be read through its instrument", async () => {
    const lib = await loadSyntheticCore();
    const g = (signal: string) => ({ ...base(), goals: [{ id: "g", text: "t", source: "s", check: { signal, op: "gt", value: 1 } }] });
    expect(codes(g("truth.power"), lib)).toEqual(["E_SCN_TRUTH_GOAL"]);
    expect(codes(g("truth.fuelTemp"), lib)).toEqual(["E_SCN_TRUTH_GOAL"]);
    // no instrument measures these, so truth is allowed
    expect(codes(g("truth.period"), lib)).toEqual([]);
    expect(codes(g("truth.xenon"), lib)).toEqual([]);
    expect(codes(g("truth.rod.safety"), lib)).toEqual([]);
  });
});

describe("prepared scenarios", () => {
  it("resolve rod presets, trip thresholds and event steps, and record the thresholds (amendment 2)", async () => {
    const lib = await loadSyntheticCore();
    const s = { ...base(), events: [{ at: 0.047, cmd: { type: "scram" } }] };
    const p = await prepareScenario(s, lib);
    expect(p.init.rods).toEqual(Object.fromEntries(lib.rods.map((r) => [r.id, 0])));
    expect(p.thresholds).toEqual({ "one-percent": 2750, "ten-percent": 27500, hold: [13750, 41250] });
    expect(p.goals[2]!.check).toEqual({ signal: "indicated.linear", op: "between", value: [13750, 41250] });
    expect(p.events).toEqual([{ step: 5, cmd: { type: "scram" }, note: "scram" }]);
    const ref = await prepareScenario({ ...base(), init: { rods: "reference" } }, lib);
    expect(ref.init.rods).toEqual(lib.refRods);
    expect(tripSetpoint(lib, "period-short")).toBe(3);
    expect(tripSetpoint(lib, "power-high")).toBe(275000);
    expect(dueStep(0, 0.01)).toBe(0);
    expect(dueStep(0.05, 0.01)).toBe(5);
  });

  it("have a digest that ignores key order and changes with the content", async () => {
    const lib = await loadSyntheticCore();
    const a = await prepareScenario(base(), lib);
    const reordered = Object.fromEntries(Object.entries(base()).reverse());
    expect((await prepareScenario(reordered, lib)).digest).toBe(a.digest);
    expect((await prepareScenario({ ...base(), title: "Other" }, lib)).digest).not.toBe(a.digest);
    expect(canonicalJson({ b: 1, a: [1, { d: 2, c: 3 }] })).toBe('{"a":[1,{"c":3,"d":2}],"b":1}');
    await expect(prepareScenario({ ...base(), outerDt: 2 }, lib)).rejects.toBeInstanceOf(ScenarioError);
  });
});

describe("goal tracker (D3a)", () => {
  /** A stand-in engine: one signal, "truth.period", with a value per step. */
  function fake(values: number[], dt = 1) {
    const e = { t: 0, config: { outerDt: dt }, y: [], _signal: () => values[Math.round(e.t / dt)] };
    return { e: e as unknown as Engine, at: (step: number) => (e.t = step * dt) };
  }
  const leaf = (op: string, value: number) => ({ signal: "truth.period", op, value });

  it("meets a goal when its check holds for `for` seconds without a break", () => {
    const { e, at } = fake([0, 5, 5, 0, 5, 5, 5, 5]);
    const tr = new GoalTracker([{ id: "a", text: "a", check: leaf("gt", 1), for: 2 }]);
    for (let s = 0; s < 8; s++) {
      at(s);
      tr.evaluate(e);
    }
    // holds at 1-2 (broken at 3), then from 4: met at 6
    expect(tr.view()[0]).toMatchObject({ status: "met", t: 6 });
  });

  it("opens a goal with `after` only when that goal is met, and fails it after `within`", () => {
    const { e, at } = fake([0, 5, 0, 0, 0, 0, 0]);
    const tr = new GoalTracker([
      { id: "a", text: "a", check: leaf("gt", 1) },
      { id: "b", text: "b", check: leaf("gt", 100), after: "a", within: 3 },
      { id: "c", text: "c", check: leaf("gt", 1), after: "b" },
    ]);
    at(0);
    tr.evaluate(e);
    expect(tr.view().map((g) => g.status)).toEqual(["open", "waiting", "waiting"]);
    for (let s = 1; s < 7; s++) {
      at(s);
      tr.evaluate(e);
    }
    expect(tr.view().map((g) => [g.status, g.t])).toEqual([
      ["met", 1],
      ["failed", 5], // opened at 1, not met by 1 + 3 s
      ["failed", 5],
    ]);
    expect(tr.done()).toBe(true);
    const copy = tr.clone();
    at(0);
    copy.evaluate(e);
    expect(tr.view()[1]!.status).toBe("failed"); // a clone does not share state
  });
});
